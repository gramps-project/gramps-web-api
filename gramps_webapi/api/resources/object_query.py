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

"""Fast, SQL-pushed-down structured query endpoints, one per object type.

`Person` was the first type wired up; every other type shares the exact same
request/response shape and wiring (`ObjectQueryResource`), differing only in
which `query.ObjectTypeSpec` a subclass binds to via its `spec` class
attribute -- the same pattern `GrampsObjectResourceHelper` subclasses already
use with `gramps_class_name` (see `resources/people.py`/`families.py`).
"""

from typing import Any, Optional, Sequence, Tuple

from gramps.gen.proxy import PrivateProxyDb
from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.plugins.db.dbapi.sqlite import SQLite
from marshmallow import Schema, validate
from webargs import fields as wf

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..blueprint import api_blueprint
from ..query import (
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
    after_columns,
    check_columns,
    compile_count_query,
    compile_query,
)
from ..query_lang import QueryLangError, parse_expr_for_spec
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
            "'gramps_id'), or {'json_path': [...]} to compare a path into the "
            "JSON blob, e.g. {'json_path': ['primary_name', 'first_name']}."
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
        required=True,
        metadata={
            "description": "Value to compare against. Must be a list when op is 'in'."
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
            "'as': '<key>'} to select a path into the JSON blob, e.g. "
            "{'json_path': ['primary_name', 'surname_list', 0, 'surname']}. "
            "'as' is optional; if omitted, the response key is a derived "
            "dotted/bracket string, e.g. 'primary_name.surname_list[0].surname'."
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


def _parse_json_path(raw: dict) -> JsonPath:
    segments = raw.get("json_path")
    if not isinstance(segments, list) or not segments:
        raise QueryError("'json_path' must be a non-empty list")
    return JsonPath(tuple(segments))


def _parse_column_ref(raw: Any) -> ColumnRef:
    """Parse a `where` condition's `column`: a plain column name, or
    `{"json_path": [...]}` for a `JsonPath`. Segment-level type checking
    (str keys / non-bool int indices only) happens in `JsonPath.__post_init__`.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and "json_path" in raw:
        return _parse_json_path(raw)
    raise QueryError(f"invalid column reference: {raw!r}")


def _parse_select_entry(raw: Any) -> Tuple[ColumnRef, str]:
    """Parse one `select` entry into `(column_ref, response_key)`.

    A plain string is both the column and its own response key. A
    `{"json_path": [...], "as": "..."}` object uses `as` as the response key
    if given, otherwise a derived dotted/bracket path
    (`_json_path_default_key`). `as: "handle"` is rejected unless the entry
    *is* the real `handle` column -- the response's `handle` key is
    load-bearing for the `next_after` cursor (see `post()`), so silently
    shadowing it with unrelated JSON content would corrupt pagination for
    the caller without any visible error.
    """
    if isinstance(raw, str):
        return raw, raw
    if isinstance(raw, dict) and "json_path" in raw:
        path = _parse_json_path(raw)
        key = raw.get("as") or _json_path_default_key(path)
        if key == "handle":
            raise QueryError("'handle' is reserved as a response key")
        return path, key
    raise QueryError(f"invalid column reference: {raw!r}")


def _json_path_default_key(path: JsonPath) -> str:
    """Dotted/bracket string built from a `JsonPath`'s segments -- the
    response key for a `select` entry with no explicit `as` alias.
    """
    parts = []
    for segment in path.segments:
        if isinstance(segment, int):
            parts.append(f"[{segment}]")
        else:
            parts.append(f".{segment}" if parts else str(segment))
    return "".join(parts)


def _check_no_duplicate_keys(parsed_select: Sequence[Tuple[ColumnRef, str]]) -> None:
    seen: set = set()
    for _, key in parsed_select:
        if key in seen:
            raise QueryError(f"duplicate select key: {key!r}")
        seen.add(key)


def _build_where(conditions: Optional[Sequence[dict]]):
    """Build a `query.py` WHERE expression from parsed leaf conditions."""
    if not conditions:
        return None
    exprs: list[Any] = []
    for condition in conditions:
        column = _parse_column_ref(condition["column"])
        op = condition["op"]
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
    can_view_private: bool,
    treeid: Optional[int] = None,
):
    """Resolve a client-supplied `after=<handle>` cursor into a value tuple.

    The sort-column values for the cursor row aren't known to the client, so
    the handle it supplies has to be looked up first. Columns were already
    validated by the caller, so this is safe to interpolate.

    `treeid`, when given, restricts the lookup to the caller's own tree (see
    `_resolve_treeid`) -- without it, a handle from any other tree on a
    shared multi-tree backend would resolve just as well, leaking that row's
    column values (and confirming the handle's existence) across tenants
    even though the main paginated query stays properly scoped.
    """
    columns = after_columns(order_by)
    sql = f"SELECT {', '.join(columns)} FROM {spec.table} WHERE handle = ?"
    params: list = [after_handle]
    if spec.has_privacy and not can_view_private:
        sql += " AND private = 0"
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
    """Fast, paged/filtered/sorted query over one object type, pushed down to SQL.

    Bypasses Gramps object deserialization entirely: rows are read directly
    from the database's flat secondary columns (see `spec.columns`), never
    materialized as Gramps objects. Only available on database backends
    exposing a `.dbapi` SQL execution capability (all currently supported
    backends). Subclasses set `spec` to one of `query.py`'s per-type
    `ObjectTypeSpec` instances; everything else is shared.
    """

    spec: ObjectTypeSpec

    @api_blueprint.response(200, ObjectQueryResponseSchema())
    @api_blueprint.arguments(QueryBodyArgs, location="json")
    def post(self, args: dict) -> Any:
        """Run a structured, SQL-pushed-down query."""
        db = get_db_handle(readonly=True)
        if isinstance(db, ProxyDbBase) and not isinstance(db, PrivateProxyDb):
            # Only `PrivateProxyDb` (and `ModifiedPrivateProxyDb`) is safe to
            # bypass: this compiler independently reimplements its exact
            # filtering (`AND private = 0`) in SQL. Any other proxy (e.g.
            # `LivingProxyDb`, `FilterProxyDb`) applies filtering with no SQL
            # equivalent here -- querying the raw database underneath it
            # would silently return exactly the data that proxy exists to
            # hide. `get_db_handle()` never constructs anything else today,
            # but this must not be assumed; refuse rather than risk a data
            # leak if that ever changes.
            abort_with_message(
                501, "Structured query is not supported through this proxy database"
            )
        basedb = db.basedb if isinstance(db, ProxyDbBase) else db
        if not hasattr(basedb, "dbapi"):
            abort_with_message(
                501, "Structured query is not supported on this database backend"
            )
        treeid = _resolve_treeid(basedb)

        can_view_private = has_permissions({PERM_VIEW_PRIVATE})

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
            after = _resolve_after(
                basedb, self.spec, order_by, args["after"], can_view_private, treeid
            )

        # `default=False`, deliberately: falling back to the system locale
        # here would apply COLLATE to every request, silently changing sort
        # order for callers who never asked for locale-aware sorting.
        # Locale-aware sorting is opt-in via an explicit `locale` param.
        locale = get_locale_for_language(args.get("locale"), default=False)
        collation = _resolve_collation(basedb, locale) if locale is not None else None

        dialect = _resolve_dialect(basedb)
        try:
            parsed_select = (
                [_parse_select_entry(item) for item in args["select"]]
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
                where=_build_where(_resolve_where_conditions(args, self.spec)),
                order_by=order_by,
                limit=args["limit"],
                after=after,
            )
            sql, params = compile_query(
                self.spec,
                query,
                can_view_private=can_view_private,
                collation=collation,
                dialect=dialect,
                treeid=treeid,
            )
            count_sql, count_params = (
                compile_count_query(
                    self.spec,
                    query,
                    can_view_private=can_view_private,
                    dialect=dialect,
                    treeid=treeid,
                )
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
        items = [
            {key: val for key, val in zip(fetch_keys, row) if key in requested_keys}
            for row in rows
        ]
        next_after = rows[-1][handle_index] if len(rows) == args["limit"] else None

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
