#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Gramps filter interface."""

import json
from typing import Any, Dict, List, Optional, Set

import gramps.gen.filters as filters
from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import Person
from marshmallow import Schema
from webargs import ValidationError, fields, validate

from ...const import GRAMPS_NAMESPACES
from ...types import Handle
from ..util import abort_with_message, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class HasAssociationType(Rule):
    """Rule that checks for a person with an association of a given type."""

    labels = ["Type:"]
    name = "People with association of type <type>"
    description = "Matches people with a certain association type"
    category = "General filters"

    def apply_to_one(self, db: DbReadBase, person: Person) -> bool:  # type: ignore
        """Apply the rule to the person."""
        for person_ref in person.get_person_ref_list():
            if person_ref.get_relation() == self.list[0]:
                return True
        return False


additional_person_rules = [HasAssociationType]


def get_rule_list(namespace: str) -> List[Rule]:
    """Return a list of available rules for a namespace."""
    return {
        "Person": filters.rules.person.editor_rule_list + additional_person_rules,
        "Family": filters.rules.family.editor_rule_list,
        "Event": filters.rules.event.editor_rule_list,
        "Place": filters.rules.place.editor_rule_list,
        "Citation": filters.rules.citation.editor_rule_list,
        "Source": filters.rules.source.editor_rule_list,
        "Repository": filters.rules.repository.editor_rule_list,
        "Media": filters.rules.media.editor_rule_list,
        "Note": filters.rules.note.editor_rule_list,
    }[namespace]


def get_filter_rules(args: Dict[str, Any], namespace: str) -> List[Dict]:
    """Return a list of available filter rules for a namespace."""
    rule_list = []
    for rule_class in get_rule_list(namespace):
        add_rule = True
        if "rules" in args and args["rules"]:
            if rule_class.__name__ not in args["rules"]:
                add_rule = False
        if add_rule:
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


def get_custom_filters(args: Dict[str, Any], namespace: str) -> List[Dict]:
    """Return a list of custom filters for a namespace."""
    filter_list = []
    filters.reload_custom_filters()
    for filter_class in filters.CustomFilters.get_filters(namespace):
        add_filter = True
        if "filters" in args and args["filters"]:
            if filter_class.get_name() not in args["filters"]:
                add_filter = False
        if add_filter:
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


def build_filter(filter_parms: Dict, namespace: str) -> GenericFilter:
    """Build and return a filter object."""
    filter_object = filters.GenericFilterFactory(namespace)()
    if "name" in filter_parms:
        filter_object.set_name(filter_parms["name"])
    if "comment" in filter_parms:
        filter_object.set_comment(filter_parms["comment"])
    if "function" in filter_parms:
        filter_object.set_logical_op(filter_parms["function"])
    if "invert" in filter_parms:
        filter_object.set_invert(filter_parms["invert"])
    for filter_rule in filter_parms["rules"]:
        rule_instance = None
        for rule_class in get_rule_list(namespace):
            if filter_rule["name"] == rule_class.__name__:
                rule_instance = rule_class
                break
        if rule_instance is None:
            abort(404)
        filter_args = []
        if "values" in filter_rule:
            filter_args = filter_rule["values"]
        filter_regex = False
        if "regex" in filter_rule:
            filter_regex = filter_rule["regex"]
        assert rule_instance is not None  # for mypy
        filter_object.add_rule(rule_instance(filter_args, use_regex=filter_regex))
    return filter_object


def apply_filter(
    db_handle: DbReadBase,
    args: Dict,
    namespace: str,
    handles: Optional[List[Handle]] = None,
) -> List[Handle]:
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

    filter_object = build_filter(filter_parms, namespace)
    return filter_object.apply(db_handle, id_list=handles)


class RuleSchema(Schema):
    """Structure for a filter rule."""

    name = fields.Str(required=True, validate=validate.Length(min=1))
    values = fields.List(fields.Raw, required=False)
    regex = fields.Boolean(required=False, load_default=False)


class FilterSchema(Schema):
    """Structure for a filter."""

    function = fields.Str(
        required=False,
        load_default="and",
        validate=validate.OneOf(["and", "or", "one"]),
    )
    invert = fields.Boolean(required=False, load_default=False)
    rules = fields.List(
        fields.Nested(RuleSchema), required=True, validate=validate.Length(min=1)
    )


class CustomFilterSchema(FilterSchema):
    """Structure for a custom filter."""

    name = fields.Str(required=True, validate=validate.Length(min=1))
    comment = fields.Str(required=False)
    rules = fields.List(
        fields.Nested(RuleSchema), required=True, validate=validate.Length(min=1)
    )


class FiltersResources(ProtectedResource, GrampsJSONEncoder):
    """Filters resources."""

    @use_args(
        {},
        location="query",
    )
    def get(self, args: Dict[str, str]) -> Response:
        """Get available custom filters and rules."""
        results = {}
        for namespace in GRAMPS_NAMESPACES:
            rule_list = get_filter_rules(args, GRAMPS_NAMESPACES[namespace])
            filter_list = get_custom_filters(args, GRAMPS_NAMESPACES[namespace])
            results[namespace] = {"filters": filter_list, "rules": rule_list}
        return self.response(200, results)


class FiltersResource(ProtectedResource, GrampsJSONEncoder):
    """Filters resource."""

    @use_args(
        {
            "filters": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "rules": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
        },
        location="query",
    )
    def get(self, args: Dict[str, str], namespace: str) -> Response:
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

    @use_args(CustomFilterSchema(), location="json")
    def post(self, args: Dict, namespace: str) -> Response:
        """Create a custom filter."""
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

    @use_args(CustomFilterSchema(), location="json")
    def put(self, args: Dict, namespace: str) -> Response:
        """Update a custom filter."""
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
        return abort(404)


class FilterResource(ProtectedResource, GrampsJSONEncoder):
    """Filter resource."""

    def get(self, namespace: str, name: str) -> Response:
        """Get a custom filter."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        args = {"filters": [name]}
        filter_list = get_custom_filters(args, namespace)
        if len(filter_list) == 0:
            abort(404)
        return self.response(200, filter_list[0])

    @use_args(
        {
            "force": fields.Str(validate=validate.Length(equal=0)),
        },
        location="query",
    )
    def delete(self, args: Dict, namespace: str, name: str) -> Response:
        """Delete a custom filter."""
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
                    if "force" not in args or not args["force"]:
                        abort(405)
                list(map(custom_filters.remove, filter_set))
                filters.CustomFilters.save()
                return self.response(200, {"message": "Deleted filter: " + name})
        return abort(404)

    def _find_dependent_filters(
        self, namespace: str, base_filter: GenericFilter, filter_set: Set[GenericFilter]
    ):
        """Recursively search for all dependent filters."""
        base_filter_name = base_filter.get_name()
        for custom_filter in filters.CustomFilters.get_filters(namespace):
            if custom_filter.get_name() == base_filter_name:
                continue
            for custom_filter_rule in custom_filter.get_rules():
                if base_filter_name in custom_filter_rule.values():
                    self._find_dependent_filters(namespace, custom_filter, filter_set)
                    break
        filter_set.add(base_filter)
