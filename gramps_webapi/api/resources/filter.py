"""Gramps filter functions."""

import inspect

from flask import abort, json
from gramps.gen.filters import GenericFilter


def list_filter_rules(lib):
    """Build and return a filter rule list."""
    class_list = [getattr(lib, k) for k, v in inspect.getmembers(lib, inspect.isclass)]
    result = []
    for rule_class in class_list:
        result.append(
            {
                "rule": rule_class.__name__,
                "name": rule_class.name,
                "description": rule_class.description,
                "labels": rule_class.labels,
            }
        )
    return result


def apply_filter_rules(db, args, lib):
    """Build and apply a filter."""
    filter_object = GenericFilter()
    if "logic" in args:
        filter_object.set_logical_op(args["logic"])
    if "invert" in args:
        filter_object.set_invert(args["invert"])
    filter_rules = args["filter"]
    if isinstance(filter_rules, str):
        filter_rules = json.loads(filter_rules)

    class_list = [k for k, v in inspect.getmembers(lib, inspect.isclass)]
    for rule in filter_rules:
        if rule not in class_list:
            abort(404)
        rule_instance = getattr(lib, rule)
        if rule_instance is None:
            abort(404)
        filter_object.add_rule(rule_instance(filter_rules[rule]))
    return filter_object.apply(db)
