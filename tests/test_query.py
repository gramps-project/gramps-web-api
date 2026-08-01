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

"""Tests for the Person query AST and SQL compiler (`gramps_webapi.api.query`)."""

import pytest

from gramps_webapi.api.query import (
    EVENT,
    FAMILY,
    MEDIA,
    PERSON,
    PLACE,
    TAG,
    And,
    ColumnIndex,
    Dialect,
    Eq,
    Gt,
    Gte,
    In,
    JsonPath,
    Like,
    Lt,
    Lte,
    Ne,
    Not,
    Or,
    OrderBy,
    Query,
    QueryError,
    RelatedObject,
    after_columns,
    compile_count_query,
    compile_query,
    resolve_column_path,
)


def test_person_columns_include_expected_flat_fields():
    assert {"handle", "gramps_id", "gender", "private", "given_name", "surname"} <= (
        PERSON.columns
    )


def test_person_table_and_privacy():
    assert PERSON.table == "person"
    assert PERSON.has_privacy is True


def test_tag_has_no_privacy_column():
    # Tag is the one object type with no `private` secondary column.
    assert TAG.table == "tag"
    assert "private" not in TAG.columns
    assert TAG.has_privacy is False


def test_compile_query_skips_privacy_clause_for_types_without_it():
    query = Query(select=["handle"])
    sql, _ = compile_query(TAG, query)
    assert "private" not in sql


def test_compile_count_query_shape():
    query = Query(where=Eq("gender", 1))
    sql, params = compile_count_query(PERSON, query)
    assert sql == (
        "SELECT COUNT(*) FROM person WHERE (gender IS NOT DISTINCT FROM ?) AND private = 0"
    )
    assert params == [1]


def test_compile_count_query_ignores_select_order_by_limit_after():
    # A count has no columns, sort order, or page -- only `where` (+privacy)
    # should affect it, matching total rows across the whole result set.
    query = Query(
        select=["handle", "surname"],
        order_by=[OrderBy("surname", "desc")],
        limit=5,
        after=("Smith", "h1"),
    )
    sql, params = compile_count_query(PERSON, query)
    assert sql == "SELECT COUNT(*) FROM person WHERE private = 0"
    assert params == []


def test_compile_count_query_respects_can_view_private():
    query = Query()
    sql, _ = compile_count_query(PERSON, query, can_view_private=True)
    assert "private" not in sql


def test_compile_count_query_skips_privacy_clause_for_types_without_it():
    sql, params = compile_count_query(TAG, Query())
    assert sql == "SELECT COUNT(*) FROM tag"
    assert params == []


def test_compile_count_query_no_where_no_params():
    sql, params = compile_count_query(PERSON, Query(), can_view_private=True)
    assert sql == "SELECT COUNT(*) FROM person"
    assert params == []


# --- treeid scoping (SharedPostgreSQL multi-tree isolation) -----------------
#
# SharedPostgreSQL stores every tree's rows in the same physical tables,
# distinguished only by a `treeid` column that's part of every table's
# primary key. Nothing applies this filter automatically -- without it,
# these queries would return rows from every tree sharing the instance, not
# just the caller's own.


def test_compile_query_omits_treeid_clause_by_default():
    # Single-tree-per-database backends (SQLite, single-user PostgreSQL)
    # have no `treeid` column at all -- omitting `treeid` must not add a
    # clause referencing a column that doesn't exist there.
    sql, params = compile_query(PERSON, Query(), can_view_private=True)
    assert "treeid" not in sql
    assert None not in params


def test_compile_query_adds_treeid_clause_when_given():
    sql, params = compile_query(PERSON, Query(), can_view_private=True, treeid=7)
    assert "treeid = ?" in sql
    assert 7 in params


def test_compile_query_treeid_clause_combines_with_where_and_privacy():
    query = Query(where=Eq("gender", 1))
    sql, params = compile_query(PERSON, query, treeid=7)
    assert "(gender IS NOT DISTINCT FROM ?)" in sql
    assert "private = 0" in sql
    assert "treeid = ?" in sql
    assert params[0] == 1  # where value
    assert 7 in params[1:-1]  # treeid, before LIMIT
    assert params[-1] == query.limit


def test_compile_count_query_adds_treeid_clause_when_given():
    sql, params = compile_count_query(PERSON, Query(), can_view_private=True, treeid=7)
    assert sql == "SELECT COUNT(*) FROM person WHERE treeid = ?"
    assert params == [7]


def test_compile_count_query_omits_treeid_clause_by_default():
    sql, params = compile_count_query(PERSON, Query(), can_view_private=True)
    assert "treeid" not in sql
    assert params == []


# --- JsonPath -----------------------------------------------------------


def test_jsonpath_requires_at_least_one_segment():
    with pytest.raises(QueryError):
        JsonPath(())


def test_jsonpath_rejects_invalid_segment_types():
    with pytest.raises(QueryError):
        JsonPath(("primary_name", 1.5))  # float
    with pytest.raises(QueryError):
        JsonPath(("primary_name", None))
    with pytest.raises(QueryError):
        JsonPath(("primary_name", True))  # bool is an int subclass -- rejected anyway


def test_jsonpath_accepts_str_and_int_segments():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    assert path.segments == ("primary_name", "surname_list", 0, "surname")
    assert path.base_column == "json_data"


def test_compile_query_jsonpath_without_dialect_raises():
    path = JsonPath(("primary_name", "first_name"))
    with pytest.raises(QueryError):
        compile_query(PERSON, Query(select=["handle", path]))


def test_compile_query_jsonpath_select_sqlite():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    sql, params = compile_query(PERSON, Query(select=["handle", path]), dialect=Dialect.SQLITE)
    assert "json_extract(json_data, ?)" in sql
    assert params[0] == "$.primary_name.surname_list[0].surname"


def test_compile_query_jsonpath_select_postgresql():
    path = JsonPath(("primary_name", "surname_list", 0, "surname"))
    sql, params = compile_query(
        PERSON, Query(select=["handle", path]), dialect=Dialect.POSTGRESQL
    )
    assert "jsonb_extract_path_text(json_data::jsonb, ?, ?, ?, ?)" in sql
    assert params[:4] == ["primary_name", "surname_list", "0", "surname"]


def test_compile_query_jsonpath_where_eq():
    path = JsonPath(("primary_name", "first_name"))
    query = Query(select=["handle"], where=Eq(path, "Root"))
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE)
    assert "json_extract(json_data, ?) IS NOT DISTINCT FROM ?" in sql
    assert params == ["$.primary_name.first_name", "Root", 50]


def test_compile_query_jsonpath_where_in():
    path = JsonPath(("gender",))
    query = Query(select=["handle"], where=In(path, [1, 2]))
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE)
    assert "json_extract(json_data, ?) IN (?, ?)" in sql
    assert params == ["$.gender", 1, 2, 50]


def test_compile_query_jsonpath_combined_with_plain_column():
    path = JsonPath(("primary_name", "first_name"))
    query = Query(select=["handle"], where=And(Eq("gender", 1), Eq(path, "Root")))
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, can_view_private=True)
    assert "gender IS NOT DISTINCT FROM ?" in sql
    assert "json_extract(json_data, ?) IS NOT DISTINCT FROM ?" in sql
    # plain-column param first, then the JsonPath's own [path, value] pair --
    # matches left-to-right order of appearance in the compiled SQL text.
    assert params == [1, "$.primary_name.first_name", "Root", 50]


def test_compile_query_jsonpath_select_params_precede_where_params():
    # SELECT appears before WHERE in the compiled SQL text, so a JsonPath in
    # `select` must contribute its params before any `where` params.
    select_path = JsonPath(("primary_name", "first_name"))
    where_path = JsonPath(("gender",))
    query = Query(select=["handle", select_path], where=Eq(where_path, 1))
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, can_view_private=True)
    assert params[0] == "$.primary_name.first_name"  # select path
    assert params[1] == "$.gender"  # where path
    assert params[2] == 1  # where value
    assert params[-1] == query.limit  # LIMIT is always last


def test_compile_count_query_jsonpath_where():
    path = JsonPath(("primary_name", "first_name"))
    sql, params = compile_count_query(
        PERSON, Query(where=Eq(path, "Root")), dialect=Dialect.SQLITE
    )
    assert sql == (
        "SELECT COUNT(*) FROM person WHERE "
        "(json_extract(json_data, ?) IS NOT DISTINCT FROM ?) AND private = 0"
    )
    assert params == ["$.primary_name.first_name", "Root"]  # no LIMIT param -- it's a COUNT


def test_compile_query_jsonpath_where_gt_numeric_postgresql_casts_to_numeric():
    # jsonb_extract_path_text always returns TEXT -- comparing TEXT with `>`
    # is lexicographic ('10' < '9'), so a numeric `value` must use the
    # non-`_text` extractor + an explicit CAST instead.
    path = JsonPath(("attribute_list", 0, "value"))
    query = Query(select=["handle"], where=Gt(path, 5))
    sql, params = compile_query(PERSON, query, dialect=Dialect.POSTGRESQL)
    assert "CAST(jsonb_extract_path(json_data::jsonb, ?, ?, ?) AS NUMERIC) > ?" in sql
    assert params == ["attribute_list", "0", "value", 5, 50]


def test_compile_query_jsonpath_where_eq_bool_postgresql_casts_to_boolean():
    path = JsonPath(("private",))
    query = Query(select=["handle"], where=Eq(path, True))
    sql, params = compile_query(PERSON, query, dialect=Dialect.POSTGRESQL, can_view_private=True)
    assert "CAST(jsonb_extract_path(json_data::jsonb, ?) AS BOOLEAN) IS NOT DISTINCT FROM ?" in sql
    assert params == ["private", True, 50]


def test_compile_query_jsonpath_where_eq_str_postgresql_stays_text():
    path = JsonPath(("primary_name", "first_name"))
    query = Query(select=["handle"], where=Eq(path, "Root"))
    sql, params = compile_query(PERSON, query, dialect=Dialect.POSTGRESQL)
    assert "jsonb_extract_path_text(json_data::jsonb, ?, ?) IS NOT DISTINCT FROM ?" in sql
    assert params == ["primary_name", "first_name", "Root", 50]


def test_compile_query_jsonpath_select_unaffected_by_value_casting():
    # SELECT entries have no comparison value -- always text extraction,
    # same as before this cast logic was added.
    path = JsonPath(("attribute_list", 0, "value"))
    sql, params = compile_query(PERSON, Query(select=[path]), dialect=Dialect.POSTGRESQL)
    assert "jsonb_extract_path_text(json_data::jsonb, ?, ?, ?)" in sql


def test_compile_query_jsonpath_where_in_numeric_postgresql_casts_to_numeric():
    path = JsonPath(("attribute_list", 0, "value"))
    query = Query(select=["handle"], where=In(path, [1, 2]))
    sql, params = compile_query(PERSON, query, dialect=Dialect.POSTGRESQL)
    assert "CAST(jsonb_extract_path(json_data::jsonb, ?, ?, ?) AS NUMERIC) IN (?, ?)" in sql
    assert params == ["attribute_list", "0", "value", 1, 2, 50]


def test_jsonpath_not_subject_to_column_whitelist():
    # JsonPath's safety comes from segment-level type checking + parameter
    # binding, not the fixed column whitelist -- any path is structurally
    # valid, unlike an unrecognized plain column name.
    path = JsonPath(("anything", "goes", "here"))
    sql, params = compile_query(PERSON, Query(select=[path]), dialect=Dialect.SQLITE)
    assert "json_extract" in sql


# --- ColumnIndex / RelatedObject / resolve_column_path -------------------------

BIRTH_DATE = resolve_column_path(PERSON, ["birth", "date"])
DEATH_DATE = resolve_column_path(PERSON, ["death", "date"])
BIRTH_DATE_SORTVAL = resolve_column_path(PERSON, ["birth", "date", "sortval"])
DEATH_DATE_SORTVAL = resolve_column_path(PERSON, ["death", "date", "sortval"])
FATHER_SURNAME = resolve_column_path(FAMILY, ["father", "surname"])
MOTHER_SURNAME = resolve_column_path(FAMILY, ["mother", "surname"])
BIRTH_PLACE_TITLE = resolve_column_path(PERSON, ["birth", "place", "title"])


def test_resolve_column_path_flat_column():
    assert resolve_column_path(PERSON, ["gender"]) == "gender"


def test_resolve_column_path_plain_json_path_no_relationship():
    result = resolve_column_path(PERSON, ["primary_name", "first_name"])
    assert result == JsonPath(("primary_name", "first_name"))


def test_resolve_column_path_empty_raises():
    with pytest.raises(QueryError):
        resolve_column_path(PERSON, [])


def test_resolve_column_path_bare_relationship_name_rejected():
    # "birth" alone isn't a value -- needs a further path.
    with pytest.raises(QueryError):
        resolve_column_path(PERSON, ["birth"])


def test_resolve_column_path_birth_date_shape():
    assert isinstance(BIRTH_DATE, RelatedObject)
    assert BIRTH_DATE.name == "birth"
    assert BIRTH_DATE.target is EVENT
    assert BIRTH_DATE.handle_ref == JsonPath(
        ("event_ref_list", ColumnIndex("birth_ref_index"), "ref")
    )
    assert BIRTH_DATE.field == JsonPath(("date",))


def test_resolve_column_path_father_surname_shape():
    # A direct foreign key (father_handle), not a dynamic index -- handle_ref
    # is a plain string, not a JsonPath.
    assert isinstance(FATHER_SURNAME, RelatedObject)
    assert FATHER_SURNAME.name == "father"
    assert FATHER_SURNAME.target is PERSON
    assert FATHER_SURNAME.handle_ref == "father_handle"
    assert FATHER_SURNAME.field == "surname"


def test_resolve_column_path_two_hop_chain():
    # birth.place.title: Person -> Event (dynamic index) -> Place (direct FK).
    assert isinstance(BIRTH_PLACE_TITLE, RelatedObject)
    assert BIRTH_PLACE_TITLE.name == "birth"
    assert BIRTH_PLACE_TITLE.target is EVENT
    inner = BIRTH_PLACE_TITLE.field
    assert isinstance(inner, RelatedObject)
    assert inner.name == "place"
    assert inner.target is PLACE
    assert inner.handle_ref == "place"
    assert inner.field == "title"


def test_resolve_column_path_no_relationships_on_place():
    # PLACE has no registered relationships -- a path through it just
    # resolves as a flat column or JsonPath, same as any other type.
    assert resolve_column_path(PLACE, ["title"]) == "title"


# --- RelatedObject rendering (select) -------------------------------------------


def test_related_object_requires_dialect():
    with pytest.raises(QueryError):
        compile_query(PERSON, Query(select=["handle", BIRTH_DATE]))


def test_related_object_not_a_relationship_on_wrong_spec_falls_through_to_json_path():
    # "birth" is only a registered relationship on Person, not Event -- on
    # Event it's just an arbitrary (harmless, matches-nothing-at-runtime)
    # JsonPath segment, not an error. Only a bare relationship name with no
    # further path is rejected (see test_resolve_column_path_bare_relationship_name_rejected).
    result = resolve_column_path(EVENT, ["birth", "date"])
    assert result == JsonPath(("birth", "date"))


def test_related_object_sqlite_shape():
    sql, params = compile_query(
        PERSON, Query(select=["handle", BIRTH_DATE], limit=10), dialect=Dialect.SQLITE
    )
    assert "FROM person" in sql
    # Correlated subquery, not a JOIN -- the outer FROM stays single-table.
    assert "JOIN" not in sql
    # The subquery's own FROM event scopes json_data unambiguously without
    # needing an explicit "event." qualifier.
    assert "SELECT json_extract(json_data, ?) FROM event" in sql
    assert "person.birth_ref_index >= 0" in sql
    assert (
        "json_extract(person.json_data, '$.event_ref_list[' || "
        "person.birth_ref_index || '].ref')" in sql
    )
    # The field extraction's own path ('$.date', parameterized via the
    # shared _render_json_path -- an improvement over the old bespoke
    # inline-literal rendering) precedes the trailing LIMIT param.
    assert params == ["$.date", 10]


def test_related_object_postgresql_shape():
    sql, params = compile_query(
        PERSON, Query(select=["handle", BIRTH_DATE], limit=10), dialect=Dialect.POSTGRESQL
    )
    assert "jsonb_extract_path_text(json_data::jsonb, ?)" in sql
    assert (
        "person.json_data::jsonb -> 'event_ref_list' -> person.birth_ref_index ->> 'ref'"
        in sql
    )
    assert "date" in params


def test_related_object_father_surname_sqlite_shape():
    # A direct FK (father_handle) needs no CASE WHEN guard at all -- NULL
    # already fails the handle equality naturally.
    sql, params = compile_query(
        FAMILY, Query(select=["handle", FATHER_SURNAME]), dialect=Dialect.SQLITE
    )
    assert "CASE WHEN" not in sql
    assert "SELECT surname FROM person WHERE person.handle = (family.father_handle)" in sql


def test_related_object_sibling_subqueries_same_table_no_conflict():
    # father and mother both correlate to "person", unaliased -- confirmed
    # live this doesn't collide since each subquery is an independent scope.
    sql, params = compile_query(
        FAMILY, Query(select=["handle", FATHER_SURNAME, MOTHER_SURNAME]), dialect=Dialect.SQLITE
    )
    assert sql.count("FROM person") == 2
    assert "family.father_handle" in sql
    assert "family.mother_handle" in sql


def test_related_object_two_hop_chain_sqlite_shape():
    sql, params = compile_query(
        PERSON, Query(select=["handle", BIRTH_PLACE_TITLE]), dialect=Dialect.SQLITE
    )
    # Nested subquery: event lookup contains a place lookup.
    assert "SELECT (SELECT title FROM place WHERE place.handle = (event.place)" in sql
    assert "FROM event WHERE event.handle = (CASE WHEN person.birth_ref_index" in sql


def test_related_object_privacy_applies_to_subquery_not_outer_query():
    # A private birth event with no view permission should make the field
    # come back null -- NOT exclude the person from the results, which a
    # top-level WHERE would incorrectly do to what's meant to be optional
    # per-row information.
    sql, params = compile_query(
        PERSON,
        Query(select=["handle", BIRTH_DATE]),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    subquery, outer_query = sql.split("FROM person")
    assert "event.private = 0" in subquery  # inside the subquery, on `event`
    assert "WHERE private = 0" in outer_query  # the outer query's own clause, on `person`


def test_related_object_treeid_applies_to_subquery():
    sql, params = compile_query(
        PERSON,
        Query(select=["handle", BIRTH_DATE, DEATH_DATE]),
        dialect=Dialect.SQLITE,
        can_view_private=True,
        treeid=7,
    )
    # Each subquery contributes its own field-extraction param ('$.date')
    # before its own treeid param, plus the outer query's own treeid clause,
    # plus the trailing LIMIT param.
    assert params == ["$.date", 7, "$.date", 7, 7, 50]
    assert sql.count("event.treeid = ?") == 2


def test_related_object_death_ref_index():
    sql, params = compile_query(
        PERSON, Query(select=["handle", DEATH_DATE]), dialect=Dialect.SQLITE
    )
    assert "person.death_ref_index >= 0" in sql
    assert "person.birth_ref_index" not in sql


def test_related_object_end_to_end_sqlite_execution():
    # Not just "does it compile" -- does it actually run correctly,
    # including picking the right event_ref_list entry (index 1, not 0)
    # via the *dynamic* per-row index, and correctly returning null for a
    # ref_index of -1 (no such event recorded).
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, birth_ref_index INTEGER, "
        "death_ref_index INTEGER, json_data TEXT)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, json_data TEXT)")
    person_json = json.dumps(
        {
            "event_ref_list": [
                {"ref": "evt-other", "role": {"value": 3}},
                {"ref": "evt-birth", "role": {"value": 1}},
            ]
        }
    )
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?, ?)", ("p1", 1, -1, person_json)
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)",
        ("evt-birth", json.dumps({"date": {"sortval": 2439857}})),
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)",
        ("evt-other", json.dumps({"date": {"sortval": 999}})),
    )

    sql, params = compile_query(
        PERSON,
        Query(select=["handle", BIRTH_DATE, DEATH_DATE], limit=10),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    row = conn.execute(sql, params).fetchone()
    assert row[0] == "p1"
    assert json.loads(row[1]) == {"sortval": 2439857}  # correct entry, index 1
    assert row[2] is None  # death_ref_index == -1


def test_related_object_father_surname_end_to_end_sqlite_execution():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE person (handle TEXT, surname TEXT)")
    conn.execute("CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT)")
    conn.execute("INSERT INTO person VALUES ('p1', 'Smith')")
    conn.execute("INSERT INTO person VALUES ('p2', 'Jones')")
    conn.execute("INSERT INTO family VALUES ('f1', 'p1', NULL)")  # father=Smith
    conn.execute("INSERT INTO family VALUES ('f2', 'p2', NULL)")  # father=Jones
    conn.execute("INSERT INTO family VALUES ('f3', NULL, NULL)")  # no father

    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(FATHER_SURNAME, "Smith")),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == [("f1",)]


# --- RelatedObject in WHERE (BIRTH_DATE_SORTVAL / DEATH_DATE_SORTVAL) -----------


def test_related_object_sortval_where_sqlite_shape():
    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Gte(BIRTH_DATE_SORTVAL, 2439857)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    assert "JOIN" not in sql
    assert "json_extract(json_data, ?)" in sql
    assert params == ["$.date.sortval", 2439857, 50]


def test_related_object_sortval_where_postgresql_numeric_cast():
    # Same numeric-cast correctness issue JsonPath already had: ->>'sortval'
    # is TEXT on PostgreSQL, which compares lexicographically, not
    # numerically -- must use -> + CAST(...AS NUMERIC) for a Gte/Lt/etc.
    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Gte(BIRTH_DATE_SORTVAL, 2439857)),
        dialect=Dialect.POSTGRESQL,
        can_view_private=True,
    )
    assert "CAST(jsonb_extract_path(json_data::jsonb, ?, ?) AS NUMERIC)" in sql
    assert "jsonb_extract_path_text" not in sql
    assert params[:2] == ["date", "sortval"]


def test_related_object_sortval_select_unaffected_by_where_addition():
    # BIRTH_DATE (select, whole struct) must render exactly as before --
    # value=None still takes the original (non-cast) code path.
    sql, params = compile_query(
        PERSON, Query(select=["handle", BIRTH_DATE]), dialect=Dialect.POSTGRESQL
    )
    assert "jsonb_extract_path_text(json_data::jsonb, ?)" in sql
    assert "CAST" not in sql


def test_related_object_sortval_range_query():
    query = Query(
        select=["handle"],
        where=And(Gte(BIRTH_DATE_SORTVAL, 2439857), Lt(BIRTH_DATE_SORTVAL, 2440222)),
    )
    sql, params = compile_query(PERSON, query, dialect=Dialect.SQLITE, can_view_private=True)
    assert sql.count("SELECT json_extract(json_data, ?) FROM event") == 2
    assert params == ["$.date.sortval", 2439857, "$.date.sortval", 2440222, 50]


def test_related_object_sortval_treeid_scoping():
    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Gte(BIRTH_DATE_SORTVAL, 2439857)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
        treeid=7,
    )
    assert "event.treeid = ?" in sql
    assert 7 in params


def test_related_object_sortval_end_to_end_sqlite_execution():
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, birth_ref_index INTEGER, json_data TEXT)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, json_data TEXT)")
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("p1", 0, json.dumps({"event_ref_list": [{"ref": "e1"}]})),
    )
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("p2", 0, json.dumps({"event_ref_list": [{"ref": "e2"}]})),
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)",
        ("e1", json.dumps({"date": {"sortval": 2439857}})),  # 1968 -- matches
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)",
        ("e2", json.dumps({"date": {"sortval": 2415021}})),  # 1900 -- doesn't
    )
    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Gte(BIRTH_DATE_SORTVAL, 2439857)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == [("p1",)]


# --- Field-vs-field comparisons (e.g. "mother died before father") -------------

MOTHER_DEATH_SORTVAL = resolve_column_path(FAMILY, ["mother", "death", "date", "sortval"])
FATHER_DEATH_SORTVAL = resolve_column_path(FAMILY, ["father", "death", "date", "sortval"])


def test_field_vs_field_sqlite_shape():
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Lt(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    assert "JOIN" not in sql
    # Both sides are independently-rendered correlated subqueries, joined
    # by the operator directly -- no ? placeholder between them.
    assert sql.count("SELECT (SELECT json_extract(json_data, ?)") == 2
    assert "family.mother_handle" in sql
    assert "family.father_handle" in sql
    assert " < " in sql
    assert params == ["$.date.sortval", "$.date.sortval", 50]


def test_field_vs_field_postgresql_numeric_cast_both_sides():
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Lt(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.POSTGRESQL,
        can_view_private=True,
    )
    # Ordering comparison between two paths: both sides get the numeric
    # cast (via a dummy int hint, since there's no literal runtime value
    # to infer it from) -- not the default TEXT extraction, which would
    # compare lexicographically.
    assert sql.count("CAST(jsonb_extract_path(json_data::jsonb, ?, ?) AS NUMERIC)") == 2
    assert "jsonb_extract_path_text" not in sql


def test_field_vs_field_equality_stays_text_both_sides():
    # Eq/Ne don't need the numeric-cast hint -- exact TEXT match is correct
    # regardless of whether the underlying value is numeric or textual, as
    # long as both sides extract the same way (they do).
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.POSTGRESQL,
        can_view_private=True,
    )
    assert sql.count("jsonb_extract_path_text(json_data::jsonb, ?, ?)") == 2
    assert "CAST" not in sql


def test_field_vs_field_two_hop_chain():
    # birth.place.title compared against a literal still works fine
    # alongside field-vs-field elsewhere -- confirms the two mechanisms
    # (field-vs-value and field-vs-field) don't interfere.
    birth_place_title = resolve_column_path(PERSON, ["birth", "place", "title"])
    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Eq(birth_place_title, "Chicago")),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    assert params[-2:] == ["Chicago", 50]


def test_field_vs_field_privacy_and_treeid_apply_independently_to_each_side():
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Lt(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=False,
        treeid=7,
    )
    # Each side's Event *and* Person subqueries get their own privacy/treeid
    # clause (2 chains x 2 hops = 4), plus the outer family query's own
    # (Family has a private column too) -- 5 of each, confirmed live rather
    # than assumed.
    assert sql.count("private = 0") == 5
    assert sql.count("treeid = ?") == 5


def test_field_vs_field_end_to_end_sqlite_execution():
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, death_ref_index INTEGER, json_data TEXT)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, json_data TEXT)")
    conn.execute("CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT)")

    # f1: mother died 1950 (earlier), father died 1980 (later) -- mother < father matches
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("mom1", 0, json.dumps({"event_ref_list": [{"ref": "mom1_death"}]})),
    )
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("dad1", 0, json.dumps({"event_ref_list": [{"ref": "dad1_death"}]})),
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)", ("mom1_death", json.dumps({"date": {"sortval": 2433283}}))
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)", ("dad1_death", json.dumps({"date": {"sortval": 2444239}}))
    )
    conn.execute("INSERT INTO family VALUES (?, ?, ?)", ("f1", "dad1", "mom1"))

    # f2: mother died 1990 (later), father died 1960 (earlier) -- doesn't match
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("mom2", 0, json.dumps({"event_ref_list": [{"ref": "mom2_death"}]})),
    )
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("dad2", 0, json.dumps({"event_ref_list": [{"ref": "dad2_death"}]})),
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)", ("mom2_death", json.dumps({"date": {"sortval": 2447893}}))
    )
    conn.execute(
        "INSERT INTO event VALUES (?, ?)", ("dad2_death", json.dumps({"date": {"sortval": 2436935}}))
    )
    conn.execute("INSERT INTO family VALUES (?, ?, ?)", ("f2", "dad2", "mom2"))

    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Lt(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == [("f1",)]


# --- NULL-safe equality (`=`/`!=` -> IS [NOT] DISTINCT FROM) ------------------
#
# Plain SQL `=`/`!=` use three-valued logic: if either side is NULL, the
# comparison is UNKNOWN, not TRUE or FALSE -- so a row where one side is
# missing satisfies neither `eq` nor `ne`. That's a sharp edge for
# field-vs-field comparisons specifically: "born and died in different
# places" (`birth.place.title != death.place.title`) should include "died
# in an unknown place", not silently drop it. `Eq`/`Ne` render as
# `IS [NOT] DISTINCT FROM` instead -- NULL-safe, so NULL is a normal,
# comparable value (NULL IS DISTINCT FROM 'x' is true; NULL IS DISTINCT
# FROM NULL is false) -- for both literal and field-vs-field comparisons.


def test_eq_ne_render_as_null_safe_distinct():
    sql, _ = compile_query(PERSON, Query(select=["handle"], where=Eq("gender", 1)))
    assert "gender IS NOT DISTINCT FROM ?" in sql
    assert "gender = ?" not in sql

    sql, _ = compile_query(PERSON, Query(select=["handle"], where=Ne("gender", 1)))
    assert "gender IS DISTINCT FROM ?" in sql
    assert "gender != ?" not in sql


def test_field_vs_field_eq_ne_render_as_null_safe_distinct():
    sql, _ = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    # The two correlated subqueries are joined directly by the top-level
    # operator, e.g. "...LIMIT 1) IS NOT DISTINCT FROM (SELECT..." -- check
    # that specific join, not just "IS NOT DISTINCT FROM" appearing
    # somewhere (the subqueries' own internal `handle = ...` correlations
    # are unrelated `=` uses that must NOT be affected by this rewrite).
    assert ") IS NOT DISTINCT FROM (SELECT" in sql

    sql, _ = compile_query(
        FAMILY,
        Query(select=["handle"], where=Ne(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    assert ") IS DISTINCT FROM (SELECT" in sql
    assert "!=" not in sql


def test_ordering_and_like_and_in_ops_unaffected_by_null_safe_rewrite():
    # Only `=`/`!=` (Eq/Ne) get the NULL-safe rewrite -- ordering operators
    # have no natural NULL-safe equivalent in standard SQL, and In/Like are
    # unrelated classes that don't go through Comparison.compile() at all
    # (In) or use their own fixed `LIKE` operator (Like).
    for op_cls, op_text in [(Lt, "<"), (Lte, "<="), (Gt, ">"), (Gte, ">=")]:
        sql, _ = compile_query(PERSON, Query(select=["handle"], where=op_cls("gender", 1)))
        assert f"gender {op_text} ?" in sql

    sql, _ = compile_query(PERSON, Query(select=["handle"], where=Like("surname", "A%")))
    assert "surname LIKE ?" in sql

    sql, _ = compile_query(PERSON, Query(select=["handle"], where=In("gender", [1, 2])))
    assert "gender IN (?, ?)" in sql


def test_null_safe_equality_end_to_end_sqlite_execution():
    # Direct proof that the NULL-safe rewrite actually changes matched rows,
    # not just the SQL text: a family where only one side's death date is
    # recorded is included by Ne (distinct: a real value vs. NULL) and
    # excluded by Eq; a family where *neither* side's death date is
    # recorded is excluded by Ne (NULL is not distinct from NULL) and
    # included by Eq.
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, death_ref_index INTEGER, json_data TEXT)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, json_data TEXT)")
    conn.execute("CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT)")

    # f3: mother's death is recorded, father's is not (death_ref_index -1,
    # "no such event") -- one side NULL, one side a real value.
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?)",
        ("mom3", 0, json.dumps({"event_ref_list": [{"ref": "mom3_death"}]})),
    )
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad3", -1, json.dumps({})))
    conn.execute(
        "INSERT INTO event VALUES (?, ?)", ("mom3_death", json.dumps({"date": {"sortval": 2433283}}))
    )
    conn.execute("INSERT INTO family VALUES (?, ?, ?)", ("f3", "dad3", "mom3"))

    # f4: neither side's death is recorded -- both NULL.
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("mom4", -1, json.dumps({})))
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad4", -1, json.dumps({})))
    conn.execute("INSERT INTO family VALUES (?, ?, ?)", ("f4", "dad4", "mom4"))

    ne_sql, ne_params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Ne(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    eq_sql, eq_params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(MOTHER_DEATH_SORTVAL, FATHER_DEATH_SORTVAL)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    ne_rows = {row[0] for row in conn.execute(ne_sql, ne_params).fetchall()}
    eq_rows = {row[0] for row in conn.execute(eq_sql, eq_params).fetchall()}

    assert "f3" in ne_rows  # one side missing -> distinct -> matches Ne
    assert "f3" not in eq_rows
    assert "f4" not in ne_rows  # both sides missing -> not distinct -> matches Eq
    assert "f4" in eq_rows


# --- Privacy guard on NULL-safe equality --------------------------------------
#
# Privacy masks a private related row's field to NULL by excluding it from
# its own subquery's WHERE (see _render_related_object) -- fine for select,
# but combined with NULL-safe Eq/Ne, a masked NULL would otherwise
# participate in the comparison as if it were genuinely missing data,
# letting an unprivileged caller learn a true/false fact about hidden data
# (verified live: two masked fields compared "equal"; one masked field
# compared to a literal it didn't match compared "not equal"). Eq/Ne now
# add a visibility guard for any RelatedObject side that crosses a
# privacy-bearing relationship, excluding the row entirely rather than
# letting a masked value participate.

FATHER_SURNAME_2 = resolve_column_path(FAMILY, ["father", "surname"])
MOTHER_SURNAME = resolve_column_path(FAMILY, ["mother", "surname"])
BIRTH_PLACE_TITLE = resolve_column_path(PERSON, ["birth", "place", "title"])
DEATH_PLACE_TITLE = resolve_column_path(PERSON, ["death", "place", "title"])


def test_privacy_guard_added_for_eq_ne_without_view_private_permission():
    sql, _ = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(FATHER_SURNAME_2, MOTHER_SURNAME)),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    assert sql.count("COALESCE((") == 2  # one visibility guard per side
    assert "CASE WHEN person.private = 1 THEN 0 ELSE 1 END" in sql


def test_privacy_guard_omitted_when_caller_can_view_private():
    sql, _ = compile_query(
        FAMILY,
        Query(select=["handle"], where=Eq(FATHER_SURNAME_2, MOTHER_SURNAME)),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    assert "COALESCE(" not in sql
    assert "CASE WHEN" not in sql


def test_privacy_guard_not_added_for_ordering_ops():
    # Lt/Lte/Gt/Gte weren't made NULL-safe, so a privacy-masked NULL
    # already excludes the row via standard three-valued logic -- no guard
    # needed, and none should be added.
    sql, _ = compile_query(
        FAMILY,
        Query(select=["handle"], where=Lt(FATHER_SURNAME_2, MOTHER_SURNAME)),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    assert "COALESCE(" not in sql
    assert "CASE WHEN" not in sql


def test_privacy_guard_end_to_end_sqlite_execution():
    # Direct proof the guard changes matched rows, not just the SQL text --
    # reproduces the exact scenario found live: two people with genuinely
    # different surnames, both marked private.
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE person (handle TEXT, surname TEXT, private INTEGER)")
    conn.execute(
        "CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT, private INTEGER)"
    )
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad1", "Smith", 1))
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("mom1", "Jones", 1))
    conn.execute("INSERT INTO family VALUES (?, ?, ?, ?)", ("f1", "dad1", "mom1", 0))

    for op_cls, expect_match_unprivileged in [(Eq, False), (Ne, False)]:
        # With permission: Smith != Jones, so Eq never matches, Ne always does.
        sql, params = compile_query(
            FAMILY,
            Query(select=["handle"], where=op_cls(FATHER_SURNAME_2, MOTHER_SURNAME)),
            dialect=Dialect.SQLITE,
            can_view_private=True,
        )
        privileged_rows = conn.execute(sql, params).fetchall()
        assert (len(privileged_rows) == 1) == (op_cls is Ne)

        # Without permission: both sides masked to NULL -- must be excluded
        # from BOTH Eq and Ne, not read as "equal" or "not equal".
        sql, params = compile_query(
            FAMILY,
            Query(select=["handle"], where=op_cls(FATHER_SURNAME_2, MOTHER_SURNAME)),
            dialect=Dialect.SQLITE,
            can_view_private=False,
        )
        unprivileged_rows = conn.execute(sql, params).fetchall()
        assert (len(unprivileged_rows) == 1) is expect_match_unprivileged


def test_privacy_guard_field_vs_literal_end_to_end_sqlite_execution():
    # The narrower, more dangerous case: a single masked field compared to
    # a literal it genuinely DOES match -- != must not assert "different"
    # about data the caller was never shown.
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE person (handle TEXT, surname TEXT, private INTEGER)")
    conn.execute(
        "CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT, private INTEGER)"
    )
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad1", "Smith", 1))
    conn.execute("INSERT INTO family VALUES (?, ?, ?, ?)", ("f1", "dad1", None, 0))

    for op_cls in (Eq, Ne):
        sql, params = compile_query(
            FAMILY,
            Query(select=["handle"], where=op_cls(FATHER_SURNAME_2, "Smith")),
            dialect=Dialect.SQLITE,
            can_view_private=False,
        )
        rows = conn.execute(sql, params).fetchall()
        assert rows == [], f"{op_cls.__name__} incorrectly matched a privacy-masked field"


def test_privacy_guard_two_hop_chain_correlates_correctly():
    # Regression test: an earlier version of this guard emitted a flat,
    # top-level clause per hop instead of nesting each hop's guard inside
    # its parent's own subquery scope -- for a 2-hop chain like
    # birth.place.title, the second hop's guard referenced "event.place"
    # with no "event" table in the outer query's FROM at all, raising
    # "no such column: event.place" the moment it was actually executed
    # (a pure SQL-string test wouldn't have caught this -- only runs it).
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, birth_ref_index INTEGER, death_ref_index INTEGER, "
        "json_data TEXT, private INTEGER)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, place TEXT, private INTEGER)")
    conn.execute("CREATE TABLE place (handle TEXT, title TEXT, private INTEGER)")

    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?, ?, ?)",
        ("p1", 0, 1, json.dumps({"event_ref_list": [{"ref": "birth1"}, {"ref": "death1"}]}), 0),
    )
    conn.execute("INSERT INTO event VALUES (?, ?, ?)", ("birth1", "place1", 0))
    conn.execute("INSERT INTO event VALUES (?, ?, ?)", ("death1", "place2", 0))
    conn.execute("INSERT INTO place VALUES (?, ?, ?)", ("place1", "Chicago", 0))
    conn.execute("INSERT INTO place VALUES (?, ?, ?)", ("place2", "Chicago", 0))

    sql, params = compile_query(
        PERSON,
        Query(select=["handle"], where=Eq(BIRTH_PLACE_TITLE, DEATH_PLACE_TITLE)),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    rows = conn.execute(sql, params).fetchall()  # must not raise
    assert rows == [("p1",)]  # both places visible and equal ("Chicago")

    # Now mark the death place private -- the chain crosses a
    # privacy-bearing hop 2 levels down, must still correctly block.
    conn.execute("UPDATE place SET private = 1 WHERE handle = 'place2'")
    rows = conn.execute(sql, params).fetchall()
    assert rows == []  # blocked, not silently treated as still matching


def test_privacy_guard_does_not_block_genuinely_missing_data():
    # A chain that bottoms out at a handle with no matching row at all
    # (not privacy -- just nothing recorded) must NOT be blocked by the
    # guard -- only an *existing*, privacy-blocked row should be.
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE person (handle TEXT, death_ref_index INTEGER, json_data TEXT, private INTEGER)"
    )
    conn.execute("CREATE TABLE event (handle TEXT, json_data TEXT, private INTEGER)")
    conn.execute("CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT, private INTEGER)")

    # mother: death recorded, not private. father: no death event at all.
    conn.execute(
        "INSERT INTO person VALUES (?, ?, ?, ?)",
        ("mom1", 0, json.dumps({"event_ref_list": [{"ref": "mom1_death"}]}), 0),
    )
    conn.execute("INSERT INTO event VALUES (?, ?, ?)", ("mom1_death", json.dumps({"date": {"sortval": 100}}), 0))
    conn.execute("INSERT INTO person VALUES (?, ?, ?, ?)", ("dad1", -1, json.dumps({}), 0))
    conn.execute("INSERT INTO family VALUES (?, ?, ?, ?)", ("f1", "dad1", "mom1", 0))

    mother_death_sortval = resolve_column_path(FAMILY, ["mother", "death", "date", "sortval"])
    father_death_sortval = resolve_column_path(FAMILY, ["father", "death", "date", "sortval"])
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Ne(mother_death_sortval, father_death_sortval)),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    rows = conn.execute(sql, params).fetchall()
    # father's death is genuinely missing (not privacy-blocked) -- NULL-safe
    # Ne should still fire normally: a real value vs. genuinely-missing is
    # "distinct".
    assert rows == [("f1",)]


# --- Privacy guard survives boolean composition (Not/And/Or) -----------------
#
# The guard must render as SQL NULL (unknown) when blocked, not a hardcoded
# FALSE -- an earlier version used `(guard) AND (comparison)`, which
# evaluates to a definite FALSE when blocked; wrapping that in Not(...)
# then flips it to TRUE (NOT FALSE = TRUE), silently re-opening the exact
# leak this guard exists to close, just reached via Not(Eq(...)) instead of
# Ne(...) directly. SQL's own three-valued logic already handles NULL
# propagating correctly through NOT/AND/OR -- expressing "blocked" as NULL
# (via CASE WHEN <guard> THEN <comparison> ELSE NULL END) needs no
# per-combinator special-casing to get this right.


def test_privacy_guard_survives_not_wrapping():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE person (handle TEXT, surname TEXT, private INTEGER)")
    conn.execute(
        "CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT, private INTEGER)"
    )
    # Father is private, and his real surname genuinely IS "Smith".
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad1", "Smith", 1))
    conn.execute("INSERT INTO family VALUES (?, ?, ?, ?)", ("f1", "dad1", None, 0))

    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Not(Eq(FATHER_SURNAME_2, "Smith"))),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    rows = conn.execute(sql, params).fetchall()
    # Must stay excluded -- NOT("unknown, blocked by privacy") is still
    # unknown, never a confident "yes, it's not Smith".
    assert rows == []

    # With permission, this should behave normally: Smith == Smith, so
    # Not(Eq(...)) is Not(True) -> excluded (same result, different reason
    # -- proves the guard isn't just unconditionally suppressing the row).
    sql, params = compile_query(
        FAMILY,
        Query(select=["handle"], where=Not(Eq(FATHER_SURNAME_2, "Smith"))),
        dialect=Dialect.SQLITE,
        can_view_private=True,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == []


def test_privacy_guard_or_lets_a_visible_sibling_still_confirm_a_match():
    # An Or() branch that's privacy-blocked shouldn't suppress a sibling
    # branch that's independently visible and genuinely true -- "blocked"
    # should behave like SQL NULL here: `NULL OR TRUE` is TRUE.
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE person (handle TEXT, surname TEXT, private INTEGER)")
    conn.execute(
        "CREATE TABLE family (handle TEXT, father_handle TEXT, mother_handle TEXT, private INTEGER)"
    )
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("dad1", "Smith", 1))  # private
    conn.execute("INSERT INTO person VALUES (?, ?, ?)", ("mom1", "Jones", 0))  # visible, matches
    conn.execute("INSERT INTO family VALUES (?, ?, ?, ?)", ("f1", "dad1", "mom1", 0))

    sql, params = compile_query(
        FAMILY,
        Query(
            select=["handle"],
            where=Or(Eq(FATHER_SURNAME_2, "Smith"), Eq(MOTHER_SURNAME, "Jones")),
        ),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == [("f1",)]  # mother's branch alone confirms the match

    # But if the visible sibling is genuinely false too, blocked OR false
    # stays unknown -- must not match.
    sql, params = compile_query(
        FAMILY,
        Query(
            select=["handle"],
            where=Or(Eq(FATHER_SURNAME_2, "Smith"), Eq(MOTHER_SURNAME, "NotJones")),
        ),
        dialect=Dialect.SQLITE,
        can_view_private=False,
    )
    rows = conn.execute(sql, params).fetchall()
    assert rows == []


def test_compile_query_uses_spec_table_and_columns():
    query = Query(select=["handle", "father_handle"])
    sql, _ = compile_query(FAMILY, query)
    assert "FROM family" in sql
    assert "father_handle" in sql


def test_compile_query_emits_logical_column_names():
    # query.py has no column-override mechanism: it always emits columns
    # exactly as `get_secondary_fields()` names them, on every backend.
    query = Query(select=["handle", "description"])
    sql, _ = compile_query(EVENT, query)
    assert "description" in sql
    assert "desc_ription" not in sql


def test_legacy_shared_postgresql_hack_self_corrects_logical_names():
    # SharedPostgreSQL's not-yet-migrated Connection.execute() still runs a
    # blind "desc" -> "desc_" string-replace on every query it receives (see
    # query.py's module-level note; verified live against a real deployed
    # instance). Confirm the plain logical names query.py emits become the
    # real physical column names after exactly one such pass -- so no
    # compensating override is needed here (adding one double-corrupts:
    # "desc_ription" -> "desc__ription", confirmed the hard way).
    def legacy_hack(sql: str) -> str:
        return sql.replace("desc", "desc_")

    sql, _ = compile_query(EVENT, Query(select=["handle", "description"]))
    assert "desc_ription" in legacy_hack(sql)

    sql, _ = compile_query(MEDIA, Query(select=["handle", "desc"]))
    # quoting survives the hack too: '"desc"' -> '"desc_"', still correct.
    assert '"desc_"' in legacy_hack(sql)


def test_text_columns_exclude_non_string_fields():
    # gender/change/private etc. are integer/boolean secondary fields --
    # not eligible for a locale COLLATE clause.
    assert {"surname", "given_name", "gramps_id", "handle"} <= PERSON.text_columns
    assert "gender" not in PERSON.text_columns
    assert "private" not in PERSON.text_columns
    assert "change" not in PERSON.text_columns


def test_no_collate_clause_without_collation_argument():
    query = Query(select=["handle"], order_by=[OrderBy("surname", "asc")])
    sql, _ = compile_query(PERSON, query)
    assert "COLLATE" not in sql


def test_collate_applied_to_text_order_by_columns():
    query = Query(select=["handle"], order_by=[OrderBy("surname", "asc")])
    sql, _ = compile_query(PERSON, query, collation="de_DE")
    assert 'surname COLLATE "de_DE" ASC' in sql
    # trailing handle tiebreaker is also text -- also collated
    assert 'handle COLLATE "de_DE" ASC' in sql


def test_collate_not_applied_to_non_text_order_by_columns():
    query = Query(select=["handle"], order_by=[OrderBy("gender", "asc")])
    sql, _ = compile_query(PERSON, query, collation="de_DE")
    assert "gender COLLATE" not in sql
    assert "gender ASC" in sql


def test_collate_applied_to_keyset_comparisons_for_text_columns():
    query = Query(
        select=["handle"],
        order_by=[OrderBy("surname", "desc"), OrderBy("gender", "asc")],
        after=("Smith", 1, "h123"),
    )
    sql, params = compile_query(PERSON, query, collation="de_DE")
    assert 'surname COLLATE "de_DE" < ?' in sql
    assert 'surname COLLATE "de_DE" = ?' in sql
    assert "gender > ?" in sql
    assert "gender COLLATE" not in sql
    assert 'handle COLLATE "de_DE" > ?' in sql
    assert params == ["Smith", "Smith", 1, "Smith", 1, "h123", 50]


def test_unknown_column_in_where_rejected():
    query = Query(where=Eq("; DROP TABLE person; --", 1))
    with pytest.raises(QueryError):
        compile_query(PERSON, query)


def test_unknown_column_in_select_rejected():
    query = Query(select=["handle", "not_a_real_column"])
    with pytest.raises(QueryError):
        compile_query(PERSON, query)


def test_unknown_column_in_order_by_rejected():
    query = Query(order_by=[OrderBy("not_a_real_column")])
    with pytest.raises(QueryError):
        compile_query(PERSON, query)


def test_simple_eq_compiles_with_bound_param():
    query = Query(select=["handle"], where=Eq("gender", 1))
    sql, params = compile_query(PERSON, query)
    assert "gender IS NOT DISTINCT FROM ?" in sql
    assert params[0] == 1
    # the value is bound as a parameter, never interpolated into the SQL text
    where_clause = sql.split("WHERE", 1)[1]
    assert "?" in where_clause and "1" not in where_clause


def test_privacy_clause_added_by_default():
    query = Query(select=["handle"])
    sql, params = compile_query(PERSON, query)
    assert "private = 0" in sql


def test_privacy_clause_omitted_with_view_private_permission():
    query = Query(select=["handle"])
    sql, params = compile_query(PERSON, query, can_view_private=True)
    assert "private = 0" not in sql


def test_privacy_clause_not_omittable_via_where():
    # Even a maximally permissive user-supplied WHERE can't remove the
    # baked-in privacy predicate.
    query = Query(select=["handle"], where=Or(Eq("private", 0), Eq("private", 1)))
    sql, params = compile_query(PERSON, query)
    assert "private = 0" in sql


def test_and_or_not_compile_and_combine_params():
    query = Query(
        select=["handle"],
        where=And(Eq("gender", 1), Or(Like("surname", "A%"), Not(Eq("surname", "")))),
    )
    sql, params = compile_query(PERSON, query)
    assert "AND" in sql
    assert "OR" in sql
    assert "NOT" in sql
    assert 1 in params
    assert "A%" in params
    assert "" in params


def test_in_requires_at_least_one_value():
    with pytest.raises(QueryError):
        In("gender", [])


def test_in_compiles_placeholders():
    query = Query(select=["handle"], where=In("gender", [0, 1]))
    sql, params = compile_query(PERSON, query)
    assert "gender IN (?, ?)" in sql
    assert params[:2] == [0, 1]


def test_default_select_is_all_whitelisted_columns():
    query = Query()
    sql, _ = compile_query(PERSON, query)
    select_clause = sql.split(" FROM ")[0]
    for column in PERSON.columns:
        assert column in select_clause


def test_order_by_gets_trailing_handle_tiebreaker():
    query = Query(select=["handle"], order_by=[OrderBy("surname", "asc")])
    sql, _ = compile_query(PERSON, query)
    assert "ORDER BY surname ASC, handle ASC" in sql


def test_order_by_does_not_duplicate_explicit_handle():
    query = Query(
        select=["handle"],
        order_by=[OrderBy("surname", "asc"), OrderBy("handle", "desc")],
    )
    sql, _ = compile_query(PERSON, query)
    order_by_clause = sql.split("ORDER BY", 1)[1]
    assert order_by_clause.startswith(" surname ASC, handle DESC")
    assert order_by_clause.count("handle") == 1  # not duplicated


def test_default_order_by_is_handle_only():
    query = Query(select=["handle"])
    sql, _ = compile_query(PERSON, query)
    assert "ORDER BY handle ASC" in sql


def test_limit_appended_as_param():
    query = Query(select=["handle"], limit=25)
    sql, params = compile_query(PERSON, query)
    assert sql.rstrip().endswith("LIMIT ?")
    assert params[-1] == 25


def test_non_positive_limit_rejected():
    with pytest.raises(QueryError):
        Query(limit=0)
    with pytest.raises(QueryError):
        Query(limit=-5)


def test_after_columns_matches_effective_order_by():
    assert after_columns([OrderBy("surname", "asc")]) == ("surname", "handle")
    assert after_columns([]) == ("handle",)
    assert after_columns([OrderBy("handle", "desc")]) == ("handle",)


def test_after_wrong_length_rejected():
    query = Query(
        select=["handle"], order_by=[OrderBy("surname", "asc")], after=("Smith",)
    )
    with pytest.raises(QueryError):
        compile_query(PERSON, query)


def test_keyset_pagination_single_column_asc():
    query = Query(
        select=["handle"],
        order_by=[OrderBy("surname", "asc")],
        after=("Smith", "h123"),
    )
    sql, params = compile_query(PERSON, query)
    assert "surname > ?" in sql
    assert "Smith" in params
    assert "h123" in params


def test_keyset_pagination_mixed_directions_seek_expansion():
    query = Query(
        select=["handle"],
        order_by=[OrderBy("surname", "desc"), OrderBy("given_name", "asc")],
        after=("Smith", "Alice", "h123"),
    )
    sql, params = compile_query(PERSON, query)
    # OR-of-ANDs seek expansion, not a row-constructor comparison, so mixed
    # asc/desc directions stay correct.
    assert "surname < ?" in sql
    assert "given_name > ?" in sql
    assert "handle > ?" in sql
    assert sql.index("OR") > 0


def test_and_or_require_at_least_one_expr():
    with pytest.raises(QueryError):
        And()
    with pytest.raises(QueryError):
        Or()
