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

"""Structured query endpoints, one per object type.

Two execution paths, dispatched on whether `get_db_handle()` returns a
proxy (`ObjectQueryResource.post`): unproxied requests get `query.py`'s
fast, SQL-pushed-down compiler (`_post_sql`); proxied requests run through
Gramps' own `Filter`/`Rule` machinery instead (`_post_proxied`, see
`proxied_query.py`) so privacy (or any other proxy-applied rule, current or
future) comes from the proxy itself rather than a second, SQL-side
reimplementation of it. Both share the same request/response shape.

`Person` was the first type wired up; every other type shares the exact same
wiring (`ObjectQueryResource`), differing only in which
`query.ObjectTypeSpec` a subclass binds to via its `spec` class attribute --
the same pattern `GrampsObjectResourceHelper` subclasses already use with
`gramps_class_name` (see `resources/people.py`/`families.py`).
"""

import json
from typing import Any, Callable, Optional, Sequence, Tuple

from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.plugins.db.dbapi.sqlite import SQLite
from marshmallow import Schema, validate
from webargs import fields as wf

from gramps_object_query_language.evaluator import (
    GETTER_BY_TABLE,
    get_flat_column,
    resolve_column_ref,
)
from gramps_object_query_language.proxied_query import run_query
from gramps_object_query_language.query import (
    CITATION,
    EVENT,
    FAMILY,
    MEDIA,
    NOTE,
    PERSON,
    PLACE,
    REPOSITORY,
    SOURCE,
    TAG,
    And,
    ColumnRef,
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
    ObjectTypeSpec,
    OrderBy,
    Query,
    QueryError,
    RelatedObject,
    SelectRef,
    after_columns,
    check_columns,
    compile_count_query,
    compile_query,
    resolve_column_path,
)
from gramps_object_query_language.query_lang import QueryLangError, parse_expr_for_spec

from ..blueprint import api_blueprint
from ..util import abort_with_message, get_db_handle, get_locale_for_language
from . import ProtectedResource
from .schemas import ObjectQueryResponseSchema

_OP_TO_EXPR = {
    "eq": Eq,
    "ne": Ne,
    "lt": Lt,
    "lte": Lte,
    "gt": Gt,
    "gte": Gte,
    "like": Like,
}


class QueryWhereConditionArgs(Schema):
    """A single WHERE leaf condition."""

    column = wf.Raw(
        required=True,
        metadata={
            "description": "Column to compare: either a plain column name (e.g. "
            "'gramps_id'), or {'json_path': [...]} for a path, e.g. "
            "{'json_path': ['primary_name', 'first_name']}. A path may cross a "
            "relationship (Family->Person, Person->Event, Event->Place, ...), "
            "e.g. {'json_path': ['father', 'surname']} or "
            "{'json_path': ['birth', 'date', 'sortval']}."
        },
    )
    op = wf.Str(
        required=True,
        validate=validate.OneOf(list(_OP_TO_EXPR) + ["in"]),
        metadata={
            "description": "Comparison operator: eq, ne, lt, lte, gt, gte, like, or in."
        },
    )
    value = wf.Raw(
        required=False,
        metadata={
            "description": "Value to compare against. Must be a list when op is "
            "'in'. Mutually exclusive with 'value_column'; exactly one is required."
        },
    )
    value_column = wf.Raw(
        required=False,
        metadata={
            "description": "Alternative to 'value': compare 'column' against "
            "another column/path instead of a literal, e.g. families where the "
            "mother died before the father -- column: {'json_path': ['mother', "
            "'death', 'date', 'sortval']}, op: 'lt', value_column: {'json_path': "
            "['father', 'death', 'date', 'sortval']}. Same shape as 'column' "
            "(plain name or {'json_path': [...]}). Not supported for 'in'/'like'."
        },
    )


class QueryOrderByArgs(Schema):
    """A single ORDER BY column."""

    column = wf.Str(required=True, metadata={"description": "Column to sort by."})
    direction = wf.Str(
        load_default="asc",
        validate=validate.OneOf(["asc", "desc"]),
        metadata={"description": "Sort direction: 'asc' or 'desc'."},
    )


class QueryBodyArgs(Schema):
    """Body arguments shared by every `POST .../query/` endpoint."""

    select = wf.List(
        wf.Raw(),
        required=False,
        metadata={
            "description": "Columns to return. Defaults to all available columns. "
            "Each entry is either a plain column name, or {'json_path': [...], "
            "'as': '<key>'} to select a path, e.g. "
            "{'json_path': ['primary_name', 'surname_list', 0, 'surname']}. "
            "'as' is optional; if omitted, the response key is a derived "
            "dotted/bracket string, e.g. 'primary_name.surname_list[0].surname'. "
            "A path may cross a relationship (Family->Person via 'father'/"
            "'mother', Person->Event via 'birth'/'death', Event->Place via "
            "'place'), e.g. {'json_path': ['father', 'surname']} or "
            "{'json_path': ['birth', 'date']} (the full Date struct -- "
            "format/calendar/modifier/quality/dateval/text/sortval -- of the "
            "referenced event, or null if none is recorded). Not usable in "
            "'order_by'."
        },
    )
    where = wf.List(
        wf.Nested(QueryWhereConditionArgs),
        required=False,
        metadata={"description": "Leaf conditions, implicitly combined with AND."},
    )
    where_expr = wf.Str(
        required=False,
        allow_none=True,
        metadata={
            "description": "Alternative to `where`: an \"almost Python\" expression, "
            "e.g. \"gender == 1 and primary_name.surname_list[0].surname == 'Smith'\". "
            "See `query_lang.py`. Mutually exclusive with `where` -- a request "
            "setting both is rejected."
        },
    )
    order_by = wf.List(
        wf.Nested(QueryOrderByArgs),
        required=False,
        metadata={"description": "Sort order, most significant column first."},
    )
    limit = wf.Int(
        load_default=50,
        validate=validate.Range(min=1, max=1000),
        metadata={"description": "Maximum number of rows to return."},
    )
    after = wf.Str(
        required=False,
        allow_none=True,
        metadata={
            "description": "Cursor from a previous response's `next_after`, for "
            "keyset pagination. Omit for the first page."
        },
    )
    locale = wf.Str(
        load_default=None,
        validate=validate.Length(min=1, max=5),
        metadata={
            "description": "Language code for locale-aware sorting of text columns "
            "(e.g. 'de', 'fr'). Affects ORDER BY only, not filtering."
        },
    )
    count = wf.Boolean(
        load_default=False,
        metadata={
            "description": "If true, also compute the total number of rows matching "
            "`where` (and privacy), independent of `limit`/`after`, and return it "
            "in the `X-Total-Count` response header (the same convention used "
            "elsewhere in this API). Costs a second query, so it's opt-in."
        },
    )


def _parse_column_ref(raw: Any, spec: ObjectTypeSpec) -> ColumnRef:
    """Parse a `where` condition's `column`: a plain column name, or
    `{"json_path": [...]}` resolved via `resolve_column_path()` -- which
    may cross a relationship (`{"json_path": ["birth", "date", "sortval"]}`)
    or stay a plain `JsonPath` into `json_data`, depending on whether the
    first segment(s) name a registered relationship on `spec`. A bare
    string is *not* run through the relationship resolver -- there's
    nothing to disambiguate for a single segment beyond "is this a real
    flat column", which `_render_column` already checks at compile time.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and "json_path" in raw:
        segments = raw["json_path"]
        if not isinstance(segments, list) or not segments:
            raise QueryError("'json_path' must be a non-empty list")
        return resolve_column_path(spec, segments)
    raise QueryError(f"invalid column reference: {raw!r}")


def _parse_select_entry(raw: Any, spec: ObjectTypeSpec) -> Tuple[SelectRef, str]:
    """Parse one `select` entry into `(column_ref, response_key)`.

    A plain string is both the column and its own response key. A
    `{"json_path": [...], "as": "..."}` object resolves the path the same
    way `_parse_column_ref` does (relationship-aware), and uses `as` as
    the response key if given, otherwise a derived dotted/bracket path
    (`_default_key_for`). `as: "handle"` is rejected unless the entry *is*
    the real `handle` column -- the response's `handle` key is
    load-bearing for the `next_after` cursor (see `post()`), so silently
    shadowing it with unrelated content would corrupt pagination for the
    caller without any visible error.
    """
    if isinstance(raw, str):
        return raw, raw
    if isinstance(raw, dict) and "json_path" in raw:
        column = _parse_column_ref(raw, spec)
        key = raw.get("as") or _default_key_for(column)
        if key == "handle":
            raise QueryError("'handle' is reserved as a response key")
        return column, key
    raise QueryError(f"invalid column reference: {raw!r}")


def _default_key_for(ref: ColumnRef) -> str:
    """Derive a default response key for a `select` entry with no explicit
    `as` alias -- a dotted/bracket string, e.g. `primary_name.surname_list[0]`
    for a plain `JsonPath`, or `birth.date.sortval` for a `RelatedObject`
    chain (recursing through `.field` and prefixing each hop's `.name`).
    """
    if isinstance(ref, str):
        return ref
    if isinstance(ref, RelatedObject):
        return f"{ref.name}.{_default_key_for(ref.field)}"
    parts: list = []
    for segment in ref.segments:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        else:
            parts.append(f".{segment}" if parts else str(segment))
    return "".join(parts)


def _check_no_duplicate_keys(parsed_select: Sequence[Tuple[SelectRef, str]]) -> None:
    seen: set = set()
    for _, key in parsed_select:
        if key in seen:
            raise QueryError(f"duplicate select key: {key!r}")
        seen.add(key)


def _sort_key(value: Any) -> Tuple[bool, Any]:
    """Sort key treating `None` (missing/masked) as sorting first in
    ascending order -- `(False, ...) < (True, ...)` regardless of `value`'s
    own type, and two `None`s compare equal without ever needing `value`
    itself to support `<` against `None`. Used only by `_post_proxied`;
    the SQL path's `ORDER BY` has its own (backend-native) NULL ordering.
    """
    return (value is not None, value)


def _sort_key_for_column(
    column: str, spec: ObjectTypeSpec
) -> Callable[[Any], Tuple[bool, Any]]:
    """A `list.sort(key=...)` callable for `column`, bound via closure rather
    than a lambda's default-argument trick -- mypy can't infer the type of a
    `lambda obj, c=column: ...` used as a sort key (`Cannot infer type of
    lambda`), since the extra defaulted parameter breaks its unification
    with `list.sort`'s expected single-argument callable.
    """

    def key(obj: Any) -> Tuple[bool, Any]:
        return _sort_key(get_flat_column(obj, column, spec))

    return key


def _terminal_is_json_path(ref: ColumnRef) -> bool:
    """Does `ref` ultimately extract via a `JsonPath` (as opposed to a
    plain flat column)? Recurses through a `RelatedObject` chain to its
    leaf `field` -- `father.surname` ends in a plain column (a real SQL
    column on `person`, no JSON functions involved at all), `birth.date`/
    `birth.date.sortval` end in a `JsonPath` (`json_extract`/`->` on
    PostgreSQL, `-> `SQLite`). Used to decide which response values need
    `_normalize_json_value`'s SQLite-string-vs-PostgreSQL-dict handling --
    a plain column's value is never JSON-encoded, so applying that
    normalization there could wrongly reinterpret e.g. a surname that
    happens to look like a JSON literal (`"123"`).
    """
    if isinstance(ref, RelatedObject):
        return _terminal_is_json_path(ref.field)
    return isinstance(ref, JsonPath)


def _normalize_json_value(value: Any) -> Any:
    """Normalize a JSON-sourced response value to its parsed form either way.

    SQLite's `json_extract()` returns a JSON *string* for object/array
    results (scalars come back already correctly typed); PostgreSQL's
    `jsonb` expressions come back through psycopg2 already parsed
    (verified live against both). `None` (no such row, or it's private and
    the caller can't view it) passes through unchanged. Only applied to
    response values whose `ColumnRef` is `_terminal_is_json_path()` --
    see there.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _build_where(conditions: Optional[Sequence[dict]], spec: ObjectTypeSpec):
    """Build a `query.py` WHERE expression from parsed leaf conditions.

    Each condition carries exactly one of `value` (a literal) or
    `value_column` (another path, for a field-vs-field comparison, e.g.
    "families where the mother died before the father") -- validated here
    since webargs' per-field `required=` can't express "exactly one of
    these two", the same reason `where`/`where_expr` mutual exclusivity is
    checked in `_resolve_where_conditions` rather than the schema.
    """
    if not conditions:
        return None
    exprs: list[Any] = []
    for condition in conditions:
        column = _parse_column_ref(condition["column"], spec)
        op = condition["op"]
        has_value = "value" in condition
        has_value_column = "value_column" in condition
        if has_value == has_value_column:
            abort_with_message(
                422, "exactly one of 'value'/'value_column' is required"
            )
        if has_value_column:
            if op in ("in", "like"):
                abort_with_message(
                    422, f"'value_column' is not supported for op {op!r}"
                )
            value = _parse_column_ref(condition["value_column"], spec)
        else:
            value = condition["value"]
        if op == "in":
            if not isinstance(value, list) or not value:
                abort_with_message(422, "'in' operator requires a non-empty list value")
            exprs.append(In(column, value))
        else:
            exprs.append(_OP_TO_EXPR[op](column, value))
    if len(exprs) == 1:
        return exprs[0]
    return And(*exprs)


def _resolve_where_conditions(
    args: dict, spec: ObjectTypeSpec
) -> Optional[Sequence[dict]]:
    """Get the leaf-condition list to feed `_build_where`, from `where` or `where_expr`.

    Mutually exclusive: a request setting both is rejected rather than
    defining merge semantics nobody asked for. `where_expr` is parsed
    directly against `spec` (`parse_expr_for_spec`, not the namespace-string
    `parse_expr`) -- the endpoint already knows its own type from `self.spec`,
    so asking the client to also name it via a namespace string would be
    redundant.
    """
    if args.get("where") and args.get("where_expr"):
        abort_with_message(422, "'where' and 'where_expr' are mutually exclusive")
    if args.get("where_expr"):
        try:
            return parse_expr_for_spec(spec, args["where_expr"])
        except QueryLangError as error:
            abort_with_message(422, str(error))
    return args.get("where")


def _resolve_after(
    basedb: Any,
    spec: ObjectTypeSpec,
    order_by: Sequence[OrderBy],
    after_handle: str,
    treeid: Optional[int] = None,
):
    """Resolve a client-supplied `after=<handle>` cursor into a value tuple.

    The sort-column values for the cursor row aren't known to the client, so
    the handle it supplies has to be looked up first. Columns were already
    validated by the caller, so this is safe to interpolate. Only ever
    called from `_post_sql`, which only ever runs against an unproxied
    database -- no privacy predicate needed here (see `query.py`'s module
    docstring).

    `treeid`, when given, restricts the lookup to the caller's own tree (see
    `_resolve_treeid`) -- without it, a handle from any other tree on a
    shared multi-tree backend would resolve just as well, leaking that row's
    column values (and confirming the handle's existence) across tenants
    even though the main paginated query stays properly scoped.
    """
    columns = after_columns(order_by)
    sql = f"SELECT {', '.join(columns)} FROM {spec.table} WHERE handle = ?"
    params: list = [after_handle]
    if treeid is not None:
        sql += " AND treeid = ?"
        params.append(treeid)
    basedb.dbapi.execute(sql, params)
    row = basedb.dbapi.fetchone()
    if row is None:
        abort_with_message(422, "Invalid 'after' cursor")
    return tuple(row)


def _resolve_collation(basedb: Any, locale: Any) -> Optional[str]:
    """Ensure the requested locale's collation exists, returning its name.

    Mirrors gramps core's own `DBAPI._collation()` (used internally for
    `get_person_handles(sort_handles=True, locale=...)`): call the backend
    connection's `check_collation()`, which creates the collation if needed
    and (on SQLite) returns the sanitized name it was registered under.
    `SharedPostgreSQL`'s `check_collation()` doesn't return a name, so fall
    back to the locale's raw collation name in that case -- Postgres, unlike
    SQLite, needs no sanitization for `CREATE COLLATION`.

    Returns `None` (no `COLLATE` clause; default ordering) if the backend's
    connection object has no `check_collation` at all.
    """
    if not hasattr(basedb.dbapi, "check_collation"):
        return None
    return basedb.dbapi.check_collation(locale) or locale.get_collation()


_DIALECT_BY_NAME: dict[str, Dialect] = {
    "sqlite": Dialect.SQLITE,
    "postgres": Dialect.POSTGRESQL,
    "postgresql": Dialect.POSTGRESQL,
}


def _resolve_dialect(basedb: Any) -> Dialect:
    """Backend SQL dialect for rendering a `JsonPath` (see `query.py`).

    Core `DBAPI`/`SQLite` and the `SharedPostgreSQL` addon don't advertise a
    `.dialect` attribute yet (proposed but unmerged core-side,
    gramps-project/gramps#2178); the single-user `PostgreSQL` addon already
    does (`dialect = "postgresql"`), so that case is read straight off
    `basedb` when present. Otherwise: `SQLite` (core-provided) is detected
    directly -- it's what every test fixture and single-tree/dev deployment
    actually runs, so guessing PostgreSQL for it would emit
    `jsonb_extract_path(...)` against a real SQLite connection and fail
    outright, not just sort wrong. Anything else (`SharedPostgreSQL`) falls
    back to PostgreSQL, since that's the only other backend this project
    targets today.
    """
    name: Optional[str] = getattr(basedb, "dialect", None)
    if name:
        dialect = _DIALECT_BY_NAME.get(name)
        if dialect is not None:
            return dialect
    if isinstance(basedb, SQLite):
        return Dialect.SQLITE
    return Dialect.POSTGRESQL


def _resolve_treeid(basedb: Any) -> Optional[int]:
    """Current tree's integer ID, for shared multi-tree backends only.

    `SharedPostgreSQL` stores every tree's rows together in the same
    physical tables, discriminated by a `treeid` column that's part of
    every object table's primary key. Nothing applies that filter
    automatically at the connection/execute level -- every one of
    `SharedDBAPI`'s own query methods (`get_person_handles`, etc.) adds
    `WHERE treeid = ?` by hand. Any raw SQL issued directly against
    `.dbapi`, as this compiler and `util.py`'s `_iter_handles()` both do,
    MUST add it too, or it silently returns rows from every tree sharing
    the instance -- not just the caller's own.

    Returns `None` for single-tree-per-database backends (`SQLite`, the
    single-user `PostgreSQL` addon), which have no `treeid` column at all
    -- `compile_query`/`compile_count_query`/`_resolve_after` all treat
    `None` as "omit the clause", not "unscoped is fine by default".
    """
    return getattr(basedb.dbapi, "treeid", None)


class ObjectQueryResource(ProtectedResource):
    """Paged/filtered/sorted query over one object type.

    Unproxied: fast, pushed down to SQL, bypassing Gramps object
    deserialization entirely -- rows are read directly from the database's
    flat secondary columns (see `spec.columns`), never materialized as
    Gramps objects. See `_post_sql`.

    Proxied: slower, routed through Gramps' own `Filter`/`Rule` machinery
    instead, so every object is deserialized and sanitized by the proxy the
    normal way. See `_post_proxied`.

    Subclasses set `spec` to one of `query.py`'s per-type `ObjectTypeSpec`
    instances; everything else is shared.
    """

    spec: ObjectTypeSpec

    @api_blueprint.response(200, ObjectQueryResponseSchema())
    @api_blueprint.arguments(QueryBodyArgs, location="json")
    def post(self, args: dict) -> Any:
        """Run a structured query."""
        db = get_db_handle(readonly=True)
        if isinstance(db, ProxyDbBase):
            # Privacy (and any future proxy-applied rule) comes from `db`
            # itself here, not from a second, SQL-side reimplementation of
            # it -- see `proxied_query.py`'s module docstring. Not fast,
            # but correct for whatever proxy this is, current or future,
            # with nothing in this module needing to know its rules.
            return self._post_proxied(db, args)
        return self._post_sql(db, args)

    def _post_sql(self, basedb: Any, args: dict) -> Any:
        """Fast, SQL-pushed-down query -- only ever called with an unproxied
        `basedb`, so there is no privacy predicate to apply here at all.
        """
        if not hasattr(basedb, "dbapi"):
            abort_with_message(
                501, "Structured query is not supported on this database backend"
            )
        treeid = _resolve_treeid(basedb)

        order_by = [
            OrderBy(item["column"], item.get("direction", "asc"))
            for item in args.get("order_by") or []
        ]
        try:
            check_columns((ob.column for ob in order_by), self.spec)
        except QueryError as error:
            abort_with_message(422, str(error))

        after = None
        if args.get("after"):
            after = _resolve_after(basedb, self.spec, order_by, args["after"], treeid)

        # `default=False`, deliberately: falling back to the system locale
        # here would apply COLLATE to every request, silently changing sort
        # order for callers who never asked for locale-aware sorting.
        # Locale-aware sorting is opt-in via an explicit `locale` param.
        locale = get_locale_for_language(args.get("locale"), default=False)
        collation = _resolve_collation(basedb, locale) if locale is not None else None

        dialect = _resolve_dialect(basedb)
        try:
            parsed_select = (
                [_parse_select_entry(item, self.spec) for item in args["select"]]
                if args.get("select")
                else [(col, col) for col in sorted(self.spec.columns)]
            )
            _check_no_duplicate_keys(parsed_select)
            fetch_refs = [ref for ref, _ in parsed_select]
            fetch_keys = [key for _, key in parsed_select]
            if not any(ref == "handle" for ref in fetch_refs):
                fetch_refs = fetch_refs + ["handle"]
                fetch_keys = fetch_keys + ["handle"]
            requested_keys = {key for _, key in parsed_select}

            query = Query(
                select=fetch_refs,
                where=_build_where(_resolve_where_conditions(args, self.spec), self.spec),
                order_by=order_by,
                limit=args["limit"],
                after=after,
            )
            sql, params = compile_query(
                self.spec,
                query,
                collation=collation,
                dialect=dialect,
                treeid=treeid,
            )
            count_sql, count_params = (
                compile_count_query(self.spec, query, dialect=dialect, treeid=treeid)
                if args["count"]
                else (None, None)
            )
        except QueryError as error:
            abort_with_message(422, str(error))

        basedb.dbapi.execute(sql, params)
        rows = basedb.dbapi.fetchall()

        headers = {}
        if count_sql is not None:
            basedb.dbapi.execute(count_sql, count_params)
            headers["X-Total-Count"] = str(basedb.dbapi.fetchone()[0])

        handle_index = fetch_refs.index("handle")
        json_path_terminal_keys = {
            key for ref, key in zip(fetch_refs, fetch_keys) if _terminal_is_json_path(ref)
        }
        items = [
            {
                key: (
                    _normalize_json_value(val) if key in json_path_terminal_keys else val
                )
                for key, val in zip(fetch_keys, row)
                if key in requested_keys
            }
            for row in rows
        ]
        next_after = rows[-1][handle_index] if len(rows) == args["limit"] else None

        return {"items": items, "next_after": next_after}, 200, headers

    def _post_proxied(self, db: Any, args: dict) -> Any:
        """Same request/response contract as `_post_sql`, but for a proxied
        `db` -- runs through Gramps' own `Filter`/`Rule` machinery
        (`proxied_query.run_query`) instead of SQL. Every candidate is
        deserialized and tested in Python (no SQL push-down, no keyset
        narrowing before that happens), so this is intentionally not fast --
        see `proxied_query.py`'s module docstring.

        `order_by` is only ever a flat top-level column (`OrderBy.column`
        never carries a `JsonPath`/`RelatedObject` -- see `query.py`), so
        sorting real objects here needs only `evaluator.get_flat_column`,
        never the full `resolve_column_ref` recursion `select` needs.
        Locale-aware `COLLATE` sorting (the SQL path's `locale` param) has
        no equivalent here yet -- this path always sorts in plain Python
        `<` order, regardless of `locale`.
        """
        order_by = [
            OrderBy(item["column"], item.get("direction", "asc"))
            for item in args.get("order_by") or []
        ]
        try:
            check_columns((ob.column for ob in order_by), self.spec)
            where = _build_where(_resolve_where_conditions(args, self.spec), self.spec)
            parsed_select = (
                [_parse_select_entry(item, self.spec) for item in args["select"]]
                if args.get("select")
                else [(col, col) for col in sorted(self.spec.columns)]
            )
            _check_no_duplicate_keys(parsed_select)
        except QueryError as error:
            abort_with_message(422, str(error))

        fetch_refs = [ref for ref, _ in parsed_select]
        fetch_keys = [key for _, key in parsed_select]
        if not any(ref == "handle" for ref in fetch_refs):
            fetch_refs = fetch_refs + ["handle"]
            fetch_keys = fetch_keys + ["handle"]
        requested_keys = {key for _, key in parsed_select}

        matches = run_query(db, self.spec, where)

        sort_columns = after_columns(order_by)  # tie-broken with 'handle'
        directions = {ob.column: ob.direction for ob in order_by}
        for column in reversed(sort_columns):
            matches.sort(
                key=lambda obj, c=column: _sort_key(get_flat_column(obj, c, self.spec)),
                reverse=directions.get(column, "asc") == "desc",
            )

        total_count = len(matches)

        start = 0
        if args.get("after"):
            getter = getattr(db, GETTER_BY_TABLE[self.spec.table])
            after_obj = getter(args["after"])
            if after_obj is None:
                abort_with_message(422, "Invalid 'after' cursor")
            for index, obj in enumerate(matches):
                if obj.handle == after_obj.handle:
                    start = index + 1
                    break
            else:
                # The cursor handle exists (through `db`) but isn't a member
                # of this exact `matches` set -- e.g. `where` narrowed since
                # the cursor was issued. Same "invalid" outcome as a handle
                # that doesn't resolve at all; a stale cursor isn't a
                # resumable position either way.
                abort_with_message(422, "Invalid 'after' cursor")

        limit = args["limit"]
        page = matches[start : start + limit]
        next_after = page[-1].handle if len(page) == limit else None

        headers = {}
        if args["count"]:
            headers["X-Total-Count"] = str(total_count)

        items = [
            {
                key: resolve_column_ref(db, obj, ref, self.spec)
                for ref, key in zip(fetch_refs, fetch_keys)
                if key in requested_keys
            }
            for obj in page
        ]

        return {"items": items, "next_after": next_after}, 200, headers


class PersonQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Person query. See `ObjectQueryResource`."""

    spec = PERSON


class FamilyQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Family query. See `ObjectQueryResource`."""

    spec = FAMILY


class EventQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Event query. See `ObjectQueryResource`."""

    spec = EVENT


class PlaceQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Place query. See `ObjectQueryResource`."""

    spec = PLACE


class RepositoryQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Repository query. See `ObjectQueryResource`."""

    spec = REPOSITORY


class SourceQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Source query. See `ObjectQueryResource`."""

    spec = SOURCE


class CitationQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Citation query. See `ObjectQueryResource`."""

    spec = CITATION


class MediaQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Media query. See `ObjectQueryResource`."""

    spec = MEDIA


class NoteQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Note query. See `ObjectQueryResource`."""

    spec = NOTE


class TagQueryResource(ObjectQueryResource):
    """Fast, paged/filtered/sorted Tag query. See `ObjectQueryResource`."""

    spec = TAG
