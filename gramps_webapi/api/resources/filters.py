"""Gramps filter interface."""

import json
from typing import Dict, List, Set

import gramps.gen.filters as filters
from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import GenericFilter
from marshmallow import Schema, ValidationError, fields
from webargs import validate
from webargs.flaskparser import use_args

from ...const import GRAMPS_NAMESPACES
from ...types import Handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder

_RULES_LOOKUP = {
    "Person": filters.rules.person.editor_rule_list,
    "Family": filters.rules.family.editor_rule_list,
    "Event": filters.rules.event.editor_rule_list,
    "Place": filters.rules.place.editor_rule_list,
    "Citation": filters.rules.citation.editor_rule_list,
    "Source": filters.rules.source.editor_rule_list,
    "Repository": filters.rules.repository.editor_rule_list,
    "Media": filters.rules.media.editor_rule_list,
    "Note": filters.rules.note.editor_rule_list,
}

# The dict used to define a filter is structured with either short or long keys for
# use in query parms or a post or put body as follows:
#
# {
#     "n": name,              # Filter name
#     "c": comment,           # Filter comment
#     "f": function,          # Logical operation: 'and', 'or', 'xor', or 'one'
#     "i": invert,            # Boolean indicator to invert result set, default False
#     "r": [                  # List of rules to apply as part of the filter
#         {
#             "n": name,      # Class name of the rule
#             "v": [],        # Values for the rule, default empty list
#             "r": regex      # Boolean indicator to treat as regex, default False
#         }
#     ]
# }

_FILTER_KEYS = {
    "short": {
        "comment": "c",
        "function": "f",
        "invert": "i",
        "name": "n",
        "rules": "r",
        "values": "v",
    },
    "long": {
        "comment": "comment",
        "function": "function",
        "invert": "invert",
        "name": "name",
        "rules": "rules",
        "values": "values",
    },
}


def build_filter(filter_parms: Dict, namespace: str, keys="short") -> GenericFilter:
    """Build and return a filter object."""
    key = _FILTER_KEYS[keys]
    filter_object = filters.GenericFilterFactory(namespace)()
    if key["name"] in filter_parms:
        filter_object.set_name(filter_parms[key["name"]])
    if key["comment"] in filter_parms:
        filter_object.set_comment(filter_parms[key["comment"]])
    if key["function"] in filter_parms:
        filter_object.set_logical_op(filter_parms[key["function"]])
    if key["invert"] in filter_parms:
        filter_object.set_invert(filter_parms[key["invert"]])
    for filter_rule in filter_parms[key["rules"]]:
        rule_instance = None
        for rule_class in _RULES_LOOKUP[namespace]:
            if filter_rule[key["name"]] == rule_class.__name__:
                rule_instance = rule_class
                break
        if rule_instance is None:
            abort(400)
        filter_args = []
        if key["values"] in filter_rule:
            filter_args = filter_rule[key["values"]]
        filter_regex = False
        for rkey in ["r", "regex"]:
            if rkey in filter_rule:
                filter_regex = filter_rule[rkey]
        filter_object.add_rule(rule_instance(filter_args, use_regex=filter_regex))
        return filter_object


def apply_filter(db_handle: DbReadBase, args: Dict, namespace: str) -> List[Handle]:
    """Apply an existing or dynamically defined filter."""
    filters.reload_custom_filters()
    if args.get("filter"):
        for filter_class in filters.CustomFilters.get_filters(namespace):
            if args["filter"] == filter_class.get_name():
                return filter_class.apply(db_handle)
        abort(400)

    try:
        filter_parms = QueryFilterSchema().load(json.loads(args["filters"]))
    except json.JSONDecodeError:
        abort(400)
    except ValidationError:
        abort(400)

    filter_object = build_filter(filter_parms, namespace, keys="short")
    return filter_object.apply(db_handle)


class RuleSchema(Schema):
    """Structure for a rule."""

    name = fields.Str(required=True, validate=validate.Length(min=1))
    values = fields.List(fields.Raw, required=False)
    regex = fields.Boolean(required=False, missing=False)


class FilterSchema(Schema):
    """Structure for a filter."""

    name = fields.Str(required=True, validate=validate.Length(min=1))
    comment = fields.Str(required=False)
    function = fields.Str(
        required=False,
        missing="and",
        validate=validate.OneOf(["and", "or", "xor", "one"]),
    )
    invert = fields.Boolean(required=False, missing=False)
    rules = fields.List(fields.Nested(RuleSchema))


class QueryRuleSchema(Schema):
    """Structure for validating a rule embedded in query parms."""

    n = fields.Str(required=True, validate=validate.Length(min=1))
    v = fields.List(fields.Raw, required=False)
    r = fields.Boolean(required=False, missing=False)


class QueryFilterSchema(Schema):
    """Structure for validating a filter embedded in query parms."""

    f = fields.Str(
        required=False,
        missing="and",
        validate=validate.OneOf(["and", "or", "xor", "one"]),
    )
    i = fields.Boolean(required=False, missing=False)
    r = fields.List(fields.Nested(QueryRuleSchema))


class FilterResource(ProtectedResource, GrampsJSONEncoder):
    """Filter resource."""

    @use_args(
        {"filter": fields.Str(), "rule": fields.Str()},
        location="query",
    )
    def get(self, args: Dict, namespace: str) -> Response:
        """Get available custom filters and rules."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(400)

        rule_list = []
        for rule_class in _RULES_LOOKUP[namespace]:
            add_rule = True
            if args.get("rule") and args["rule"] != rule_class.__name__:
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
        if args.get("rule") and not args.get("filter"):
            return self.response(200, {"rules": rule_list})
        filter_list = []
        filters.reload_custom_filters()
        for filter_class in filters.CustomFilters.get_filters(namespace):
            add_filter = True
            if args.get("filter") and args["filter"] != filter_class.get_name():
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
        if args.get("filter") and not args.get("rule"):
            return self.response(200, {"filters": filter_list})
        return self.response(200, {"filters": filter_list, "rules": rule_list})

    @use_args(FilterSchema(), location="json")
    def post(self, args: Dict, namespace: str) -> Response:
        """Create a custom filter."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        new_filter = build_filter(args, namespace, keys="long")
        filters.reload_custom_filters()
        for filter_rule in filters.CustomFilters.get_filters(namespace):
            if new_filter.get_name() == filter_rule.get_name():
                abort(422)
        filters.CustomFilters.add(namespace, new_filter)
        filters.CustomFilters.save()
        return self.response(201, {"message": "Added filter: " + new_filter.get_name()})

    @use_args(FilterSchema(), location="json")
    def put(self, args: Dict, namespace: str) -> Response:
        """Update a custom filter."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        new_filter = build_filter(args, namespace, keys="long")
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

    @use_args(
        {
            "name": fields.Str(required=True),
            "force": fields.Boolean(required=False, missing=False),
        },
        location="json",
    )
    def delete(self, args: Dict, namespace: str) -> Response:
        """Delete a custom filter."""
        try:
            namespace = GRAMPS_NAMESPACES[namespace]
        except KeyError:
            abort(404)

        filters.reload_custom_filters()
        custom_filters = filters.CustomFilters.get_filters(namespace)
        for custom_filter in custom_filters:
            if args["name"] == custom_filter.get_name():
                filter_set: Set[GenericFilter] = set()
                self._find_dependent_filters(namespace, custom_filter, filter_set)
                if len(filter_set) > 1:
                    if "force" not in args or not args["force"]:
                        abort(405)
                list(map(custom_filters.remove, filter_set))
                filters.CustomFilters.save()
                return self.response(
                    200, {"message": "Deleted filter: " + args["name"]}
                )
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
