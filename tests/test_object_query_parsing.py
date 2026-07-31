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

from gramps_webapi.api.query import (
    BIRTH_DATE,
    BIRTH_DATE_SORTVAL,
    DEATH_DATE,
    DEATH_DATE_SORTVAL,
    PERSON,
    Dialect,
    JsonPath,
    OrderBy,
    QueryError,
)
from gramps_webapi.api.resources.object_query import (
    _check_no_duplicate_keys,
    _json_path_default_key,
    _normalize_related_event_date_value,
    _parse_column_ref,
    _parse_select_entry,
    _resolve_after,
    _resolve_dialect,
    _resolve_treeid,
    _resolve_where_conditions,
)


# --- _parse_column_ref -------------------------------------------------------


def test_parse_column_ref_plain_string():
    assert _parse_column_ref("gramps_id") == "gramps_id"


def test_parse_column_ref_json_path():
    ref = _parse_column_ref({"json_path": ["primary_name", "first_name"]})
    assert ref == JsonPath(("primary_name", "first_name"))


def test_parse_column_ref_birth_date_resolves_to_sortval_variant():
    # WHERE context uses the sortval-extracting constant, not the
    # full-struct one select uses for the same bare string.
    assert _parse_column_ref("birth_date") == BIRTH_DATE_SORTVAL
    assert _parse_column_ref("birth_date") != BIRTH_DATE


def test_parse_column_ref_death_date_resolves_to_sortval_variant():
    assert _parse_column_ref("death_date") == DEATH_DATE_SORTVAL


def test_parse_column_ref_rejects_non_str_non_dict():
    with pytest.raises(QueryError):
        _parse_column_ref(123)


def test_parse_column_ref_rejects_dict_without_json_path_key():
    with pytest.raises(QueryError):
        _parse_column_ref({"column": "gramps_id"})


def test_parse_column_ref_rejects_non_list_json_path():
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": "primary_name.first_name"})


def test_parse_column_ref_rejects_empty_json_path():
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": []})


def test_parse_column_ref_rejects_bad_segment_type():
    # Bubbles up from JsonPath.__post_init__ -- bool disguised as int, float,
    # None, nested list, etc. are all rejected there.
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": ["primary_name", True]})
    with pytest.raises(QueryError):
        _parse_column_ref({"json_path": ["primary_name", 1.5]})


# --- _json_path_default_key ---------------------------------------------------


def test_json_path_default_key_str_segments():
    path = JsonPath(("primary_name", "first_name"))
    assert _json_path_default_key(path) == "primary_name.first_name"


def test_json_path_default_key_with_int_segment():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert _json_path_default_key(path) == "primary_name.surname_list[0].surname"


def test_json_path_default_key_leading_int_segment():
    path = JsonPath((0, "value"))
    assert _json_path_default_key(path) == "[0].value"


def test_json_path_default_key_single_segment():
    assert _json_path_default_key(JsonPath(("gender",))) == "gender"


# --- _parse_select_entry -------------------------------------------------------


def test_parse_select_entry_plain_string():
    assert _parse_select_entry("surname") == ("surname", "surname")


def test_parse_select_entry_json_path_without_alias_uses_derived_key():
    ref, key = _parse_select_entry(
        {"json_path": ["primary_name", "surname_list", 0, "surname"]}
    )
    assert ref == JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert key == "primary_name.surname_list[0].surname"


def test_parse_select_entry_json_path_with_alias():
    ref, key = _parse_select_entry(
        {"json_path": ["primary_name", "first_name"], "as": "first"}
    )
    assert ref == JsonPath(("primary_name", "first_name"))
    assert key == "first"


def test_parse_select_entry_rejects_handle_alias_on_json_path():
    # The response's "handle" key is load-bearing for next_after -- letting a
    # client shadow it with unrelated JSON content would corrupt pagination
    # silently.
    with pytest.raises(QueryError):
        _parse_select_entry({"json_path": ["primary_name", "first_name"], "as": "handle"})


def test_parse_select_entry_plain_handle_column_is_fine():
    assert _parse_select_entry("handle") == ("handle", "handle")


def test_parse_select_entry_rejects_invalid_shape():
    with pytest.raises(QueryError):
        _parse_select_entry(123)


# --- _check_no_duplicate_keys --------------------------------------------------


def test_check_no_duplicate_keys_passes_for_unique_keys():
    _check_no_duplicate_keys([("a", "a"), ("b", "b")])  # no raise


def test_check_no_duplicate_keys_rejects_duplicate():
    path_a = JsonPath(("x",))
    path_b = JsonPath(("y",))
    with pytest.raises(QueryError):
        _check_no_duplicate_keys([(path_a, "same"), (path_b, "same")])


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
    _resolve_after(basedb, PERSON, [OrderBy("surname", "asc")], "h1", True, treeid=None)
    sql, params = basedb.dbapi.calls[0]
    assert "treeid" not in sql
    assert params == ["h1"]


def test_resolve_after_adds_treeid_clause_when_given():
    # Without this, a handle from another tree on a shared multi-tree
    # backend would resolve just as well -- leaking that row's sort-column
    # values (and confirming its existence) across tenants even though the
    # main paginated query stays properly scoped.
    basedb = _FakeAfterBasedb(row=("Smith", "h1"))
    _resolve_after(basedb, PERSON, [OrderBy("surname", "asc")], "h1", True, treeid=7)
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


def test_resolve_where_conditions_invalid_expr_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_where_conditions({"where_expr": "gender == 1 or gender == 2"}, PERSON)
    assert exc_info.value.code == 422


# --- birth_date / death_date (RelatedEventDate) --------------------------------


def test_parse_select_entry_birth_date():
    assert _parse_select_entry("birth_date") == (BIRTH_DATE, "birth_date")


def test_parse_select_entry_death_date():
    assert _parse_select_entry("death_date") == (DEATH_DATE, "death_date")


def test_normalize_related_event_date_value_parses_sqlite_json_string():
    assert _normalize_related_event_date_value('{"sortval": 2439857}') == {
        "sortval": 2439857
    }


def test_normalize_related_event_date_value_passes_through_dict():
    # PostgreSQL's jsonb expressions come back through psycopg2 already
    # parsed -- nothing to do.
    value = {"sortval": 2439857}
    assert _normalize_related_event_date_value(value) is value


def test_normalize_related_event_date_value_passes_through_none():
    assert _normalize_related_event_date_value(None) is None
