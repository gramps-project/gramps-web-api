#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Douglas Blank
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

"""Tests for the "almost Python" expression parser (`gramps_webapi.api.query_lang`)."""

import pytest

from gramps_webapi.api.query_lang import QueryLangError, parse_expr, resolve_namespace
from gramps_webapi.api.query import PERSON, FAMILY


# --- namespace resolution -----------------------------------------------------


def test_resolve_namespace_full_name():
    assert resolve_namespace("person") is PERSON


def test_resolve_namespace_single_letter_alias():
    assert resolve_namespace("F") is FAMILY


def test_resolve_namespace_unknown_raises():
    with pytest.raises(QueryLangError):
        resolve_namespace("bogus")


def test_resolve_namespace_person_has_no_single_letter_alias():
    # Deliberately unassigned -- conflicts with Gramps' own gramps_id
    # convention (P = Place, I = Person). Use "person" until this is settled.
    with pytest.raises(QueryLangError):
        resolve_namespace("P")


# --- plain-column vs JsonPath resolution --------------------------------------


def test_single_segment_matching_flat_column_becomes_plain_string():
    assert parse_expr("person", "gender == 1") == [
        {"column": "gender", "op": "eq", "value": 1}
    ]


def test_multi_segment_path_becomes_json_path():
    result = parse_expr("person", "primary_name.first_name == 'John'")
    assert result == [
        {
            "column": {"json_path": ["primary_name", "first_name"]},
            "op": "eq",
            "value": "John",
        }
    ]


def test_single_segment_not_matching_flat_column_becomes_json_path():
    # "birth_year" isn't a real flat column on PERSON -- falls back to
    # json_path even though it's a single segment.
    result = parse_expr("person", "birth_year == 1900")
    assert result == [
        {"column": {"json_path": ["birth_year"]}, "op": "eq", "value": 1900}
    ]


def test_integer_subscript_becomes_int_segment():
    result = parse_expr("person", "primary_name.surname_list[0].surname == 'Smith'")
    assert result == [
        {
            "column": {
                "json_path": ["primary_name", "surname_list", 0, "surname"]
            },
            "op": "eq",
            "value": "Smith",
        }
    ]


# --- comparison operators ------------------------------------------------------


@pytest.mark.parametrize(
    "op_src,op_json",
    [
        ("==", "eq"),
        ("!=", "ne"),
        ("<", "lt"),
        ("<=", "lte"),
        (">", "gt"),
        (">=", "gte"),
    ],
)
def test_all_comparison_operators(op_src, op_json):
    result = parse_expr("person", f"gender {op_src} 1")
    assert result == [{"column": "gender", "op": op_json, "value": 1}]


def test_in_operator():
    result = parse_expr("person", "gender in [1, 2]")
    assert result == [{"column": "gender", "op": "in", "value": [1, 2]}]


def test_in_operator_requires_nonempty_list():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender in []")


def test_in_operator_rejects_non_list_rhs():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender in (1, 2)")  # tuple, not list


def test_like_call():
    result = parse_expr("person", "like(primary_name.first_name, 'Jo%')")
    assert result == [
        {
            "column": {"json_path": ["primary_name", "first_name"]},
            "op": "like",
            "value": "Jo%",
        }
    ]


def test_like_call_wrong_arity_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "like(gender)")


def test_like_call_non_string_pattern_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "like(gender, 5)")


# --- literals --------------------------------------------------------------------


def test_string_int_float_bool_literals():
    assert parse_expr("person", "gender == True") == [
        {"column": "gender", "op": "eq", "value": True}
    ]
    assert parse_expr("person", "gender == 1.5") == [
        {"column": "gender", "op": "eq", "value": 1.5}
    ]
    assert parse_expr("person", "gender == None") == [
        {"column": "gender", "op": "eq", "value": None}
    ]


def test_negative_number_literal():
    result = parse_expr("family", "some_field == -5")
    assert result[0]["value"] == -5


def test_unary_minus_on_non_numeric_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender == -'x'")


# --- conjunction (and) -----------------------------------------------------------


def test_and_conjunction_produces_multiple_conditions():
    result = parse_expr("person", "gender == 1 and primary_name.first_name == 'John'")
    assert result == [
        {"column": "gender", "op": "eq", "value": 1},
        {
            "column": {"json_path": ["primary_name", "first_name"]},
            "op": "eq",
            "value": "John",
        },
    ]


def test_and_conjunction_of_three():
    result = parse_expr("person", "gender == 1 and gender != 2 and gender < 3")
    assert len(result) == 3


# --- explicitly rejected: things with no wire-format equivalent yet -------------


def test_or_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender == 1 or gender == 2")


def test_not_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "not (gender == 1)")


def test_not_in_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender not in [1, 2]")


def test_is_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender is None")


def test_chained_comparison_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "1 < gender < 3")


def test_bare_name_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender")


def test_syntax_error_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "gender == 1 +")


# --- safety: arbitrary code must never be reachable ------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('ls')",
        "foo(gender, 1)",  # arbitrary function call, not the whitelisted `like`
        "lambda x: x",
        "[x for x in range(10)]",
        "{x: x for x in range(10)}",
        "(yield 1)",
        "gender if True else 1",
        "f'{gender}'",
    ],
)
def test_unsupported_node_shapes_rejected(expr):
    with pytest.raises(QueryLangError):
        parse_expr("person", expr)


def test_subscript_with_non_constant_index_rejected():
    with pytest.raises(QueryLangError):
        parse_expr("person", "primary_name.surname_list[i].surname == 'Smith'")


def test_subscript_with_bool_index_rejected():
    # bool is an int subclass -- explicitly excluded, matching JsonPath's own
    # segment validation in query.py.
    with pytest.raises(QueryLangError):
        parse_expr("person", "primary_name.surname_list[True].surname == 'Smith'")
