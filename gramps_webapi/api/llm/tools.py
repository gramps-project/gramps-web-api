#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Pydantic AI tools for LLM interactions."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from functools import wraps
from typing import Any

from pydantic_ai import RunContext
from werkzeug.exceptions import HTTPException

from ..resources.filters import apply_filter
from ..resources.util import get_one_relationship
from ..search import get_search_indexer
from ..util import get_db_outside_request, get_logger
from .deps import AgentDeps
from .render import render_handle, render_object


def _query_rule(query: str) -> dict[str, Any]:
    """Return a filter rule matching objects with a GOQL expression."""
    return {"name": "MatchesQuery", "values": [query]}


def _place_handles(db_handle, text: str) -> list[str]:
    """Return the handles of the places whose full name contains the text.

    The full name includes the enclosing places, e.g. "Copenhagen, Denmark",
    like the place matching of the Gramps filter rules. The names are
    resolved in memory, after reading all places once.
    """
    names: dict[str, str] = {}
    parents: dict[str, str] = {}
    for place in db_handle.iter_places():
        names[place.handle] = place.get_name().get_value() or place.get_title()
        placeref_list = place.get_placeref_list()
        if placeref_list:
            parents[place.handle] = placeref_list[0].ref

    def full_name(handle: str) -> str:
        parts, seen = [], set()
        while handle in names and handle not in seen:
            seen.add(handle)
            parts.append(names[handle])
            handle = parents.get(handle, "")
        return ", ".join(parts)

    text = text.casefold()
    return [handle for handle in names if text in full_name(handle).casefold()]


class _LocatedIn(ast.NodeTransformer):
    """Rewrite `located_in(path, 'name')` to `path.handle in [...]`."""

    def __init__(self, db_handle):
        self.db_handle = db_handle

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        # e.g. birth.place.name: the name of a place does not include the
        # enclosing places, so matching it misses e.g. cities in a country
        parent = node.value
        parent_name = (
            parent.attr
            if isinstance(parent, ast.Attribute)
            else parent.id if isinstance(parent, ast.Name) else ""
        )
        if node.attr in ("name", "title") and parent_name in ("place", "enclosed_by"):
            raise ValueError(
                "do not match place names directly; use the function located_in"
                f" with the place's field first, e.g. located_in({ast.unparse(parent)},"
                " 'Denmark'), which also matches enclosing places"
            )
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "located_in":
            # e.g. birth.place.located_in('Denmark')
            names = [
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            ]
            example = f"located_in({ast.unparse(node.func.value)}, "
            example += f"'{names[0]}')" if names else "'Denmark')"
            raise ValueError(
                "located_in is a function, not a field; pass the place's field"
                f" as the first argument: {example}"
            )
        if not (isinstance(node.func, ast.Name) and node.func.id == "located_in"):
            return node
        if (
            len(node.args) != 2
            or node.keywords
            or not isinstance(node.args[1], ast.Constant)
            or not isinstance(node.args[1].value, str)
        ):
            raise ValueError(
                "located_in takes the place's field and a place name,"
                " e.g. located_in(birth.place, 'Boston')"
            )
        name = node.args[1].value
        handles = _place_handles(self.db_handle, name)
        if not handles:
            raise ValueError(f"no place in the tree matches '{name}'")
        return ast.Compare(
            left=ast.Attribute(value=node.args[0], attr="handle", ctx=ast.Load()),
            ops=[ast.In()],
            comparators=[
                ast.List(
                    elts=[ast.Constant(handle) for handle in handles],
                    ctx=ast.Load(),
                )
            ],
        )


def _resolve_places(db_handle, query: str) -> str:
    """Replace the `located_in(path, 'name')` calls of a query.

    GOQL can only match the name of a place itself, not of its enclosing
    places, so a place is matched by the handles of all places whose full
    name contains the name. Matching place names directly is rejected.
    """
    if "located_in" not in query and "place" not in query:
        return query
    try:
        tree = ast.parse(query, mode="eval")
    except SyntaxError:
        # GOQL reports the error
        return query
    return ast.unparse(_LocatedIn(db_handle).visit(tree))


def _get_relationship_prefix(db_handle, anchor_person, result_person, logger) -> str:
    """Get a relationship string prefix for a result person.

    Args:
        db_handle: Database handle
        anchor_person: The Person object to calculate relationship from
        result_person: The Person object to calculate relationship to
        logger: Logger instance

    Returns:
        A formatted relationship prefix like "[grandfather] " or empty string
    """
    try:
        rel_string, dist_orig, dist_other = get_one_relationship(
            db_handle=db_handle,
            person1=anchor_person,
            person2=result_person,
            depth=10,
        )
        if rel_string and rel_string.lower() not in ["", "self"]:
            return f"[{rel_string}] "
        elif dist_orig == 0 and dist_other == 0:
            return "[self] "
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(
            "Error calculating relationship between %s and %s: %s",
            anchor_person.gramps_id,
            result_person.gramps_id,
            e,
        )
    return ""


def _leaf_messages(messages: Any) -> list[str]:
    """Return the texts in an API error's `messages`, without the keys that
    locate them in the request: the tools build the request, so the model
    can't relate those keys to anything it wrote.
    """
    if isinstance(messages, dict):
        return [text for value in messages.values() for text in _leaf_messages(value)]
    if isinstance(messages, list):
        return [text for value in messages for text in _leaf_messages(value)]
    return [str(messages)]


def _describe_error(error: Exception) -> str:
    """Return an error's text for the model, including the details an API
    error carries in `messages` (e.g. why a rule value didn't parse, or
    GOQL's explanation of an invalid query), which `str(error)` leaves out.
    """
    if isinstance(error, HTTPException) and error.response is not None:
        try:
            body = json.loads(error.get_response().get_data(as_text=True))["error"]
        except (ValueError, KeyError, TypeError):
            return str(error)
        details = _leaf_messages(body.get("messages") or [])
        if details:
            return f"{body.get('message', '')}: {'; '.join(details)}"
        return str(body.get("message", error))
    return str(error)


def _apply_gramps_filter(
    ctx: RunContext[AgentDeps],
    namespace: str,
    rules: list[dict[str, Any]],
    max_results: int,
    empty_message: str = "No results found matching the filter criteria.",
    show_relation_with: str = "",
    handles: list | None = None,
) -> str:
    """Apply a Gramps filter and return formatted results.

    This is a common helper for filter tools that handles:
    - Database handle management
    - Filter application
    - Result iteration with privacy checking
    - Context length limiting
    - Truncation messages
    - Error handling
    - Optional relationship calculation

    Args:
        ctx: The Pydantic AI run context with dependencies
        namespace: Gramps object namespace ("Person", "Event", "Family", etc.)
        rules: List of filter rule dictionaries
        max_results: Maximum number of results to return (already validated)
        empty_message: Message to return when no results found
        show_relation_with: Gramps ID of anchor person for relationship calculation (Person namespace only)
        handles: Optional pre-filtered list of handles to restrict the search space

    Returns:
        Formatted string with matching objects or error message
    """
    logger = get_logger()
    db_handle = None

    try:
        # Use get_db_outside_request to avoid Flask's g caching, since Pydantic AI's
        # run_sync() uses an event loop that can violate SQLite's thread-safety.
        db_handle = get_db_outside_request(
            tree=ctx.deps.tree,
            view_private=ctx.deps.include_private,
            readonly=True,
            user_id=ctx.deps.user_id,
        )

        # rule values come from the chat, so only log the rule names
        logger.debug("%s filter rules: %s", namespace, [rule["name"] for rule in rules])

        try:
            rules = [
                (
                    {**rule, "values": [_resolve_places(db_handle, rule["values"][0])]}
                    if rule["name"] == "MatchesQuery"
                    else rule
                )
                for rule in rules
            ]
        except ValueError as e:
            db_handle.close()
            return f"Invalid filter: {e}"

        args = {"rules": json.dumps({"rules": rules})}
        try:
            matching_handles = apply_filter(
                db_handle=db_handle,
                args=args,
                namespace=namespace,
                handles=handles,
            )
        except HTTPException as e:
            # e.g. an invalid query; the message tells the model how to fix it
            # but contains the query, so it is not logged
            logger.debug("%s filter failed with status %s", namespace, e.code)
            db_handle.close()
            return f"Invalid filter: {_describe_error(e)}"

        if not matching_handles:
            db_handle.close()
            return empty_message

        total_matches = len(matching_handles)
        matching_handles = matching_handles[:max_results]

        context_parts: list[str] = []
        max_length = ctx.deps.max_context_length
        per_item_max = 10000
        current_length = 0

        # Get the anchor person for relationship calculation if requested
        anchor_person = None
        if show_relation_with and namespace == "Person":
            try:
                anchor_person = db_handle.get_person_from_gramps_id(show_relation_with)
                if not anchor_person:
                    logger.warning(
                        "Anchor person %s not found for relationship calculation",
                        show_relation_with,
                    )
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(
                    "Error fetching anchor person %s: %s", show_relation_with, e
                )

        # Get the appropriate method to fetch objects
        get_method_name = f"get_{namespace.lower()}_from_handle"
        get_method = getattr(db_handle, get_method_name)

        for handle in matching_handles:
            try:
                obj = get_method(handle)

                # the private proxy returns None for private objects
                if obj is None:
                    continue

                content = render_object(db_handle, namespace, obj)

                # Add relationship prefix if anchor person is set
                if anchor_person and namespace == "Person":
                    rel_prefix = _get_relationship_prefix(
                        db_handle, anchor_person, obj, logger
                    )
                    content = rel_prefix + content

                # Truncate individual items if they're too long
                if len(content) > per_item_max:
                    logger.debug(
                        "Truncating %s content from %d to %d chars",
                        namespace,
                        len(content),
                        per_item_max,
                    )
                    content = _truncate_content(content, per_item_max)

                # Check if adding this item would exceed total limit
                if current_length + len(content) > max_length:
                    logger.debug(
                        "Reached max context length (%d chars), stopping at %d results",
                        max_length,
                        len(context_parts),
                    )
                    break

                context_parts.append(content)
                current_length += len(content) + 2

            except Exception as e:  # pylint: disable=broad-except
                logger.warning("Error processing %s %s: %s", namespace, handle, e)
                continue

        if not context_parts:
            db_handle.close()
            return f"{empty_message} (or all results are private)."

        result = "\n\n".join(context_parts)

        # Add truncation messages
        returned_count = len(context_parts)
        if returned_count < total_matches:
            result += f"\n\n---\nShowing {returned_count} of {total_matches} matching {namespace.lower()}s. Use max_results parameter to see more."
        elif total_matches == max_results:
            result += f"\n\n---\nShowing {returned_count} {namespace.lower()}s (limit reached). There may be more matches."

        logger.debug(
            "Tool filter_%ss returned %d results (%d chars)",
            namespace.lower(),
            returned_count,
            len(result),
        )

        db_handle.close()
        return result

    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error filtering %ss: %s", namespace.lower(), e)
        if db_handle is not None:
            try:
                db_handle.close()
            except Exception:  # pylint: disable=broad-except
                pass
        return f"Error filtering {namespace.lower()}s: {_describe_error(e)}"


def _truncate_content(
    content: str, max_chars: int, head: int = 4000, tail: int = 1000
) -> str:
    """Truncate long content using head+tail strategy.

    Keeps the first `head` chars and last `tail` chars, with an elision marker in
    between showing how many characters were dropped. This is more useful to the
    model than a front-only cut because the tail often contains summary information.
    """
    if len(content) <= max_chars:
        return content
    if head + tail >= len(content):
        # Truncation would not reduce the content; return as-is.
        return content
    elided = len(content) - head - tail
    return content[:head] + f"\n\n...[{elided} chars elided]...\n\n" + content[-tail:]


def log_tool_call(func):
    """Decorator to log tool usage."""
    logger = get_logger()

    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug("Tool called: %s", func.__name__)
        return func(*args, **kwargs)

    return wrapper


@log_tool_call
def get_current_date(_ctx: RunContext[AgentDeps]) -> str:
    """Returns today's date in ISO format (YYYY-MM-DD)."""
    logger = get_logger()

    result = datetime.now().date().isoformat()
    logger.debug("Tool get_current_date returned: %s", result)
    return result


@log_tool_call
def search_genealogy_database(
    ctx: RunContext[AgentDeps],
    query: str,
    object_type: str = "",
    max_results: int = 20,
) -> str:
    """Search the family tree database for exact names or phrases.

    Each record matches on its own text: names, descriptions, attributes,
    addresses, and note text; event records also contain the names of their
    main participants. Dates, places of events, and relatives are not
    searchable; use the filter tools for them.

    Args:
        query: Exact names or phrases to match.
        object_type: Restrict to one object type: "Person", "Family", "Event",
            "Place", "Source", "Citation", "Repository", "Note", "Media".
            Leave empty to search all types.
        max_results: Maximum results to return (default: 20, max: 50)

    Returns:
        Formatted genealogical data matching the query.
    """
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback(
            "search_genealogy_database", "Searching genealogy database..."
        )

    logger = get_logger()

    # Limit max_results to reasonable bounds
    max_results = min(max(1, max_results), 50)

    object_types = [object_type.lower()] if object_type else None

    db_handle = None
    try:
        searcher = get_search_indexer(ctx.deps.tree)
        total, hits = searcher.search(
            query=query,
            page=1,
            pagesize=max_results,
            include_private=ctx.deps.include_private,
            object_types=object_types,
        )

        no_results = (
            "No results found in the genealogy database."
            " All search terms must match, so try fewer or different words "
            "(e.g. only the surname, or a name variant), or use filter_people "
            "for names, dates and places."
        )
        if not hits:
            return no_results

        # The index stores a bag of words without links or dates, so each hit
        # is rendered from the database like in the get_* tools.
        db_handle = get_db_outside_request(
            tree=ctx.deps.tree,
            view_private=ctx.deps.include_private,
            readonly=True,
            user_id=ctx.deps.user_id,
        )

        context_parts: list[str] = []
        max_length = ctx.deps.max_context_length
        per_item_max = 10000  # Maximum chars per individual item
        current_length = 0

        for hit in hits:
            content = render_handle(
                db_handle, hit["object_type"].capitalize(), hit["handle"]
            )
            if not content:
                # deleted since the index was last updated
                continue

            # Truncate individual items if they're too long
            if len(content) > per_item_max:
                logger.debug(
                    "Truncating search result from %d to %d chars",
                    len(content),
                    per_item_max,
                )
                content = _truncate_content(content, per_item_max)

            if current_length + len(content) > max_length:
                logger.debug(
                    "Reached max context length (%d chars), stopping at %d results",
                    max_length,
                    len(context_parts),
                )
                break
            context_parts.append(content)
            current_length += len(content) + 2

        if not context_parts:
            # e.g. only tags matched
            return no_results
        result = "\n\n".join(context_parts)
        if len(context_parts) < total:
            result += f"\n\n---\nShowing {len(context_parts)} of {total} matches."
        logger.debug(
            "Tool search_genealogy_database returned %d results (%d chars)",
            len(context_parts),
            len(result),
        )
        return result

    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error searching genealogy database: %s", e)
        return f"Error searching the database: {str(e)}"
    finally:
        if db_handle is not None:
            db_handle.close()


@log_tool_call
def filter_people(
    ctx: RunContext[AgentDeps],
    query: str = "",
    birth_place: str = "",
    death_place: str = "",
    ancestor_of: str = "",
    ancestor_generations: int = 10,
    descendant_of: str = "",
    descendant_generations: int = 10,
    probably_alive_on_date: str = "",
    has_common_ancestor_with: str = "",
    degrees_of_separation_from: str = "",
    degrees_of_separation: int = 2,
    max_results: int = 50,
    show_relation_with: str = "",
) -> str:
    """Filter people in the family tree with a query and relationship criteria.

    All given criteria must match.

    IMPORTANT: When filtering by relationships (ancestor_of, descendant_of, degrees_of_separation_from),
    ALWAYS set show_relation_with to the same Gramps ID to get relationship labels in results.
    Without it, you cannot determine specific relationships like "grandfather" vs "father".

    Query fields of a person: given_name, surname (the primary name),
    gender (Person.MALE, Person.FEMALE, Person.UNKNOWN), birth and death (the
    birth and death events, e.g. birth.date.sortval, death.description).
    Collections for any()/len(): events (all events, e.g. burial), families
    (as a spouse), parent_families (as a child), alternate_names,
    associations, notes, citations, media.

    Query examples:
        - surname Smith: "'Smith' in surname"
        - women named Mary: "gender == Person.FEMALE and 'Mary' in given_name"
        - born in 1850: "Date('1850') <= birth.date.sortval < Date('1851')"
        - born before 1900: "0 < birth.date.sortval < Date('1900')"
        - died between 1890 and 1899: "Date('1890') <= death.date.sortval < Date('1900')"
        - no birth date recorded: "birth.date.sortval is None or birth.date.sortval == 0"
        - buried: "any(events, type.value == EventType.BURIAL)"
        - buried at Windsor: "any(events, type.value == EventType.BURIAL and located_in(place, 'Windsor'))"
        - born in Denmark or Norway: "located_in(birth.place, 'Denmark') or located_in(birth.place, 'Norway')"
        - with a custom event type: "any(events, type.string == 'Coronation')"
        - married more than once: "len(families) > 1"
        - no parents recorded: "not any(parent_families)"
        - an alternate name Doyle: "any(alternate_names, 'Doyle' in surname_list[0].surname)"

    Args:
        query: A query expression, see the system prompt and the examples
        birth_place: Place name where the person was born (partial match,
            including enclosing places, e.g. the country)
        death_place: Place name where the person died (partial match,
            including enclosing places)
        ancestor_of: Gramps ID of person to find ancestors of (e.g., "I0044")
        ancestor_generations: Maximum generations to search for ancestors (default: 10)
        descendant_of: Gramps ID of person to find descendants of (e.g., "I0044")
        descendant_generations: Maximum generations to search for descendants (default: 10)
        probably_alive_on_date: Date to check if person was likely alive (YYYY-MM-DD)
        has_common_ancestor_with: Gramps ID to find people sharing an ancestor (e.g., "I0044")
        degrees_of_separation_from: Gramps ID of person to find relatives connected to (e.g., "I0044")
        degrees_of_separation: Maximum relationship path length (default: 2). Each parent-child
            or spousal connection counts as 1. Examples: sibling=2, grandparent=2, uncle=3,
            first cousin=4, brother-in-law=2
        max_results: Maximum results to return (default: 50, max: 100)
        show_relation_with: Gramps ID of person to show relationships relative to (e.g., "I0044").
            When set, each result will include the relationship to this anchor person.

    Returns:
        Formatted list of people matching the filter criteria.

    Examples:
        - Find who was alive in 1880: probably_alive_on_date="1880-01-01"
        - Find cousins: has_common_ancestor_with="I0044"
        - Find someone's parents (with labels): ancestor_of="I0044", ancestor_generations=1, show_relation_with="I0044"
        - Find someone's grandfathers (with labels): ancestor_of="I0044", ancestor_generations=2, query="gender == Person.MALE", show_relation_with="I0044"
        - Find siblings (with labels): degrees_of_separation_from="I0044", degrees_of_separation=2, show_relation_with="I0044"
        - Find extended family (uncles, aunts): degrees_of_separation_from="I0044", degrees_of_separation=3
        - Find ancestors born in Germany: ancestor_of="I0044", birth_place="Germany", show_relation_with="I0044"
    """
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback(
            "filter_people", "Filtering people in family tree..."
        )

    logger = get_logger()

    max_results = min(max(1, max_results), 100)

    rules: list[dict[str, Any]] = []

    if query:
        rules.append(_query_rule(query))

    if birth_place:
        rules.append({"name": "HasBirth", "values": ["", birth_place, ""]})

    if death_place:
        rules.append({"name": "HasDeath", "values": ["", death_place, ""]})

    if ancestor_of:
        rules.append(
            {
                "name": "IsLessThanNthGenerationAncestorOf",
                "values": [ancestor_of, str(ancestor_generations + 1)],
            }
        )

    if descendant_of:
        rules.append(
            {
                "name": "IsLessThanNthGenerationDescendantOf",
                "values": [descendant_of, str(descendant_generations + 1)],
            }
        )

    if has_common_ancestor_with:
        rules.append(
            {"name": "HasCommonAncestorWith", "values": [has_common_ancestor_with]}
        )

    if degrees_of_separation_from:
        # Check if DegreesOfSeparation filter is available (from FilterRules addon)
        from ..resources.filters import get_rule_list

        available_rules = [rule.__name__ for rule in get_rule_list("Person")]  # type: ignore
        if "DegreesOfSeparation" in available_rules:
            rules.append(
                {
                    "name": "DegreesOfSeparation",
                    "values": [degrees_of_separation_from, str(degrees_of_separation)],
                }
            )
        else:
            logger.warning(
                "DegreesOfSeparation filter not available. "
                "Install FilterRules addon to use this feature."
            )
            return (
                "DegreesOfSeparation filter is not available. "
                "The FilterRules addon must be installed to use this feature."
            )

    if probably_alive_on_date:
        rules.append({"name": "ProbablyAlive", "values": [probably_alive_on_date]})

    if not rules:
        return (
            "No filter criteria provided. Please specify at least one filter parameter."
        )

    return _apply_gramps_filter(
        ctx=ctx,
        namespace="Person",
        rules=rules,
        max_results=max_results,
        empty_message="No people found matching the filter criteria.",
        show_relation_with=show_relation_with,
    )


@log_tool_call
def filter_events(
    ctx: RunContext[AgentDeps],
    query: str = "",
    place: str = "",
    participant_id: str = "",
    max_results: int = 50,
) -> str:
    """Filter events in the genealogy database with a query and a place.

    Events are occurrences in people's lives (births, deaths, marriages, etc.)
    or general historical events. Results list the participants of each event.
    All given criteria must match.

    Query fields of an event: type (type.value for standard types, e.g.
    EventType.BIRTH, EventType.DEATH, EventType.MARRIAGE, EventType.BAPTISM,
    EventType.BURIAL, EventType.CENSUS, EventType.OCCUPATION,
    EventType.RESIDENCE; type.string for custom types), date (date.sortval),
    description.

    Query examples:
        - marriages: "type.value == EventType.MARRIAGE"
        - births in 1850: "type.value == EventType.BIRTH and Date('1850') <= date.sortval < Date('1851')"
        - events between 1892 and 1900: "Date('1892') <= date.sortval < Date('1901')"
        - events before 1900: "0 < date.sortval < Date('1900')"
        - coronations (a custom type): "type.string == 'Coronation'"
        - description mentions a war: "'war' in description"
        - in Boston or Cambridge: "located_in(place, 'Boston') or located_in(place, 'Cambridge')"

    Args:
        query: A query expression, see the system prompt and the examples
        place: Place name where the event took place (partial match,
            including enclosing places, e.g. "Boston" or "Massachusetts")
        participant_id: Gramps ID of a person who participated in the event (e.g., "I0001")
        max_results: Maximum number of results to return (1-100, default 50)

    Returns:
        A formatted string containing matching events with their details, or an error message.

    Examples:
        - "marriages in Boston": query="type.value == EventType.MARRIAGE", place="Boston"
        - "burials at Windsor": query="type.value == EventType.BURIAL", place="Windsor"
        - "events for person I0044": participant_id="I0044"
    """
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback("filter_events", "Filtering events...")

    max_results = min(max(1, max_results), 100)

    rules: list[dict[str, Any]] = []

    if query:
        rules.append(_query_rule(query))

    if place:
        rules.append({"name": "HasData", "values": ["", "", place, ""]})

    if not rules and not participant_id:
        return (
            "No filter criteria provided. Please specify at least one filter parameter "
            "(query, place, or participant_id)."
        )

    # Resolve participant_id to a set of event handles before filtering.
    # MatchesPersonFilter requires a named filter stored in Gramps and cannot
    # accept inline JSON, so we look up the person's events directly instead.
    participant_handles: list | None = None
    if participant_id:
        logger = get_logger()
        try:
            db_handle = get_db_outside_request(
                tree=ctx.deps.tree,
                view_private=ctx.deps.include_private,
                readonly=True,
                user_id=ctx.deps.user_id,
            )
            try:
                person = db_handle.get_person_from_gramps_id(participant_id)
            finally:
                db_handle.close()
            if person is None:
                return f"No person found with Gramps ID '{participant_id}'."
            participant_handles = [ref.ref for ref in person.get_event_ref_list()]
            if not participant_handles:
                return f"No events found for person '{participant_id}'."
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error looking up participant %s: %s", participant_id, e)
            return f"Error looking up participant '{participant_id}': {e}"

    if not rules:
        # participant_id only — return all events for that person directly
        rules = [{"name": "AllEvents", "values": []}]

    return _apply_gramps_filter(
        ctx=ctx,
        namespace="Event",
        rules=rules,
        max_results=max_results,
        empty_message="No events found matching the filter criteria.",
        handles=participant_handles,
    )


def _page(content: str, offset: int, limit: int, tool: str) -> str:
    """Return a section of a long text, saying how to read the next one."""
    offset = max(0, offset)
    if offset == 0 and len(content) <= limit:
        return content
    if offset >= len(content):
        return f"The text has only {len(content)} characters."
    end = min(offset + limit, len(content))
    page = content[offset:end]
    if end < len(content):
        page += (
            f"\n\n[Characters {offset}–{end} of {len(content)}. "
            f"Call {tool} with offset={end} to read on.]"
        )
    else:
        page += f"\n\n[Characters {offset}–{end} of {len(content)}, end of text.]"
    return page


def _get_object(
    ctx: RunContext[AgentDeps],
    class_name: str,
    gramps_id: str,
    offset: int | None = None,
) -> str:
    """Fetch and render a single object by its Gramps ID.

    Long records are truncated, unless `offset` is given: then the section
    starting at that character is returned.
    """
    label = class_name.lower()
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback(f"get_{label}", f"Fetching {label} record...")

    logger = get_logger()
    try:
        db_handle = get_db_outside_request(
            tree=ctx.deps.tree,
            view_private=ctx.deps.include_private,
            readonly=True,
            user_id=ctx.deps.user_id,
        )
        try:
            obj = db_handle.method("get_%s_from_gramps_id", class_name)(gramps_id)
            if obj is None:
                return f"No {label} found with Gramps ID '{gramps_id}'."
            content = render_object(db_handle, class_name, obj)
        finally:
            db_handle.close()
        limit = min(ctx.deps.max_context_length // 2, 10000)
        if offset is not None:
            return _page(content, offset, limit, f"get_{label}")
        return _truncate_content(content, limit)
    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error fetching %s %s: %s", label, gramps_id, e)
        return f"Error fetching {label} '{gramps_id}': {e}"


@log_tool_call
def get_person(ctx: RunContext[AgentDeps], gramps_id: str) -> str:
    """Fetch the full record for a single person by their Gramps ID.

    Use this after finding a Gramps ID in search or filter results to retrieve
    the complete details for that person: names, events, parents, spouses and
    children, attributes, and links to notes. This is the most efficient way
    to look up a known individual.

    Args:
        gramps_id: The Gramps ID of the person (e.g., "I0044")

    Returns:
        Full person record as formatted text, or an error message.
    """
    return _get_object(ctx, "Person", gramps_id)


@log_tool_call
def get_family(ctx: RunContext[AgentDeps], gramps_id: str) -> str:
    """Fetch the full record for a single family by their Gramps ID.

    Use this after finding a family Gramps ID in search or filter results to
    retrieve the complete record: spouses, children, marriage events, notes, etc.

    Args:
        gramps_id: The Gramps ID of the family (e.g., "F0001")

    Returns:
        Full family record as formatted text, or an error message.
    """
    return _get_object(ctx, "Family", gramps_id)


@log_tool_call
def get_event(ctx: RunContext[AgentDeps], gramps_id: str) -> str:
    """Fetch the full record for a single event by its Gramps ID.

    Use this after finding an event Gramps ID in search or filter results to
    retrieve the complete details: type, date, place, description, participants, etc.

    Args:
        gramps_id: The Gramps ID of the event (e.g., "E0123")

    Returns:
        Full event record as formatted text, or an error message.
    """
    return _get_object(ctx, "Event", gramps_id)


@log_tool_call
def get_place(ctx: RunContext[AgentDeps], gramps_id: str) -> str:
    """Fetch the full record for a single place by its Gramps ID.

    Use this after finding a place Gramps ID in search or filter results to
    retrieve the complete details: name, type, coordinates, place hierarchy, etc.

    Args:
        gramps_id: The Gramps ID of the place (e.g., "P0042")

    Returns:
        Full place record as formatted text, or an error message.
    """
    return _get_object(ctx, "Place", gramps_id)


@log_tool_call
def get_note(ctx: RunContext[AgentDeps], gramps_id: str, offset: int = 0) -> str:
    """Fetch the full text of a single note by its Gramps ID.

    Other records only show the beginning of their notes. Use this to read a
    note in full, e.g. a biography, and to see which records it belongs to.
    Long notes are returned in sections; the end of each section says which
    offset to use for the next one.

    Args:
        gramps_id: The Gramps ID of the note (e.g., "N0001")
        offset: Character position to start reading from (default: 0)

    Returns:
        Note text and the records referencing it, or an error message.
    """
    return _get_object(ctx, "Note", gramps_id, offset=offset)


@log_tool_call
def filter_families(
    ctx: RunContext[AgentDeps],
    query: str = "",
    marriage_place: str = "",
    max_results: int = 50,
) -> str:
    """Filter families in the genealogy database with a query and a marriage place.

    A "family" in Gramps represents a couple (with or without children) and may
    include marriage events, children, and notes. All given criteria must match.

    Query fields of a family: father and mother (the two partners, people with
    the fields of filter_people, e.g. father.surname, mother.birth.date.sortval),
    type (type.value: FamilyRelType.MARRIED, FamilyRelType.UNMARRIED,
    FamilyRelType.CIVIL_UNION, FamilyRelType.UNKNOWN). Collections for
    any()/len(): children (people), events (e.g. the marriage).

    Query examples:
        - father named Smith: "'Smith' in father.surname"
        - Smith father and Jones mother: "'Smith' in father.surname and 'Jones' in mother.surname"
        - married in the 1860s: "any(events, type.value == EventType.MARRIAGE and Date('1860') <= date.sortval < Date('1870'))"
        - married before 1900: "any(events, type.value == EventType.MARRIAGE and 0 < date.sortval < Date('1900'))"
        - unmarried couples: "type.value == FamilyRelType.UNMARRIED"
        - five or more children: "len(children) >= 5"
        - a child named Steve: "any(children, 'Steve' in given_name)"
        - mother born in 1850: "Date('1850') <= mother.birth.date.sortval < Date('1851')"
        - mother born in Denmark: "located_in(mother.birth.place, 'Denmark')"

    Args:
        query: A query expression, see the system prompt and the examples
        marriage_place: Place of marriage (partial match, including enclosing
            places, e.g. "Boston")
        max_results: Maximum results to return (default: 50, max: 100)

    Returns:
        Formatted list of families matching the filter criteria.
    """
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback("filter_families", "Filtering families...")

    max_results = min(max(1, max_results), 100)

    rules: list[dict[str, Any]] = []

    if query:
        rules.append(_query_rule(query))

    if marriage_place:
        rules.append(
            {"name": "HasEvent", "values": ["Marriage", "", marriage_place, "", ""]}
        )

    if not rules:
        return (
            "No filter criteria provided. Please specify at least one filter parameter."
        )

    return _apply_gramps_filter(
        ctx=ctx,
        namespace="Family",
        rules=rules,
        max_results=max_results,
        empty_message="No families found matching the filter criteria.",
    )
