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

"""Pure unit tests for `object_query.py`'s request-parsing helpers.

Deliberately independent of the Flask app / test client -- these are plain
functions with no app-context dependency, and the shared endpoint test app
fixture (`tests/test_endpoints/__init__.py`) pulls in a sentence-transformers
model load that's broken in some local dev environments (unrelated to this
module). Full request/response wiring is still covered by
`tests/test_endpoints/test_people_query.py` and `test_object_query.py`.
"""

import pytest
from gramps.plugins.db.dbapi.sqlite import SQLite
from werkzeug.exceptions import HTTPException

from gramps_object_query_language.query import (
    FAMILY,
    PERSON,
    And,
    CollectionCount,
    Dialect,
    Eq,
    Exists,
    FlatColumnRef,
    Gt,
    JsonPath,
    Not,
    Or,
    OrderBy,
    QueryError,
    RelatedObject,
    resolve_column_path,
)
from gramps_object_query_language.query_lang import VALID_LEAF_OPS
from gramps_webapi.api.resources.object_query import (
    QueryWhereConditionArgs,
    _build_where,
    _check_no_duplicate_keys,
    _default_key_for,
    _normalize_json_value,
    _parse_column_ref,
    _parse_select_entry,
    _resolve_after,
    _resolve_dialect,
    _resolve_treeid,
    _resolve_where_conditions,
    _terminal_is_json_path,
)


# --- _parse_column_ref -------------------------------------------------------


def test_parse_column_ref_plain_string():
    assert _parse_column_ref("gramps_id", PERSON) == "gramps_id"


def test_parse_column_ref_json_path():
    ref = _parse_column_ref({"json_path": ["primary_name", "first_name"]}, PERSON)
    assert ref == JsonPath(("primary_name", "first_name"))


def test_parse_column_ref_relationship_crossing_path():
    ref = _parse_column_ref({"json_path": ["birth", "date", "sortval"]}, PERSON)
    assert ref == resolve_column_path(PERSON, ["birth", "date", "sortval"])
    assert isinstance(ref, RelatedObject)


def test_parse_column_ref_family_father_surname():
    ref = _parse_column_ref({"json_path": ["father", "surname"]}, FAMILY)
    assert ref == resolve_column_path(FAMILY, ["father", "surname"])


def test_parse_column_ref_rejects_non_str_non_dict():
    with pytest.raises(QueryError):
        _parse_column_ref(123, PERSON)


def test_parse_column_ref_rejects_dict_without_json_path_key():
    with pytest.raises(QueryError):
        _parse_column_ref({"column": "gramps_id"}, PERSON)


def test_parse_column_ref_rejects_non_list_json_path():
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": "primary_name.first_name"}, PERSON)


def test_parse_column_ref_rejects_empty_json_path():
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": []}, PERSON)


def test_parse_column_ref_rejects_bad_segment_type():
    # Bubbles up from JsonPath.__post_init__ -- bool disguised as int, float,
    # None, nested list, etc. are all rejected there.
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": ["primary_name", True]}, PERSON)
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": ["primary_name", 1.5]}, PERSON)


def test_parse_column_ref_rejects_bare_relationship_name():
    # "birth" alone isn't a value -- needs a further path (resolve_column_path).
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": ["birth"]}, PERSON)


def test_parse_column_ref_count_of():
    # count(events) > 2's column side -- previously only reachable via
    # where_expr (which bypasses _parse_column_ref entirely); this is the
    # regression test for that gap.
    ref = _parse_column_ref({"count_of": {"relationship": "events"}}, PERSON)
    assert isinstance(ref, CollectionCount)
    assert ref.collection.name == "events"
    assert ref.condition is None


def test_parse_column_ref_count_of_with_where():
    ref = _parse_column_ref(
        {
            "count_of": {
                "relationship": "events",
                "where": [{"column": {"json_path": ["type", "value"]}, "op": "eq", "value": 12}],
            }
        },
        PERSON,
    )
    assert isinstance(ref, CollectionCount)
    assert isinstance(ref.condition, Eq)


def test_parse_column_ref_rejects_count_of_missing_relationship():
    with pytest.raises(QueryError):
        _parse_column_ref({"count_of": {}}, PERSON)


def test_parse_column_ref_rejects_count_of_non_list_where():
    with pytest.raises(QueryError):
        _parse_column_ref(
            {"count_of": {"relationship": "events", "where": "not-a-list"}}, PERSON
        )


def test_parse_column_ref_rejects_count_of_malformed_nested_leaf():
    # The same value/value_column XOR check a top-level `where` leaf gets --
    # count_of's nested `where` is just as untrusted (select/order_by have
    # no schema shape at all), so it needs the same guard.
    with pytest.raises(HTTPException):
        _parse_column_ref(
            {
                "count_of": {
                    "relationship": "events",
                    "where": [{"column": "gramps_id", "op": "eq"}],
                }
            },
            PERSON,
        )


# --- _default_key_for -----------------------------------------------------------


def test_default_key_for_plain_string():
    assert _default_key_for("gramps_id") == "gramps_id"


def test_default_key_for_json_path_str_segments():
    path = JsonPath(("primary_name", "first_name"))
    assert _default_key_for(path) == "primary_name.first_name"


def test_default_key_for_json_path_with_int_segment():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert _default_key_for(path) == "primary_name.surname_list[0].surname"


def test_default_key_for_json_path_leading_int_segment():
    path = JsonPath((0, "value"))
    assert _default_key_for(path) == "[0].value"


def test_default_key_for_json_path_single_segment():
    assert _default_key_for(JsonPath(("gender",))) == "gender"


def test_default_key_for_related_object():
    ref = resolve_column_path(PERSON, ["birth", "date", "sortval"])
    assert _default_key_for(ref) == "birth.date.sortval"


def test_default_key_for_two_hop_related_object():
    ref = resolve_column_path(PERSON, ["birth", "place", "title"])
    assert _default_key_for(ref) == "birth.place.title"


def test_default_key_for_related_object_plain_field():
    ref = resolve_column_path(FAMILY, ["father", "surname"])
    assert _default_key_for(ref) == "father.surname"


# --- _parse_select_entry -------------------------------------------------------


def test_parse_select_entry_plain_string():
    assert _parse_select_entry("surname", PERSON) == ("surname", "surname")


def test_parse_select_entry_json_path_without_alias_uses_derived_key():
    ref, key = _parse_select_entry(
        {"json_path": ["primary_name", "surname_list", 0, "surname"]}, PERSON
    )
    assert ref == JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert key == "primary_name.surname_list[0].surname"


def test_parse_select_entry_json_path_with_alias():
    ref, key = _parse_select_entry(
        {"json_path": ["primary_name", "first_name"], "as": "first"}, PERSON
    )
    assert ref == JsonPath(("primary_name", "first_name"))
    assert key == "first"


def test_parse_select_entry_rejects_handle_alias_on_json_path():
    # The response's "handle" key is load-bearing for next_after -- letting a
    # client shadow it with unrelated JSON content would corrupt pagination
    # silently.
    with pytest.raises(QueryError):
        _parse_select_entry(
            {"json_path": ["primary_name", "first_name"], "as": "handle"}, PERSON
        )


def test_parse_select_entry_plain_handle_column_is_fine():
    assert _parse_select_entry("handle", PERSON) == ("handle", "handle")


def test_parse_select_entry_rejects_invalid_shape():
    with pytest.raises(QueryError):
        _parse_select_entry(123, PERSON)


def test_parse_select_entry_count_of_with_alias():
    ref, key = _parse_select_entry(
        {"count_of": {"relationship": "events"}, "as": "event_count"}, PERSON
    )
    assert isinstance(ref, CollectionCount)
    assert key == "event_count"


def test_parse_select_entry_count_of_requires_alias():
    # Unlike json_path, there's no natural dotted-name default to derive.
    with pytest.raises(QueryError):
        _parse_select_entry({"count_of": {"relationship": "events"}}, PERSON)


def test_parse_select_entry_count_of_rejects_handle_alias():
    with pytest.raises(QueryError):
        _parse_select_entry(
            {"count_of": {"relationship": "events"}, "as": "handle"}, PERSON
        )


def test_parse_select_entry_relationship_crossing_default_key():
    ref, key = _parse_select_entry({"json_path": ["birth", "date"]}, PERSON)
    assert isinstance(ref, RelatedObject)
    assert key == "birth.date"


def test_parse_select_entry_relationship_crossing_with_alias():
    ref, key = _parse_select_entry(
        {"json_path": ["father", "surname"], "as": "father_surname"}, FAMILY
    )
    assert key == "father_surname"


# --- _check_no_duplicate_keys --------------------------------------------------


def test_check_no_duplicate_keys_passes_for_unique_keys():
    _check_no_duplicate_keys([("a", "a"), ("b", "b")])  # no raise


def test_check_no_duplicate_keys_rejects_duplicate():
    path_a = JsonPath(("x",))
    path_b = JsonPath(("y",))
    with pytest.raises(QueryError):
        _check_no_duplicate_keys([(path_a, "same"), (path_b, "same")])


# --- _terminal_is_json_path / _normalize_json_value -----------------------------


def test_terminal_is_json_path_plain_string_false():
    assert _terminal_is_json_path("surname") is False


def test_terminal_is_json_path_json_path_true():
    assert _terminal_is_json_path(JsonPath(("primary_name", "first_name"))) is True


def test_terminal_is_json_path_related_object_plain_field_false():
    # father.surname ends in a real flat column -- no JSON functions
    # involved at all, so no normalization needed.
    ref = resolve_column_path(FAMILY, ["father", "surname"])
    assert _terminal_is_json_path(ref) is False


def test_terminal_is_json_path_related_object_json_path_field_true():
    ref = resolve_column_path(PERSON, ["birth", "date"])
    assert _terminal_is_json_path(ref) is True


def test_terminal_is_json_path_chained_related_object():
    # birth.place.title: the chain's own leaf ("title") is a plain column,
    # even though an intermediate hop (birth -> Event) uses a JsonPath
    # internally for its handle_ref -- only the final `field` matters.
    ref = resolve_column_path(PERSON, ["birth", "place", "title"])
    assert _terminal_is_json_path(ref) is False


def test_normalize_json_value_parses_json_object_string():
    assert _normalize_json_value('{"sortval": 2439857}') == {"sortval": 2439857}


def test_normalize_json_value_parses_json_number_string():
    # PostgreSQL's jsonb_extract_path_text always returns TEXT, even for a
    # scalar number -- confirmed live ('2439857', not a native int).
    assert _normalize_json_value("2439857") == 2439857


def test_normalize_json_value_passes_through_dict():
    # PostgreSQL's jsonb expressions can also come back through psycopg2
    # already parsed for some call shapes -- nothing to do in that case.
    value = {"sortval": 2439857}
    assert _normalize_json_value(value) is value


def test_normalize_json_value_passes_through_none():
    assert _normalize_json_value(None) is None


def test_normalize_json_value_passes_through_non_json_text():
    # A free-text value that happens not to be valid JSON (e.g. SQLite's
    # json_extract on a plain string field already de-quotes it) must not
    # raise -- returned unchanged.
    assert _normalize_json_value("About 1968") == "About 1968"


# --- _resolve_dialect -----------------------------------------------------------


class _FakeDbWithDialect:
    def __init__(self, dialect):
        self.dialect = dialect


class _FakeDbNoDialect:
    pass


def test_resolve_dialect_uses_explicit_attribute_when_present():
    assert _resolve_dialect(_FakeDbWithDialect("sqlite")) == Dialect.SQLITE
    assert _resolve_dialect(_FakeDbWithDialect("postgres")) == Dialect.POSTGRESQL
    assert _resolve_dialect(_FakeDbWithDialect("postgresql")) == Dialect.POSTGRESQL


def test_resolve_dialect_detects_real_sqlite_instance_without_dialect_attr():
    # No released Gramps core sets `.dialect` yet -- this is the fallback
    # that keeps every SQLite-backed test fixture and single-tree/dev
    # deployment from silently getting PostgreSQL-only SQL syntax.
    basedb = SQLite.__new__(SQLite)  # bypass __init__ -- isinstance is enough
    assert not hasattr(basedb, "dialect")
    assert _resolve_dialect(basedb) == Dialect.SQLITE


def test_resolve_dialect_falls_back_to_postgresql_for_unknown_backend():
    assert _resolve_dialect(_FakeDbNoDialect()) == Dialect.POSTGRESQL


def test_resolve_dialect_ignores_unrecognized_explicit_dialect_name():
    # An unrecognized `.dialect` string falls through to the isinstance/
    # default fallback rather than raising -- resolution here never fails,
    # `compile_query` raises `QueryError` if the dialect actually turns out
    # to be unsupported when rendering a `JsonPath`.
    assert _resolve_dialect(_FakeDbWithDialect("mysql")) == Dialect.POSTGRESQL


# --- _resolve_treeid ------------------------------------------------------------
#
# SharedPostgreSQL stores every tree's rows in the same physical tables --
# `treeid` is the only thing that scopes a query to the caller's own tree.


class _FakeDbapiWithTreeid:
    treeid = 7


class _FakeBasedbWithTreeidDbapi:
    dbapi = _FakeDbapiWithTreeid()


class _FakeDbapiNoTreeid:
    pass


class _FakeBasedbNoTreeidDbapi:
    dbapi = _FakeDbapiNoTreeid()


def test_resolve_treeid_reads_dbapi_treeid_when_present():
    assert _resolve_treeid(_FakeBasedbWithTreeidDbapi()) == 7


def test_resolve_treeid_returns_none_for_single_tree_backend():
    # SQLite / single-user PostgreSQL have no `.dbapi.treeid` at all --
    # `None` means "omit the clause", not "unscoped is fine by default".
    assert _resolve_treeid(_FakeBasedbNoTreeidDbapi()) is None


# --- _resolve_after treeid scoping -----------------------------------------------


class _FakeAfterDbapi:
    def __init__(self, row):
        self._row = row
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._row


class _FakeAfterBasedb:
    def __init__(self, row):
        self.dbapi = _FakeAfterDbapi(row)


def test_resolve_after_omits_treeid_clause_by_default():
    basedb = _FakeAfterBasedb(row=("Smith", "h1"))
    _resolve_after(basedb, PERSON, [OrderBy("surname", "asc")], "h1", treeid=None)
    sql, params = basedb.dbapi.calls[0]
    assert "treeid" not in sql
    assert params == ["h1"]


def test_resolve_after_adds_treeid_clause_when_given():
    # Without this, a handle from another tree on a shared multi-tree
    # backend would resolve just as well -- leaking that row's sort-column
    # values (and confirming its existence) across tenants even though the
    # main paginated query stays properly scoped.
    basedb = _FakeAfterBasedb(row=("Smith", "h1"))
    _resolve_after(basedb, PERSON, [OrderBy("surname", "asc")], "h1", treeid=7)
    sql, params = basedb.dbapi.calls[0]
    assert "AND treeid = ?" in sql
    assert params == ["h1", 7]


# --- _resolve_where_conditions (where / where_expr mutual exclusivity) ----------


def test_resolve_where_conditions_plain_where_passthrough():
    conditions = [{"column": "gender", "op": "eq", "value": 1}]
    assert _resolve_where_conditions({"where": conditions}, PERSON) == conditions


def test_resolve_where_conditions_neither_given_returns_none():
    assert _resolve_where_conditions({}, PERSON) is None


def test_resolve_where_conditions_where_expr_parsed_against_spec():
    result = _resolve_where_conditions({"where_expr": "gender == 1"}, PERSON)
    assert result == [{"column": "gender", "op": "eq", "value": 1}]


def test_resolve_where_conditions_where_expr_json_path():
    result = _resolve_where_conditions(
        {"where_expr": "primary_name.surname_list[0].surname == 'Smith'"}, PERSON
    )
    assert result == [
        {
            "column": {"json_path": ["primary_name", "surname_list", 0, "surname"]},
            "op": "eq",
            "value": "Smith",
        }
    ]


def test_resolve_where_conditions_both_given_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_where_conditions(
            {"where": [{"column": "gender", "op": "eq", "value": 1}], "where_expr": "gender == 1"},
            PERSON,
        )
    assert exc_info.value.code == 422


def test_resolve_where_conditions_where_expr_or_group():
    # `or` (and `not`) compile to a nested {"or": [...]}/{"not": ...} node
    # rather than a QueryLangError -- see _build_where's "or"/"not" tests
    # below for what happens to this shape next.
    result = _resolve_where_conditions({"where_expr": "gender == 1 or gender == 2"}, PERSON)
    assert result == [
        {
            "or": [
                {"column": "gender", "op": "eq", "value": 1},
                {"column": "gender", "op": "eq", "value": 2},
            ]
        }
    ]


# --- _build_where: value / value_column (field-vs-field comparisons) -----------


def test_build_where_field_vs_field():
    conditions = [
        {
            "column": {"json_path": ["mother", "death", "date", "sortval"]},
            "op": "lt",
            "value_column": {"json_path": ["father", "death", "date", "sortval"]},
        }
    ]
    where = _build_where(conditions, FAMILY)
    assert where.column == resolve_column_path(
        FAMILY, ["mother", "death", "date", "sortval"]
    )
    assert where.value == resolve_column_path(
        FAMILY, ["father", "death", "date", "sortval"]
    )


def test_build_where_both_value_and_value_column_rejected():
    conditions = [
        {"column": "gramps_id", "op": "eq", "value": "F1", "value_column": {"json_path": ["father", "surname"]}}
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


def test_build_where_neither_value_nor_value_column_rejected():
    conditions = [{"column": "gramps_id", "op": "eq"}]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


def test_build_where_value_column_rejected_for_in():
    conditions = [
        {"column": "gramps_id", "op": "in", "value_column": {"json_path": ["father", "surname"]}}
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


def test_build_where_value_column_rejected_for_like():
    conditions = [
        {"column": "gramps_id", "op": "like", "value_column": {"json_path": ["father", "surname"]}}
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


# --- _build_where: 'or'/'not' groups (from where_expr's "a or b"/"not a") ------


def test_build_where_or_group():
    conditions = [
        {
            "or": [
                {"column": "gender", "op": "eq", "value": 1},
                {"column": "gender", "op": "eq", "value": 2},
            ]
        }
    ]
    where = _build_where(conditions, PERSON)
    assert isinstance(where, Or)
    assert len(where.exprs) == 2
    assert all(isinstance(e, Eq) and e.column == "gender" for e in where.exprs)
    assert [e.value for e in where.exprs] == [1, 2]


def test_build_where_not_group():
    conditions = [{"not": {"column": "gender", "op": "eq", "value": 1}}]
    where = _build_where(conditions, PERSON)
    assert isinstance(where, Not)
    assert isinstance(where.expr, Eq)
    assert where.expr.column == "gender"
    assert where.expr.value == 1


def test_build_where_or_empty_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _build_where([{"or": []}], PERSON)
    assert exc_info.value.code == 422


def test_build_where_nested_or_and_leaf():
    # "gender == 1 and (surname == 'Smith' or surname == 'Jones')" --
    # top-level list item 0 is a plain leaf, item 1 is an 'or' group; the
    # two combine via the same implicit-AND _build_where already does for
    # an all-leaf conditions list.
    conditions = [
        {"column": "gender", "op": "eq", "value": 1},
        {
            "or": [
                {"column": "surname", "op": "eq", "value": "Smith"},
                {"column": "surname", "op": "eq", "value": "Jones"},
            ]
        },
    ]
    where = _build_where(conditions, PERSON)
    assert len(where.exprs) == 2
    assert isinstance(where.exprs[0], Eq)
    assert isinstance(where.exprs[1], Or)


# --- _build_where: end-to-end via where_expr (and/exists/count_of/FlatColumnRef) --
#
# These go through the real _resolve_where_conditions -> _build_where pair
# together, the same as _post_sql, since 'and'/'exists'/'count_of' only ever
# arise from where_expr (QueryWhereConditionArgs' schema can't produce them
# for a raw `where` body) -- see where_list_to_ast's docstring for why these
# are delegated there rather than hand-built here.


def _where(expr: str, spec=PERSON):
    return _build_where(_resolve_where_conditions({"where_expr": expr}, spec), spec)


def test_build_where_and_group_nested_under_not():
    where = _where("not (gender == 1 and gramps_id == 'I1')")
    assert isinstance(where, Not)
    assert isinstance(where.expr, And)
    assert all(isinstance(e, Eq) for e in where.expr.exprs)


def test_build_where_exists():
    where = _where("exists(events, type.value == 12)")
    assert isinstance(where, Exists)
    assert where.collection.name == "events"
    assert where.condition is not None


def test_build_where_exists_any_sugar_equivalent():
    assert repr(_where("exists(events, type.value == 12)")) == repr(
        _where("any(e.type.value == 12 for e in events)")
    )


def test_build_where_count_of():
    where = _where("count(events) > 2")
    assert isinstance(where, Gt)
    assert isinstance(where.column, CollectionCount)
    assert where.column.collection.name == "events"
    assert where.value == 2


def test_build_where_value_column_same_table_wrapped_as_flat_column_ref():
    # Regression test: a same-table plain-string value_column ("given_name
    # == surname") must resolve to a FlatColumnRef, not a bare str -- a bare
    # str is indistinguishable from an ordinary literal to Comparison/
    # Contains, so without this wrapping the query would silently compare
    # given_name against the *literal text* "surname" instead of the two
    # columns against each other (see FlatColumnRef's docstring).
    conditions = [{"column": "given_name", "op": "eq", "value_column": "surname"}]
    where = _build_where(conditions, PERSON)
    assert isinstance(where, Eq)
    assert isinstance(where.value, FlatColumnRef)
    assert where.value.name == "surname"


# --- QueryWhereConditionArgs.op: derived from VALID_LEAF_OPS, not hand-copied --


def test_where_op_schema_matches_valid_leaf_ops():
    # Regression test for the whole point of VALID_LEAF_OPS existing: a new
    # op added to gramps_object_query_language should become valid for a raw
    # `where` JSON body automatically, with no gramps-web-api edit needed --
    # this fails the moment the schema's allowed set and VALID_LEAF_OPS
    # diverge, whichever direction that happens.
    op_field = QueryWhereConditionArgs().fields["op"]
    allowed = {choice for validator in op_field.validators for choice in validator.choices}
    assert allowed == set(VALID_LEAF_OPS)
