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

from marshmallow import ValidationError

from gramps_object_query_language.query import (
    EVENT,
    FAMILY,
    MEDIA,
    NOTE,
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
    Query,
    QueryError,
    RelatedObject,
    Regex,
    compile_count_query,
    compile_query,
    default_ref_key,
    resolve_column_path,
)
from gramps_object_query_language.query_lang import VALID_LEAF_OPS
from gramps_webapi.api.resources.object_query import (
    QueryExistsPayloadArgs,
    QueryWhereConditionArgs,
    _build_where,
    _check_no_duplicate_keys,
    _needs_json_decoding,
    _normalize_json_value,
    _parse_column_ref,
    _parse_select_entry,
    _resolve_after,
    _resolve_dialect,
    _resolve_treeid,
    _resolve_where_conditions,
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


# --- default_ref_key (moved into the library; see gramps_object_query_language) ---


def test_default_key_for_plain_string():
    assert default_ref_key("gramps_id") == "gramps_id"


def test_default_key_for_json_path_str_segments():
    path = JsonPath(("primary_name", "first_name"))
    assert default_ref_key(path) == "primary_name.first_name"


def test_default_key_for_json_path_with_int_segment():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert default_ref_key(path) == "primary_name.surname_list[0].surname"


def test_default_key_for_json_path_leading_int_segment():
    path = JsonPath((0, "value"))
    assert default_ref_key(path) == "[0].value"


def test_default_key_for_json_path_single_segment():
    assert default_ref_key(JsonPath(("gender",))) == "gender"


def test_default_key_for_related_object():
    ref = resolve_column_path(PERSON, ["birth", "date", "sortval"])
    assert default_ref_key(ref) == "birth.date.sortval"


def test_default_key_for_two_hop_related_object():
    ref = resolve_column_path(PERSON, ["birth", "place", "title"])
    assert default_ref_key(ref) == "birth.place.title"


def test_default_key_for_related_object_plain_field():
    ref = resolve_column_path(FAMILY, ["father", "surname"])
    assert default_ref_key(ref) == "father.surname"


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


# --- _needs_json_decoding / _normalize_json_value --------------------------------


def test_needs_json_decoding_plain_string_false():
    assert _needs_json_decoding("surname", PERSON) is False


def test_needs_json_decoding_scalar_json_path_false():
    """Regression: `primary_name.first_name` terminates in a JsonPath, but
    Gramps' schema says it holds a *string*. Decoding it turned a person
    genuinely named "123" into the integer 123 in the response.
    """
    assert _needs_json_decoding(JsonPath(("primary_name", "first_name")), PERSON) is False


def test_needs_json_decoding_composite_json_path_true():
    # A whole Name struct is an object -- SQLite hands that back as JSON text.
    assert _needs_json_decoding(JsonPath(("primary_name",)), PERSON) is True


def test_needs_json_decoding_array_json_path_true():
    assert _needs_json_decoding(JsonPath(("event_ref_list",)), PERSON) is True


def test_needs_json_decoding_related_object_plain_field_false():
    # father.surname ends in a real flat column -- no JSON functions
    # involved at all, so no decoding needed.
    ref = resolve_column_path(FAMILY, ["father", "surname"])
    assert _needs_json_decoding(ref, FAMILY) is False


def test_needs_json_decoding_related_object_composite_field_true():
    ref = resolve_column_path(PERSON, ["birth", "date"])
    assert _needs_json_decoding(ref, PERSON) is True


def test_needs_json_decoding_related_object_scalar_field_false():
    # birth.date.sortval is an integer inside the related event's JSON --
    # typed correctly by SQLite already, so nothing to decode.
    ref = resolve_column_path(PERSON, ["birth", "date", "sortval"])
    assert _needs_json_decoding(ref, PERSON) is False


def test_needs_json_decoding_chained_related_object():
    # birth.place.title: the chain's own leaf ("title") is a plain column,
    # even though an intermediate hop (birth -> Event) uses a JsonPath
    # internally for its handle_ref -- only the final value's type matters.
    ref = resolve_column_path(PERSON, ["birth", "place", "title"])
    assert _needs_json_decoding(ref, PERSON) is False


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


# Named "PostgreSQL"/"SomeFutureBackend" via `type(...)` rather than a real
# subclass -- exercises the class-*name* allowlist `_resolve_dialect`/
# `_resolve_treeid` actually check (see `_resolve_dialect`'s docstring on why
# `isinstance` can't be trusted for a plugin-loaded backend class), without
# importing the real addon.
_FakeSingleUserPostgresBackend = type("PostgreSQL", (), {})
_FakeUnknownBackend = type("SomeFutureBackend", (), {})


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


def test_resolve_dialect_detects_shared_postgres_by_class_name():
    # `SharedPostgreSQL` versions without a `.dialect` attribute yet are
    # still recognized by class name -- not lumped in with genuinely unknown
    # backends.
    basedb = type("SharedPostgreSQL", (), {})()
    assert not hasattr(basedb, "dialect")
    assert _resolve_dialect(basedb) == Dialect.POSTGRESQL


def test_resolve_dialect_aborts_for_unknown_backend():
    # Guessing PostgreSQL for a backend this module has never seen can
    # render dialect-specific SQL (`::jsonb`, `jsonb_extract_path(...)`)
    # against a connection that can't run it -- failing closed (501) is
    # safer than a silent, possibly-wrong guess.
    with pytest.raises(HTTPException) as exc_info:
        _resolve_dialect(_FakeDbNoDialect())
    assert exc_info.value.code == 501


def test_resolve_dialect_falls_through_unrecognized_explicit_dialect_name_to_class_check():
    # An unrecognized `.dialect` string falls through to the class-name
    # checks rather than being trusted outright or immediately aborting.
    fake_shared_postgres_with_bad_dialect = type(
        "SharedPostgreSQL", (), {"dialect": "mysql"}
    )
    assert (
        _resolve_dialect(fake_shared_postgres_with_bad_dialect())
        == Dialect.POSTGRESQL
    )


def test_resolve_dialect_aborts_when_explicit_dialect_name_and_class_both_unrecognized():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_dialect(_FakeDbWithDialect("mysql"))
    assert exc_info.value.code == 501


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


def test_resolve_treeid_reads_dbapi_treeid_when_present():
    assert _resolve_treeid(_FakeBasedbWithTreeidDbapi()) == 7


def test_resolve_treeid_returns_none_for_single_tree_backend():
    # SQLite / single-user PostgreSQL have no `.dbapi.treeid` at all --
    # `None` means "omit the clause", not "unscoped is fine by default".
    basedb = _FakeSingleUserPostgresBackend()
    basedb.dbapi = _FakeDbapiNoTreeid()
    assert _resolve_treeid(basedb) is None

    sqlite_basedb = SQLite.__new__(SQLite)
    sqlite_basedb.dbapi = _FakeDbapiNoTreeid()
    assert _resolve_treeid(sqlite_basedb) is None


def test_resolve_treeid_aborts_for_unrecognized_backend():
    # A backend this module has never seen, with no `.dbapi.treeid` and a
    # class name matching neither known single-tree backend, must not be
    # treated as "no scoping needed" -- on a genuinely shared backend that
    # would let an unscoped query return other tenants' rows instead of
    # erroring.
    basedb = _FakeUnknownBackend()
    basedb.dbapi = _FakeDbapiNoTreeid()
    with pytest.raises(HTTPException) as exc_info:
        _resolve_treeid(basedb)
    assert exc_info.value.code == 501


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
    # Compiled by `compile_after_lookup` now, so the trailing value is the
    # compiled query's own LIMIT, not part of the cursor lookup itself.
    assert params == ["h1", 1]


def test_resolve_after_adds_treeid_clause_when_given():
    # Without this, a handle from another tree on a shared multi-tree
    # backend would resolve just as well -- leaking that row's sort-column
    # values (and confirming its existence) across tenants even though the
    # main paginated query stays properly scoped.
    basedb = _FakeAfterBasedb(row=("Smith", "h1"))
    _resolve_after(basedb, PERSON, [OrderBy("surname", "asc")], "h1", treeid=7)
    sql, params = basedb.dbapi.calls[0]
    assert "AND treeid = ?" in sql
    assert params == ["h1", 7, 1]


def test_resolve_after_compiles_a_path_sort_column():
    """A path sort column can't be read by interpolating a name into a
    SELECT -- it's a correlated subquery with bound params, which is why
    this goes through the compiler.
    """
    basedb = _FakeAfterBasedb(row=(2439857, "h1"))
    _resolve_after(
        basedb,
        PERSON,
        [OrderBy("birth.date.sortval", "asc")],
        "h1",
        treeid=None,
        dialect=Dialect.SQLITE,
    )
    sql, params = basedb.dbapi.calls[0]
    assert "FROM event" in sql
    assert sql.count("?") == len(params)


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


def test_build_where_value_column_rejected_for_regex():
    # A pattern only known at row-execution time can't be validated as a
    # compilable regex ahead of time, same reasoning as "in"/"like" above --
    # this is the guard that keeps a hand-crafted raw `where` JSON leaf from
    # reaching Regex(column, RelatedObject(...)) with no field-vs-field
    # support of its own for this op.
    conditions = [
        {"column": "gramps_id", "op": "regex", "value_column": {"json_path": ["father", "surname"]}}
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


def test_build_where_regex_with_plain_value_accepted():
    # The value_column guard above is scoped to `value_column` specifically
    # -- a plain literal pattern (the normal case) must still build fine.
    conditions = [{"column": "gramps_id", "op": "regex", "value": "^F.*"}]
    where = _build_where(conditions, FAMILY)
    assert isinstance(where, Regex)
    assert where.column == resolve_column_path(FAMILY, ["gramps_id"])
    assert where.value == "^F.*"


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


# --- _build_where: end-to-end via where_expr and via raw `where` JSON ---------
#
# These go through the real _resolve_where_conditions -> _build_where pair
# together, the same as _post_sql. 'and'/'or'/'not'/'exists'/'count_of' used
# to only be reachable via where_expr -- QueryWhereConditionArgs' schema
# rejected them for a raw `where` body (a 422, "Unknown field: exists" etc.,
# for *any* collection, not just a new one -- confirmed live against
# test_build_where_exists() below before the schema was widened). That gap
# is exactly how it went unnoticed for as long as it did: every test in this
# section only ever exercised `_where()`/where_expr, so a regression on the
# `where` side had nothing here to catch it. Every case below now goes
# through `_assert_expr_and_where_agree`, which checks both paths produce
# the *identical* AST, not just "both don't crash" -- see that helper's own
# docstring.


def _where(expr: str, spec=PERSON):
    return _build_where(_resolve_where_conditions({"where_expr": expr}, spec), spec)


def _assert_expr_and_where_agree(expr: str, where_json: list, spec=PERSON):
    """Asserts `where_expr` and the equivalent raw `where` JSON produce the
    identical `query.py` AST, and returns it (so a caller can still make
    its own assertions on the shape, same as `_where()`'s callers already
    do). `where_json` is loaded through `QueryWhereConditionArgs` first
    (`many=True`, matching how `QueryBodyArgs.where`'s own `wf.List(wf.Nested(
    QueryWhereConditionArgs))` field loads a request body) rather than
    handed to `_build_where` as a raw dict -- so this also exercises the
    schema's own `attribute`/`data_key` mapping for `and`/`or`/`not`, not
    just `_build_where`'s AST-building logic.
    """
    loaded = QueryWhereConditionArgs(many=True).load(where_json)
    where_from_json = _build_where(loaded, spec)
    where_from_expr = _where(expr, spec)
    assert repr(where_from_json) == repr(where_from_expr), (
        f"where={where_from_json!r} but where_expr={where_from_expr!r}"
    )
    return where_from_expr


def test_build_where_and_group_nested_under_not():
    where = _assert_expr_and_where_agree(
        "not (gender == 1 and gramps_id == 'I1')",
        [{"not": {"and": [
            {"column": "gender", "op": "eq", "value": 1},
            {"column": "gramps_id", "op": "eq", "value": "I1"},
        ]}}],
    )
    assert isinstance(where, Not)
    assert isinstance(where.expr, And)
    assert all(isinstance(e, Eq) for e in where.expr.exprs)


def test_build_where_or_group_via_where_expr_and_json():
    where = _assert_expr_and_where_agree(
        "gender == 1 or gender == 2",
        [{"or": [
            {"column": "gender", "op": "eq", "value": 1},
            {"column": "gender", "op": "eq", "value": 2},
        ]}],
    )
    assert isinstance(where, Or)
    assert len(where.exprs) == 2


def test_build_where_not_group_via_where_expr_and_json():
    where = _assert_expr_and_where_agree(
        "not (gender == 1)",
        [{"not": {"column": "gender", "op": "eq", "value": 1}}],
    )
    assert isinstance(where, Not)
    assert isinstance(where.expr, Eq)


def test_build_where_exists():
    where = _assert_expr_and_where_agree(
        "exists(events, type.value == 12)",
        [{"exists": {
            "relationship": "events",
            "where": [{"column": {"json_path": ["type", "value"]}, "op": "eq", "value": 12}],
        }}],
    )
    assert isinstance(where, Exists)
    assert where.collection.name == "events"
    assert where.condition is not None


def test_build_where_exists_no_condition():
    where = _assert_expr_and_where_agree(
        "exists(events)",
        [{"exists": {"relationship": "events"}}],
    )
    assert isinstance(where, Exists)
    assert where.condition is None


def test_build_where_exists_any_sugar_equivalent():
    assert repr(_where("exists(events, type.value == 12)")) == repr(
        _where("any(e.type.value == 12 for e in events)")
    )


def test_build_where_count_of():
    where = _assert_expr_and_where_agree(
        "count(events) > 2",
        [{"column": {"count_of": {"relationship": "events"}}, "op": "gt", "value": 2}],
    )
    assert isinstance(where, Gt)
    assert isinstance(where.column, CollectionCount)
    assert where.column.collection.name == "events"
    assert where.value == 2


def test_build_where_backlinks_not_exists():
    where = _assert_expr_and_where_agree(
        "not exists(backlinks)",
        [{"not": {"exists": {"relationship": "backlinks"}}}],
        spec=NOTE,
    )
    assert isinstance(where, Not)
    assert isinstance(where.expr, Exists)


def test_build_where_backlinks_class_filter():
    where = _assert_expr_and_where_agree(
        'exists(backlinks, _class == "Person")',
        [{"exists": {
            "relationship": "backlinks",
            "where": [{"column": "_class", "op": "eq", "value": "Person"}],
        }}],
        spec=NOTE,
    )
    assert isinstance(where, Exists)
    assert where.collection.name == "backlinks"


def test_build_where_backlinks_count():
    where = _assert_expr_and_where_agree(
        "count(backlinks) == 0",
        [{"column": {"count_of": {"relationship": "backlinks"}}, "op": "eq", "value": 0}],
        spec=NOTE,
    )
    assert isinstance(where.column, CollectionCount)


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


# --- QueryWhereConditionArgs: schema-level shape validation -------------------
#
# A condition node must be exactly one of: a leaf (column+op[+value/
# value_column]), or one combinator (and/or/not/exists) -- checked in
# _check_shape, since no single field's own `required`/`validate` can
# express "required unless X is present" on its own.


def test_where_schema_accepts_plain_leaf():
    loaded = QueryWhereConditionArgs().load({"column": "gender", "op": "eq", "value": 1})
    assert loaded == {"column": "gender", "op": "eq", "value": 1}


def test_where_schema_accepts_and_or_not_exists():
    assert "and" in QueryWhereConditionArgs().load(
        {"and": [{"column": "gender", "op": "eq", "value": 1}]}
    )
    assert "or" in QueryWhereConditionArgs().load(
        {"or": [{"column": "gender", "op": "eq", "value": 1}]}
    )
    assert "not" in QueryWhereConditionArgs().load(
        {"not": {"column": "gender", "op": "eq", "value": 1}}
    )
    assert "exists" in QueryWhereConditionArgs().load(
        {"exists": {"relationship": "notes"}}
    )


def test_where_schema_loaded_dict_uses_wire_keys_not_python_attribute_names():
    # Regression test for the schema's own and_/or_/not_ Python attribute
    # names (and/or/not are reserved words, can't be literal attribute
    # names) -- without `attribute="and"` etc. on each field, .load() would
    # return "and_"/"or_"/"not_" keys, which where_list_to_ast's
    # _node_from_json (checking `"and" in node`, never `"and_"`) would
    # silently fail to recognize as a combinator at all.
    loaded = QueryWhereConditionArgs().load(
        {"and": [{"column": "gender", "op": "eq", "value": 1}]}
    )
    assert set(loaded) == {"and"}


def test_where_schema_rejects_empty_condition():
    with pytest.raises(ValidationError):
        QueryWhereConditionArgs().load({})


def test_where_schema_rejects_leaf_missing_op():
    with pytest.raises(ValidationError):
        QueryWhereConditionArgs().load({"column": "gender"})


def test_where_schema_rejects_leaf_missing_column():
    with pytest.raises(ValidationError):
        QueryWhereConditionArgs().load({"op": "eq", "value": 1})


def test_where_schema_rejects_combinator_mixed_with_leaf():
    with pytest.raises(ValidationError):
        QueryWhereConditionArgs().load(
            {
                "column": "gender",
                "op": "eq",
                "value": 1,
                "not": {"column": "gender", "op": "eq", "value": 0},
            }
        )


def test_where_schema_rejects_two_combinators():
    with pytest.raises(ValidationError):
        QueryWhereConditionArgs().load(
            {
                "and": [{"column": "a", "op": "eq", "value": 1}],
                "or": [{"column": "b", "op": "eq", "value": 1}],
            }
        )


def test_exists_payload_schema_requires_relationship():
    with pytest.raises(ValidationError):
        QueryExistsPayloadArgs().load({})


# --- nested-leaf validation: _validate_leaf_condition applied at any depth ---
#
# Regression tests for a gap found while widening QueryWhereConditionArgs:
# _build_where's leaf-validation used to only ever walk the *top-level*
# `where` list -- a leaf nested inside `count_of`'s own `where` already
# silently bypassed it (confirmed live: a malformed non-list "in" value
# there was accepted and iterated character-by-character instead of
# rejected); widening the schema for and/or/not/exists made this far more
# reachable (any nested leaf, at any depth), so _validate_where_tree walks
# the full tree now, not just the top level.


def test_malformed_in_rejected_when_nested_in_or():
    conditions = QueryWhereConditionArgs(many=True).load(
        [{"or": [{"column": "gender", "op": "in", "value": "not-a-list"}]}]
    )
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, PERSON)
    assert exc_info.value.code == 422


def test_malformed_in_rejected_when_nested_in_exists_where():
    conditions = QueryWhereConditionArgs(many=True).load(
        [{"exists": {
            "relationship": "backlinks",
            "where": [{"column": "_class", "op": "in", "value": "not-a-list"}],
        }}]
    )
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, NOTE)
    assert exc_info.value.code == 422


def test_malformed_in_rejected_when_nested_in_count_of_where():
    conditions = [
        {
            "column": {
                "count_of": {
                    "relationship": "children",
                    "where": [{"column": "gender", "op": "in", "value": "not-a-list"}],
                }
            },
            "op": "gt",
            "value": 0,
        }
    ]
    with pytest.raises(HTTPException) as exc_info:
        _build_where(conditions, FAMILY)
    assert exc_info.value.code == 422


# --- treeid threading through every SQL-emitting path -----------------------
#
# `_resolve_treeid` (tested above) is only half the story -- the value it
# returns has to actually reach every place raw SQL gets built, or a new
# query shape added later without scoping would silently return rows from
# every tree sharing a `SharedPostgreSQL` instance, not just the caller's
# own. `_resolve_after`'s own treeid clause is already covered above
# (`test_resolve_after_adds_treeid_clause_when_given`); the three below --
# main query, COUNT query, and a RelatedObject subquery -- are `compile_query`/
# `compile_count_query`'s own responsibility, called from `_post_sql` with
# whatever `_resolve_treeid` returned.


def test_compile_query_adds_treeid_clause_to_main_query():
    query = Query(select=["handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, treeid=7)
    assert "WHERE treeid = ?" in sql
    assert 7 in params


def test_compile_query_omits_treeid_clause_when_none():
    query = Query(select=["handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, treeid=None)
    assert "treeid" not in sql
    assert 7 not in params


def test_compile_count_query_adds_treeid_clause():
    query = Query(select=["handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_count_query(PERSON, query, dialect=Dialect.SQLITE, treeid=7)
    assert "treeid = ?" in sql
    assert params == [7]


def test_compile_count_query_omits_treeid_clause_when_none():
    query = Query(select=["handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_count_query(PERSON, query, dialect=Dialect.SQLITE, treeid=None)
    assert "treeid" not in sql
    assert params == []


def test_compile_query_related_object_subquery_carries_treeid():
    # A `select`/`where` column that crosses a relationship (Person->Event
    # via "birth") compiles to a correlated subquery against the related
    # table -- that subquery's own `FROM event ...` needs its own
    # `treeid = ?` scoping, independent of (and in addition to) the outer
    # `person` table's, since the related row lives in the same
    # shared-tenant physical table.
    ref = resolve_column_path(PERSON, ["birth", "date", "sortval"])
    query = Query(select=[ref, "handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, treeid=7)
    # Once for the correlated subquery's own related-table scoping, once for
    # the outer table.
    assert sql.count("treeid = ?") == 2
    assert params.count(7) == 2


def test_compile_query_related_object_subquery_omits_treeid_when_none():
    ref = resolve_column_path(PERSON, ["birth", "date", "sortval"])
    query = Query(select=[ref, "handle"], where=None, order_by=[], limit=10, after=None)
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, treeid=None)
    assert "treeid" not in sql


# --- PostgreSQL physical-name column overrides -------------------------------
#
# The `SharedPostgreSQL`/`PostgreSQL` addons physically rename a handful of
# columns that collide with reserved SQL words (`Media.desc` -> `desc_`,
# `Event.description` -> `desc_ription`) -- see `query.py`'s
# `_POSTGRESQL_PHYSICAL_COLUMN_OVERRIDES`. `compile_query` takes an explicit
# `dialect`, so this is asserted directly against the rendered SQL string,
# with no Postgres instance required.


def test_compile_query_renders_postgresql_physical_name_for_desc_select():
    query = Query(select=["desc", "handle"], where=None, order_by=[], limit=10, after=None)
    sql, _ = compile_query(MEDIA, query, dialect=Dialect.POSTGRESQL)
    assert "desc_," in sql or "desc_ FROM" in sql or "SELECT desc_," in sql
    assert '"desc"' not in sql


def test_compile_query_keeps_plain_desc_column_name_for_sqlite():
    query = Query(select=["desc", "handle"], where=None, order_by=[], limit=10, after=None)
    sql, _ = compile_query(MEDIA, query, dialect=Dialect.SQLITE)
    assert '"desc"' in sql
    assert "desc_" not in sql


def test_compile_query_renders_postgresql_physical_name_for_desc_order_by():
    query = Query(
        select=["handle"],
        where=None,
        order_by=[OrderBy("desc", "asc")],
        limit=10,
        after=None,
    )
    sql, _ = compile_query(MEDIA, query, dialect=Dialect.POSTGRESQL)
    assert "ORDER BY desc_ ASC" in sql


def test_compile_query_renders_postgresql_physical_name_for_desc_where():
    query = Query(select=["handle"], where=Eq("desc", ""), order_by=[], limit=10, after=None)
    sql, params = compile_query(MEDIA, query, dialect=Dialect.POSTGRESQL)
    assert "desc_" in sql
    assert '"desc"' not in sql
    assert params == ["", 10]


def test_compile_query_renders_postgresql_physical_name_for_description():
    query = Query(select=["handle"], where=Eq("description", ""), order_by=[], limit=10, after=None)
    sql, _ = compile_query(EVENT, query, dialect=Dialect.POSTGRESQL)
    assert "desc_ription" in sql
