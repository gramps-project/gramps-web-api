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

import json
from datetime import datetime
from functools import wraps
from typing import Any

from pydantic_ai import RunContext

from ..resources.filters import apply_filter
from ..resources.util import get_one_relationship
from ..search import get_semantic_search_indexer
from ..search.text import obj_strings_from_object
from ..util import get_db_outside_request, get_logger
from .deps import AgentDeps


def _build_date_expression(before: str, after: str) -> str:
    """Build a date string from before/after parameters.

    Args:
        before: Year before which to filter (e.g., "1900")
        after: Year after which to filter (e.g., "1850")

    Returns:
        A date string for Gramps filters:
        - "between 1850 and 1900" for date ranges
        - "after 1850" for only after
        - "before 1900" for only before
    """
    if before and after:
        return f"between {after} and {before}"
    if after:
        return f"after {after}"
    if before:
        return f"before {before}"
    return ""


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


def _apply_gramps_filter(
    ctx: RunContext[AgentDeps],
    namespace: str,
    rules: list[dict[str, Any]],
    max_results: int,
    empty_message: str = "No results found matching the filter criteria.",
    show_relation_with: str = "",
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

        filter_dict: dict[str, Any] = {"rules": rules}
        if len(rules) > 1:
            filter_dict["function"] = "and"

        filter_rules = json.dumps(filter_dict)
        logger.debug("%s filter rules: %s", namespace, filter_rules)

        args = {"rules": filter_rules}
        matching_handles = apply_filter(
            db_handle=db_handle,
            args=args,
            namespace=namespace,
            handles=None,
        )

        if not matching_handles:
            db_handle.close()
            return empty_message

        total_matches = len(matching_handles)
        matching_handles = matching_handles[:max_results]

        context_parts: list[str] = []
        max_length = ctx.deps.max_context_length
        per_item_max = 10000  # Maximum chars per individual item
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

                if not ctx.deps.include_private and obj.private:
                    continue

                obj_dict = obj_strings_from_object(
                    db_handle=db_handle,
                    class_name=namespace,
                    obj=obj,
                    semantic=True,
                )

                if not obj_dict:
                    continue

                # obj_strings_from_object always returns string_all/string_public
                content = (
                    obj_dict["string_all"]
                    if ctx.deps.include_private
                    else obj_dict["string_public"]
                )

                if not content:
                    continue

                # Add relationship prefix if anchor person is set
                if anchor_person and namespace == "Person":
                    rel_prefix = _get_relationship_prefix(
                        db_handle, anchor_person, obj, logger
                    )
                    content = rel_prefix + content

                # Truncate individual items if they're too long
                if len(content) > per_item_max:
                    content = (
                        content[:per_item_max]
                        + "\n\n[Content truncated due to length...]"
                    )
                    logger.debug(
                        "Truncated %s content from %d to %d chars",
                        namespace,
                        len(content) - per_item_max,
                        per_item_max,
                    )

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
        return f"Error filtering {namespace.lower()}s: {str(e)}"


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
    ctx: RunContext[AgentDeps], query: str, max_results: int = 20
) -> str:
    """Searches the user's family tree using semantic similarity.

    Args:
        query: Search query for genealogical information
        max_results: Maximum results to return (default: 20, max: 50)

    Returns:
        Formatted genealogical data including people, families, events, places,
        sources, citations, repositories, notes, and media matching the query.
    """

    logger = get_logger()

    # Limit max_results to reasonable bounds
    max_results = min(max(1, max_results), 50)

    try:
        searcher = get_semantic_search_indexer(ctx.deps.tree)
        _, hits = searcher.search(
            query=query,
            page=1,
            pagesize=max_results,
            include_private=ctx.deps.include_private,
            include_content=True,
        )

        if not hits:
            return "No results found in the genealogy database."

        context_parts: list[str] = []
        max_length = ctx.deps.max_context_length
        per_item_max = 10000  # Maximum chars per individual item
        current_length = 0

        for hit in hits:
            content = hit.get("content", "")

            # Truncate individual items if they're too long
            if len(content) > per_item_max:
                content = (
                    content[:per_item_max] + "\n\n[Content truncated due to length...]"
                )
                logger.debug(
                    "Truncated search result from %d to %d chars",
                    len(content) - per_item_max,
                    per_item_max,
                )

            if current_length + len(content) > max_length:
                logger.debug(
                    "Reached max context length (%d chars), stopping at %d results",
                    max_length,
                    len(context_parts),
                )
                break
            context_parts.append(content)
            current_length += len(content) + 2

        result = "\n\n".join(context_parts)
        logger.debug(
            "Tool search_genealogy_database returned %d results (%d chars) for query: %r",
            len(context_parts),
            len(result),
            query,
        )
        return result

    except Exception as e:  # pylint: disable=broad-except
        logger.error("Error searching genealogy database: %s", e)
        return f"Error searching the database: {str(e)}"


@log_tool_call
def filter_people(
    ctx: RunContext[AgentDeps],
    given_name: str = "",
    surname: str = "",
    birth_year_before: str = "",
    birth_year_after: str = "",
    birth_place: str = "",
    death_year_before: str = "",
    death_year_after: str = "",
    death_place: str = "",
    ancestor_of: str = "",
    ancestor_generations: int = 10,
    descendant_of: str = "",
    descendant_generations: int = 10,
    is_male: bool = False,
    is_female: bool = False,
    probably_alive_on_date: str = "",
    has_common_ancestor_with: str = "",
    degrees_of_separation_from: str = "",
    degrees_of_separation: int = 2,
    combine_filters: str = "and",
    max_results: int = 50,
    show_relation_with: str = "",
) -> str:
    """Filters people in the family tree based on simple criteria.

    IMPORTANT: When filtering by relationships (ancestor_of, descendant_of, degrees_of_separation_from),
    ALWAYS set show_relation_with to the same Gramps ID to get relationship labels in results.
    Without it, you cannot determine specific relationships like "grandfather" vs "father".

    Args:
        given_name: Given/first name to search for (partial match)
        surname: Surname/last name to search for (partial match)
        birth_year_before: Year before which people were born (e.g., "1900"). Use only the year.
        birth_year_after: Year after which people were born (e.g., "1850"). Use only the year.
        birth_place: Place name where person was born (partial match)
        death_year_before: Year before which people died (e.g., "1950"). Use only the year.
        death_year_after: Year after which people died (e.g., "1800"). Use only the year.
        death_place: Place name where person died (partial match)
        ancestor_of: Gramps ID of person to find ancestors of (e.g., "I0044")
        ancestor_generations: Maximum generations to search for ancestors (default: 10)
        descendant_of: Gramps ID of person to find descendants of (e.g., "I0044")
        descendant_generations: Maximum generations to search for descendants (default: 10)
        is_male: Filter to only males (True/False)
        is_female: Filter to only females (True/False)
        probably_alive_on_date: Date to check if person was likely alive (YYYY-MM-DD)
        has_common_ancestor_with: Gramps ID to find people sharing an ancestor (e.g., "I0044")
        degrees_of_separation_from: Gramps ID of person to find relatives connected to (e.g., "I0044")
        degrees_of_separation: Maximum relationship path length (default: 2). Each parent-child
            or spousal connection counts as 1. Examples: sibling=2, grandparent=2, uncle=3,
            first cousin=4, brother-in-law=2
        combine_filters: How to combine multiple filters: "and" (default) or "or"
        max_results: Maximum results to return (default: 50, max: 100)
        show_relation_with: Gramps ID of person to show relationships relative to (e.g., "I0044").
            When set, each result will include the relationship to this anchor person.

    Returns:
        Formatted list of people matching the filter criteria.

    Examples:
        - Find people with surname Smith: surname="Smith"
        - Find people born before 1900: birth_year_before="1900"
        - Find people born between 1850-1900: birth_year_after="1850", birth_year_before="1900"
        - Find who was alive in 1880: probably_alive_on_date="1880-01-01"
        - Find cousins: has_common_ancestor_with="I0044"
        - Find someone's parents (with labels): ancestor_of="I0044", ancestor_generations=1, show_relation_with="I0044"
        - Find someone's grandfathers (with labels): ancestor_of="I0044", ancestor_generations=2, is_male=True, show_relation_with="I0044"
        - Find siblings (with labels): degrees_of_separation_from="I0044", degrees_of_separation=2, show_relation_with="I0044"
        - Find extended family (uncles, aunts): degrees_of_separation_from="I0044", degrees_of_separation=3
    """
    logger = get_logger()

    max_results = min(max(1, max_results), 100)

    rules: list[dict[str, Any]] = []

    if given_name or surname:
        rules.append(
            {
                "name": "HasNameOf",
                "values": [given_name, surname, "", "", "", "", "", "", "", "", ""],
            }
        )

    if birth_year_before or birth_year_after or birth_place:
        date_expr = _build_date_expression(birth_year_before, birth_year_after)
        rules.append({"name": "HasBirth", "values": [date_expr, birth_place, ""]})

    if death_year_before or death_year_after or death_place:
        date_expr = _build_date_expression(death_year_before, death_year_after)
        rules.append({"name": "HasDeath", "values": [date_expr, death_place, ""]})

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

    if is_male:
        rules.append({"name": "IsMale", "values": []})

    if is_female:
        rules.append({"name": "IsFemale", "values": []})

    if probably_alive_on_date:
        rules.append({"name": "ProbablyAlive", "values": [probably_alive_on_date]})

    if not rules:
        return (
            "No filter criteria provided. Please specify at least one filter parameter."
        )

    if combine_filters.lower() == "or":
        # For OR logic, we need to update the filter_dict in _apply_gramps_filter
        # Pass it as part of the rules structure
        filter_dict: dict[str, Any] = {"rules": rules, "function": "or"}
        filter_rules = json.dumps(filter_dict)
        logger.debug("Built filter rules: %s", filter_rules)

        db_handle = None
        try:
            db_handle = get_db_outside_request(
                tree=ctx.deps.tree,
                view_private=ctx.deps.include_private,
                readonly=True,
                user_id=ctx.deps.user_id,
            )

            args = {"rules": filter_rules}
            try:
                matching_handles = apply_filter(
                    db_handle=db_handle,
                    args=args,
                    namespace="Person",
                    handles=None,
                )
            except Exception as filter_error:
                logger.error(
                    "Filter validation failed: %s. Filter rules: %r",
                    filter_error,
                    filter_rules,
                )
                db_handle.close()
                raise

            if not matching_handles:
                db_handle.close()
                return "No people found matching the filter criteria."

            matching_handles = matching_handles[:max_results]

            context_parts: list[str] = []
            max_length = ctx.deps.max_context_length
            per_item_max = 10000  # Maximum chars per individual item
            current_length = 0

            # Get the anchor person for relationship calculation if requested
            anchor_person = None
            if show_relation_with:
                try:
                    anchor_person = db_handle.get_person_from_gramps_id(
                        show_relation_with
                    )
                    if not anchor_person:
                        logger.warning(
                            "Anchor person %s not found for relationship calculation",
                            show_relation_with,
                        )
                except Exception as e:  # pylint: disable=broad-except
                    logger.warning(
                        "Error fetching anchor person %s: %s", show_relation_with, e
                    )

            for handle in matching_handles:
                try:
                    person = db_handle.get_person_from_handle(handle)

                    if not ctx.deps.include_private and person.private:
                        continue

                    obj_dict = obj_strings_from_object(
                        db_handle=db_handle,
                        class_name="Person",
                        obj=person,
                        semantic=True,
                    )

                    if obj_dict:
                        content = (
                            obj_dict["string_all"]
                            if ctx.deps.include_private
                            else obj_dict["string_public"]
                        )

                        # Add relationship prefix if anchor person is set
                        if anchor_person:
                            rel_prefix = _get_relationship_prefix(
                                db_handle, anchor_person, person, logger
                            )
                            content = rel_prefix + content

                        # Truncate individual items if they're too long
                        if len(content) > per_item_max:
                            content = (
                                content[:per_item_max]
                                + "\n\n[Content truncated due to length...]"
                            )
                            logger.debug(
                                "Truncated Person content from %d to %d chars",
                                len(content) - per_item_max,
                                per_item_max,
                            )

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
                    logger.warning("Error processing person %s: %s", handle, e)
                    continue

            if not context_parts:
                db_handle.close()
                return "No people found matching the filter criteria (or all results are private)."

            result = "\n\n".join(context_parts)

            total_matches = len(matching_handles)
            returned_count = len(context_parts)

            if returned_count < total_matches:
                result += f"\n\n---\nShowing {returned_count} of {total_matches} matching people. Use max_results parameter to see more."
            elif total_matches == max_results:
                result += f"\n\n---\nShowing {returned_count} people (limit reached). There may be more matches."

            logger.debug(
                "Tool filter_people returned %d results (%d chars)",
                len(context_parts),
                len(result),
            )

            db_handle.close()

            return result

        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error filtering people: %s", e)
            if db_handle is not None:
                try:
                    db_handle.close()
                except Exception:  # pylint: disable=broad-except
                    pass
            return f"Error filtering people: {str(e)}"

    # Use the common filter helper for AND logic
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
    event_type: str = "",
    date_before: str = "",
    date_after: str = "",
    place: str = "",
    description_contains: str = "",
    participant_id: str = "",
    participant_role: str = "",
    max_results: int = 50,
) -> str:
    """Filter events in the genealogy database.

    Use this tool to find events matching specific criteria. Events are occurrences in
    people's lives (births, deaths, marriages, etc.) or general historical events.

    Args:
        event_type: Type of event (e.g., "Birth", "Death", "Marriage", "Baptism",
            "Census", "Emigration", "Burial", "Occupation", "Residence")
        date_before: Latest year to include (inclusive). For "between 1892 and 1900", use "1900".
            Use only the year as a string.
        date_after: Earliest year to include (inclusive). For "between 1892 and 1900", use "1892".
            Use only the year as a string.
        place: Location name to search for (e.g., "Boston", "Massachusetts")
        description_contains: Text that should appear in the event description
        participant_id: Gramps ID of a person who participated in the event (e.g., "I0001")
        participant_role: Role of the participant if participant_id is provided
            (e.g., "Primary", "Family")
        max_results: Maximum number of results to return (1-100, default 50)

    Returns:
        A formatted string containing matching events with their details, or an error message.

    Examples:
        - "births in 1850": filter_events(event_type="Birth", date_after="1850", date_before="1850")
        - "marriages in Boston": filter_events(event_type="Marriage", place="Boston")
        - "events between 1892 and 1900": filter_events(date_after="1892", date_before="1900")
        - "events after 1850": filter_events(date_after="1850")
        - "events before 1900": filter_events(date_before="1900")
        - "events for person I0044": filter_events(participant_id="I0044")
    """
    max_results = min(max(1, max_results), 100)

    rules: list[dict[str, Any]] = []

    if event_type or date_before or date_after or place or description_contains:
        date_expr = _build_date_expression(before=date_before, after=date_after)
        rules.append(
            {
                "name": "HasData",
                "values": [
                    event_type or "",
                    date_expr,
                    place or "",
                    description_contains or "",
                ],
            }
        )

    if participant_id:
        person_filter_rules = [{"name": "HasIdOf", "values": [participant_id]}]
        person_filter_json = json.dumps({"rules": person_filter_rules})

        rules.append(
            {
                "name": "MatchesPersonFilter",
                "values": [person_filter_json, "1" if participant_role else "0"],
            }
        )

    if not rules:
        return (
            "No filter criteria provided. Please specify at least one filter parameter "
            "(event_type, date_before, date_after, place, description_contains, or participant_id)."
        )

    # Use the common filter helper
    return _apply_gramps_filter(
        ctx=ctx,
        namespace="Event",
        rules=rules,
        max_results=max_results,
        empty_message="No events found matching the filter criteria.",
    )
