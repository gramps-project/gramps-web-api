#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2025-2026 David Straub
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

"""Gramps filter interface."""

import inspect
import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import gramps.gen.filters as filters
from flask import Response, abort, current_app
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import Media, Person
from marshmallow import Schema
from webargs import ValidationError, fields, validate

from ...auth.const import PERM_EDIT_CUSTOM_FILTER
from ...const import GRAMPS_NAMESPACES, TREE_MULTI
from ...types import Handle
from ..blueprint import api_blueprint
from ..util import abort_with_message
from ..auth import require_permissions
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .schemas import (
    CustomFilterSchema as CustomFilterResponseSchema,
    NamespaceFiltersSchema,
)


class HasAssociationType(Rule):
    """Rule that checks for a person with an association of a given type."""

    labels = ["Type:"]
    name = "People with association of type <type>"
    description = "Matches people with a certain association type"
    category = "General filters"

    def apply_to_one(self, db: DbReadBase, person: Person) -> bool:  # type: ignore
        for person_ref in person.get_person_ref_list():
            if person_ref.get_relation() == self.list[0]:
                return True
        return False


class IsReferencedByObjectType(Rule):
    """Rule that checks if a media object is referenced by a given object type."""

    labels = ["Type:"]
    name = "Media referenced by <type>"
    description = "Matches media objects referenced by a specific object type"
    category = "General filters"

    def apply_to_one(self, db: DbReadBase, media: Media) -> bool:  # type: ignore
        object_type = self.list[0]
        for class_name, _ in db.find_backlink_handles(media.handle):
            if class_name == object_type:
                return True
        return False


MAX_FILTER_DEPTH = 5

_NAMESPACE_MODULES = {
    "Person": filters.rules.person,
    "Family": filters.rules.family,
    "Event": filters.rules.event,
    "Place": filters.rules.place,
    "Citation": filters.rules.citation,
    "Source": filters.rules.source,
    "Repository": filters.rules.repository,
    "Media": filters.rules.media,
    "Note": filters.rules.note,
}

_ADDITIONAL_RULES: dict[str, list[type[Rule]]] = {
    "Person": [HasAssociationType],
    "Media": [IsReferencedByObjectType],
}

_RULE_CLASS_CACHE: dict[str, dict[str, type[Rule]]] = {}

# Maps (parent_namespace, sub_namespace) to a function (db, obj) -> [sub_handle, ...]
_NAMESPACE_BRIDGES: dict[tuple[str, str], Callable] = {
    ("Event", "Place"): lambda db, obj: [obj.place] if obj.place else [],
    ("Person", "Event"): lambda db, obj: [ref.ref for ref in obj.get_event_ref_list()],
    ("Person", "Family"): lambda db, obj: (
        obj.get_family_handle_list() + obj.get_parent_family_handle_list()
    ),
    ("Family", "Event"): lambda db, obj: [ref.ref for ref in obj.get_event_ref_list()],
    ("Family", "Person"): lambda db, obj: (
        ([obj.get_father_handle()] if obj.get_father_handle() else [])
        + ([obj.get_mother_handle()] if obj.get_mother_handle() else [])
        + [ref.ref for ref in obj.get_child_ref_list()]
    ),
    ("Citation", "Source"): lambda db, obj: (
        [obj.get_reference_handle()] if obj.get_reference_handle() else []
    ),
    ("Source", "Repository"): lambda db, obj: [
        ref.ref for ref in obj.get_reporef_list()
    ],
}


def get_rule_map(namespace: str) -> dict[str, type[Rule]]:
    """Return a class-name → class mapping for all available rules in a namespace."""
    if namespace not in _RULE_CLASS_CACHE:
        mod = _NAMESPACE_MODULES.get(namespace)
        if mod is None:
            _RULE_CLASS_CACHE[namespace] = {}
        else:
            seen: set[str] = set()
            result: dict[str, type[Rule]] = {}
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if (
                    cls is not Rule
                    and issubclass(cls, Rule)
                    and hasattr(cls, "name")
                    and cls.name  # type: ignore[union-attr]
                    and cls.__name__ not in seen
                ):
                    result[cls.__name__] = cls
                    seen.add(cls.__name__)
            for additional_cls in _ADDITIONAL_RULES.get(namespace, []):
                if additional_cls.__name__ not in seen:
                    result[additional_cls.__name__] = additional_cls
                    seen.add(additional_cls.__name__)
            _RULE_CLASS_CACHE[namespace] = result
    return _RULE_CLASS_CACHE[namespace]


def get_rule_list(namespace: str) -> list[type[Rule]]:
    """Return all available rule classes for a namespace."""
    return list(get_rule_map(namespace).values())


def get_filter_rules(args: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    """Return a list of available filter rules for a namespace."""
    rule_list = []
    for rule_class in get_rule_list(namespace):
        if (
            "rules" in args
            and args["rules"]
            and rule_class.__name__ not in args["rules"]
        ):
            continue
        rule_list.append(
            {
                "category": rule_class.category,
                "description": rule_class.description,
                "labels": rule_class.labels,
                "name": rule_class.name,
                "rule": rule_class.__name__,
            }
        )
    if "rules" in args and len(args["rules"]) != len(rule_list):
        abort(404)
    return rule_list


def get_custom_filters(args: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    """Return a list of custom filters for a namespace."""
    filter_list = []
    filters.reload_custom_filters()
    for filter_class in filters.CustomFilters.get_filters(namespace):
        if (
            "filters" in args
            and args["filters"]
            and filter_class.get_name() not in args["filters"]
        ):
            continue
        filter_list.append(
            {
                "comment": filter_class.get_comment(),
                "function": filter_class.get_logical_op(),
                "invert": filter_class.invert,
                "name": filter_class.get_name(),
                "rules": [
                    {
                        "name": filter_rule.__class__.__name__,
                        "regex": filter_rule.use_regex,
                        "values": filter_rule.values(),
                    }
                    for filter_rule in filter_class.get_rules()
                ],
            }
        )
    if "filters" in args and len(args["filters"]) != len(filter_list):
        abort(404)
    return filter_list


def _build_rule_instance(rule_parms: dict[str, Any], namespace: str) -> Rule:
    """Instantiate a single rule from its parameter dict."""
    rule_class = get_rule_map(namespace).get(rule_parms["name"])
    if rule_class is None:
        abort(404)
    assert rule_class is not None
    return rule_class(
        rule_parms.get("values", []),
        use_regex=rule_parms.get("regex", False),
    )


def _apply_filter_parms(
    filter_parms: dict[str, Any],
    db_handle: DbReadBase,
    namespace: str,
    handles: list[Handle],
    depth: int = 0,
) -> list[Handle]:
    """Recursively evaluate a filter spec and return matching handles."""
    if depth >= MAX_FILTER_DEPTH:
        abort_with_message(400, "Filter nesting depth exceeded")

    function = filter_parms.get("function", "and")
    invert = filter_parms.get("invert", False)
    handle_set = set(handles)
    result_sets = []

    for item in filter_parms["rules"]:
        if "name" in item:
            single = filters.GenericFilterFactory(namespace)()
            single.add_rule(_build_rule_instance(item, namespace))
            result_sets.append(set(single.apply(db_handle, id_list=handles)))
        elif item.get("namespace", namespace) != namespace:
            sub_namespace = item["namespace"]
            bridge = _NAMESPACE_BRIDGES.get((namespace, sub_namespace))
            if bridge is None:
                abort_with_message(
                    400,
                    f"Unsupported namespace bridge: {namespace} → {sub_namespace}",
                )
            getter = getattr(db_handle, f"get_{namespace.lower()}_from_handle")
            sub_to_parents: dict[Handle, list[Handle]] = defaultdict(list)
            for handle in handles:
                obj = getter(handle)
                if obj is None:
                    continue
                for sub_handle in bridge(db_handle, obj):
                    sub_to_parents[sub_handle].append(handle)
            matching_sub = set(
                _apply_filter_parms(
                    item, db_handle, sub_namespace, list(sub_to_parents), depth + 1
                )
            )
            matched: set[Handle] = set()
            for sub_handle in matching_sub:
                matched.update(sub_to_parents[sub_handle])
            result_sets.append(matched)
        else:
            result_sets.append(
                set(_apply_filter_parms(item, db_handle, namespace, handles, depth + 1))
            )

    if not result_sets:
        combined = handle_set
    elif function == "and":
        combined = handle_set.intersection(*result_sets)
    elif function == "or":
        combined = set().union(*result_sets) & handle_set
    else:  # "one"
        combined = {h for h in handles if sum(1 for s in result_sets if h in s) == 1}

    if invert:
        combined = handle_set - combined

    return [h for h in handles if h in combined]


def build_filter(filter_parms: dict[str, Any], namespace: str) -> GenericFilter:
    """Build a flat GenericFilter for named custom filter persistence."""
    filter_object = filters.GenericFilterFactory(namespace)()
    if "name" in filter_parms:
        filter_object.set_name(filter_parms["name"])
    if "comment" in filter_parms:
        filter_object.set_comment(filter_parms["comment"])
    if "function" in filter_parms:
        filter_object.set_logical_op(filter_parms["function"])
    if "invert" in filter_parms:
        filter_object.set_invert(filter_parms["invert"])
    for rule_parms in filter_parms["rules"]:
        filter_object.add_rule(_build_rule_instance(rule_parms, namespace))
    return filter_object


def apply_filter(
    db_handle: DbReadBase,
    args: dict[str, Any],
    namespace: str,
    handles: list[Handle] | None = None,
) -> list[Handle]:
    """Apply an existing or dynamically defined filter."""
    filters.reload_custom_filters()
    if args.get("filter"):
        for filter_class in filters.CustomFilters.get_filters(namespace):
            if args["filter"] == filter_class.get_name():
                return filter_class.apply(db_handle, id_list=handles)
        abort(404)

    try:
        filter_parms = FilterSchema().load(json.loads(args["rules"]))
    except json.JSONDecodeError:
        abort_with_message(400, "Error decoding JSON")
    except ValidationError:
        abort_with_message(422, "Filter does not adhere to schema")

    if handles is None:
        query_method = db_handle.method("get_%s_handles", namespace)
        assert query_method is not None, f"No handle query for namespace '{namespace}'"
        handles = list(query_method())
    return _apply_filter_parms(filter_parms, db_handle, namespace, handles)


class RuleSchema(Schema):
    """Structure for a filter rule."""

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Rule class name (e.g. 'HasTag', 'MatchIdOf')."},
    )
    values = fields.List(
        fields.Raw,
        metadata={"description": "Parameter values for the rule."},
    )
    regex = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, treat text values as regular expressions."},
    )


class RuleOrFilterField(fields.Field):
    """Polymorphic field: deserializes as RuleSchema (has 'name') or nested FilterSchema (has 'rules')."""

    def _deserialize(self, value, attr, data, **kwargs):
        if not isinstance(value, dict):
            raise ValidationError("Expected a dict")
        if "name" in value:
            return RuleSchema().load(value)
        if "rules" in value:
            return FilterSchema().load(value)
        raise ValidationError("Must have 'name' (rule) or 'rules' (sub-filter)")

    def _serialize(self, value, attr, obj, **kwargs):
        return value


class FilterSchema(Schema):
    """Structure for a filter."""

    function = fields.Str(
        load_default="and",
        validate=validate.OneOf(["and", "or", "one"]),
        metadata={
            "description": "Logical operation applied across rules: 'and', 'or', or 'one'."
        },
    )
    invert = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, invert the filter result set."},
    )
    namespace = fields.Str(
        validate=validate.OneOf(list(GRAMPS_NAMESPACES.values())),
        metadata={
            "description": (
                "If set on a nested sub-filter, evaluate it in this namespace and "
                "bridge results back to the parent namespace. Supported bridges: "
                "Event→Place, Person→Event, Person→Family, Family→Event, "
                "Family→Person, Citation→Source, Source→Repository."
            )
        },
    )
    rules = fields.List(
        RuleOrFilterField(),
        required=True,
        validate=validate.Length(min=1),
        metadata={
            "description": "List of rule specs or nested filter specs to compose."
        },
    )


class CustomFilterCreateSchema(FilterSchema):
    """Structure for a custom filter (request body for create/update)."""

    name = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Unique name for this custom filter."},
    )
    comment = fields.Str(
        metadata={
            "description": "Optional comment describing the purpose of the filter."
        },
    )
    rules = fields.List(
        fields.Nested(RuleSchema),
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "List of rule specs."},
    )


class FiltersResources(ProtectedResource, GrampsJSONEncoder):
    """Filters resources."""

    @api_blueprint.response(200, NamespaceFiltersSchema())
    @api_blueprint.arguments(Schema(), location="query")
    def get(self, args: dict[str, Any]) -> Response:
        """Get available custom filters and rules."""
        results = {}
        for namespace in GRAMPS_NAMESPACES:
            rule_list = get_filter_rules(args, GRAMPS_NAMESPACES[namespace])
            filter_list = get_custom_filters(args, GRAMPS_NAMESPACES[namespace])
            results[namespace] = {"filters": filter_list, "rules": rule_list}
        return self.response(200, results)


class FiltersQueryArgs(Schema):
    """Query arguments for GET /filters/<namespace>/."""

    filters = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        metadata={
            "description": "Comma-delimited list of custom filter names to return."
        },
    )
    rules = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        metadata={"description": "Comma-delimited list of rule class names to return."},
    )


class FiltersResource(ProtectedResource, GrampsJSONEncoder):
    """Filters resource."""

    @api_blueprint.response(200, NamespaceFiltersSchema())
    @api_blueprint.arguments(FiltersQueryArgs, location="query")
    def get(self, args: dict[str, Any], namespace: str) -> Response:
        """Get available custom filters and rules."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        rule_list = get_filter_rules(args, namespace)
        if "rules" in args and "filters" not in args:
            return self.response(200, {"rules": rule_list})
        filter_list = get_custom_filters(args, namespace)
        if "filters" in args and "rules" not in args:
            return self.response(200, {"filters": filter_list})
        return self.response(200, {"filters": filter_list, "rules": rule_list})

    @api_blueprint.arguments(CustomFilterCreateSchema(), location="json")
    def post(self, args: dict[str, Any], namespace: str) -> Response:
        """Create a custom filter."""
        if current_app.config["TREE"] == TREE_MULTI:
            abort_with_message(
                405, "Custom filters cannot be edited in a multi-tree setup"
            )
        require_permissions([PERM_EDIT_CUSTOM_FILTER])
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        new_filter = build_filter(args, namespace)
        filters.reload_custom_filters()
        for filter_rule in filters.CustomFilters.get_filters(namespace):
            if new_filter.get_name() == filter_rule.get_name():
                abort(422)
        filters.CustomFilters.add(namespace, new_filter)
        filters.CustomFilters.save()
        return self.response(201, {"message": "Added filter: " + new_filter.get_name()})

    @api_blueprint.arguments(CustomFilterCreateSchema(), location="json")
    def put(self, args: dict[str, Any], namespace: str) -> Response:
        """Update a custom filter."""
        if current_app.config["TREE"] == TREE_MULTI:
            abort_with_message(
                405, "Custom filters cannot be edited in a multi-tree setup"
            )
        require_permissions([PERM_EDIT_CUSTOM_FILTER])
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        new_filter = build_filter(args, namespace)
        filters.reload_custom_filters()
        for filter_rule in filters.CustomFilters.get_filters(namespace):
            if new_filter.get_name() == filter_rule.get_name():
                filters.CustomFilters.get_filters(namespace).remove(filter_rule)
                filters.CustomFilters.add(namespace, new_filter)
                filters.CustomFilters.save()
                return self.response(
                    200, {"message": "Updated filter: " + new_filter.get_name()}
                )
        abort(404)


class FilterDeleteQueryArgs(Schema):
    """Query arguments for DELETE /filters/<namespace>/<name>/."""

    force = fields.Str(
        validate=validate.Length(equal=0),
        metadata={
            "description": "If present (empty string), force-delete the filter and any dependent filters."
        },
    )


class FilterResource(ProtectedResource, GrampsJSONEncoder):
    """Filter resource."""

    @api_blueprint.response(200, CustomFilterResponseSchema())
    def get(self, namespace: str, name: str) -> Response:
        """Get a custom filter."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        filter_list = get_custom_filters({"filters": [name]}, namespace)
        if not filter_list:
            abort(404)
        return self.response(200, filter_list[0])

    @api_blueprint.arguments(FilterDeleteQueryArgs, location="query")
    def delete(self, args: dict[str, Any], namespace: str, name: str) -> Response:
        """Delete a custom filter."""
        if current_app.config["TREE"] == TREE_MULTI:
            abort_with_message(
                405, "Custom filters cannot be edited in a multi-tree setup"
            )
        require_permissions([PERM_EDIT_CUSTOM_FILTER])
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        filters.reload_custom_filters()
        custom_filters = filters.CustomFilters.get_filters(namespace)
        for custom_filter in custom_filters:
            if name == custom_filter.get_name():
                filter_set: set[GenericFilter] = set()
                self._find_dependent_filters(namespace, custom_filter, filter_set)
                if len(filter_set) > 1:
                    if "force" not in args:
                        abort(405)
                for f in filter_set:
                    custom_filters.remove(f)
                filters.CustomFilters.save()
                return self.response(200, {"message": "Deleted filter: " + name})
        abort(404)

    def _find_dependent_filters(
        self,
        namespace: str,
        base_filter: GenericFilter,
        filter_set: set[GenericFilter],
    ) -> None:
        """Recursively collect base_filter and all filters that depend on it."""
        base_filter_name = base_filter.get_name()
        for custom_filter in filters.CustomFilters.get_filters(namespace):
            if custom_filter.get_name() == base_filter_name:
                continue
            for custom_filter_rule in custom_filter.get_rules():
                if base_filter_name in custom_filter_rule.values():
                    self._find_dependent_filters(namespace, custom_filter, filter_set)
                    break
        filter_set.add(base_filter)
