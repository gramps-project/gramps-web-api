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
    compile_count_query,
    compile_query,
    default_ref_key,
    resolve_column_path,
)
from gramps_webapi.api.resources.object_query import (
    _build_where,
    _check_no_duplicate_keys,
    _parse_select_entry,
    _resolve_after,
    _resolve_dialect,
    _resolve_treeid,
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


def test_parse_select_entry_path_uses_its_own_text_as_key():
    ref, key = _parse_select_entry("primary_name.surname_list[0].surname", PERSON)
    assert ref == JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert key == "primary_name.surname_list[0].surname"


def test_parse_select_entry_path_with_alias():
    ref, key = _parse_select_entry("primary_name.first_name as first", PERSON)
    assert ref == JsonPath(("primary_name", "first_name"))
    assert key == "first"


def test_parse_select_entry_rejects_handle_alias():
    # The response's "handle" key is what next_after is read from --
    # letting a client shadow it with other content would break pagination
    # silently.
    with pytest.raises(QueryError):
        _parse_select_entry("primary_name.first_name as handle", PERSON)
    with pytest.raises(QueryError):
        _parse_select_entry("count(events) as handle", PERSON)


def test_parse_select_entry_plain_handle_column_is_fine():
    assert _parse_select_entry("handle", PERSON) == ("handle", "handle")


def test_parse_select_entry_rejects_unknown_field():
    with pytest.raises(QueryError):
        _parse_select_entry("no_such_field", PERSON)


def test_parse_select_entry_count_with_alias():
    ref, key = _parse_select_entry("count(events) as event_count", PERSON)
    assert isinstance(ref, CollectionCount)
    assert key == "event_count"


def test_parse_select_entry_relationship_crossing():
    ref, key = _parse_select_entry("birth.date", PERSON)
    assert isinstance(ref, RelatedObject)
    assert key == "birth.date"
    assert _parse_select_entry("father.surname as father_surname", FAMILY)[1] == "father_surname"


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


# --- _build_where: where_expr, compiled by GOQL --------------------------------


def _where(expr: str, spec=PERSON):
    return _build_where({"where_expr": expr}, spec)


def test_build_where_none_without_where_expr():
    assert _build_where({}, PERSON) is None
    assert _build_where({"where_expr": None}, PERSON) is None
    assert _build_where({"where_expr": ""}, PERSON) is None


def test_build_where_simple_comparison():
    where = _where("gender == 1")
    assert isinstance(where, Eq)
    assert where.value == 1


def test_build_where_and_or_not():
    where = _where("not (gender == 1 and gramps_id == 'I1') or gender == 2")
    assert isinstance(where, Or)
    assert isinstance(where.exprs[0], Not)
    assert isinstance(where.exprs[0].expr, And)


def test_build_where_exists_and_any_sugar():
    where = _where("exists(events, type.value == 12)")
    assert isinstance(where, Exists)
    assert where.collection.name == "events"
    assert repr(where) == repr(_where("any(e.type.value == 12 for e in events)"))
    assert _where("exists(events)").condition is None


def test_build_where_count():
    where = _where("count(events) > 2")
    assert isinstance(where, Gt)
    assert isinstance(where.column, CollectionCount)
    assert where.value == 2


def test_build_where_backlinks():
    assert isinstance(_where("not exists(backlinks)", NOTE), Not)
    assert isinstance(_where('exists(backlinks, _class == "Person")', NOTE), Exists)
    assert isinstance(_where("count(backlinks) == 0", NOTE).column, CollectionCount)


def test_build_where_field_vs_field():
    where = _where("given_name == surname")
    assert isinstance(where, Eq)
    assert isinstance(where.value, FlatColumnRef)
    assert where.value.name == "surname"


@pytest.mark.parametrize(
    "expr",
    ["gender ==", "no_such_field == 1", "gender in []", "handle == Env.HOME"],
)
def test_build_where_bad_expression_is_422(expr):
    with pytest.raises(HTTPException) as exc_info:
        _where(expr)
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
