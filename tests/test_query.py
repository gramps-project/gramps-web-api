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
    TAG,
    And,
    Dialect,
    Eq,
    Gt,
    In,
    JsonPath,
    Like,
    Not,
    Or,
    OrderBy,
    Query,
    QueryError,
    after_columns,
    compile_count_query,
    compile_query,
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
    assert sql == "SELECT COUNT(*) FROM person WHERE (gender = ?) AND private = 0"
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
    assert "json_extract(json_data, ?) = ?" in sql
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
    assert "gender = ?" in sql
    assert "json_extract(json_data, ?) = ?" in sql
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
    assert sql == "SELECT COUNT(*) FROM person WHERE (json_extract(json_data, ?) = ?) AND private = 0"
    assert params == ["$.primary_name.first_name", "Root"]  # no LIMIT param -- it's a COUNT


def test_jsonpath_not_subject_to_column_whitelist():
    # JsonPath's safety comes from segment-level type checking + parameter
    # binding, not the fixed column whitelist -- any path is structurally
    # valid, unlike an unrecognized plain column name.
    path = JsonPath(("anything", "goes", "here"))
    sql, params = compile_query(PERSON, Query(select=[path]), dialect=Dialect.SQLITE)
    assert "json_extract" in sql


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
    assert "gender = ?" in sql
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
