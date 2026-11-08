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

from typing import Any, Optional, Sequence, Tuple

from gramps.gen.errors import HandleError
from gramps.gen.proxy.proxybase import ProxyDbBase
from marshmallow import Schema, validate
from webargs import fields as wf

from gramps_object_query_language.evaluator import (
    GETTER_BY_TABLE,
    RawDataReader,
    resolve_column_ref,
)
from gramps_object_query_language.proxied_query import run_query_with_total
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
    Dialect,
    ObjectTypeSpec,
    OrderBy,
    Query,
    QueryError,
    SelectRef,
    after_columns,
    compile_after_lookup,
    compile_count_query,
    compile_query,
    resolve_order_by,
    select_normalizer,
)
from gramps_object_query_language.query_lang import (
    QueryLangError,
    compile_expr_for_spec,
    parse_select_entry,
)

from ...auth.const import PERM_VIEW_PRIVATE
from ..access import RestrictedDb
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import abort_with_message, get_db_handle, get_locale_for_language
from . import ProtectedResource
from .db_backend import (
    SHARED_POSTGRES_CLASS_NAME,
    SINGLE_TREE_POSTGRES_CLASS_NAME,
    is_sqlite,
    resolve_collation,
)
from .schemas import ObjectQueryResponseSchema


class QueryOrderByArgs(Schema):
    """A single ORDER BY column."""

    column = wf.Str(
        required=True,
        metadata={
            "description": "Column to sort by: a flat column name ('surname'), "
            "or a path ('birth.date.sortval', "
            "'primary_name.surname_list[0].surname'), resolved exactly as the "
            "same text is in 'select'. Note the cost: flat columns like "
            "'surname' and 'given_name' are indexed, while nothing indexes "
            "inside a record, so sorting by a path reads and parses every row "
            "in the tree, and a relationship path ('birth.date.sortval') adds a "
            "lookup per row on top. That work repeats for every page. Fine for "
            "a result set 'where_expr' has already narrowed; slow as the default "
            "order of a large tree."
        },
    )
    direction = wf.Str(
        load_default="asc",
        validate=validate.OneOf(["asc", "desc"]),
        metadata={"description": "Sort direction: 'asc' or 'desc'."},
    )


class QueryBodyArgs(Schema):
    """Body arguments shared by every `POST .../query/` endpoint."""

    select = wf.List(
        wf.Str(),
        required=False,
        metadata={
            "description": "Columns to return. Defaults to all available columns. "
            "Each entry is a column name ('gramps_id'), a path "
            "('primary_name.surname_list[0].surname'), or "
            "count(relationship[, condition]) ('count(events)'), each optionally "
            "followed by 'as <key>' to name it in the response, e.g. "
            "'birth.place.title as birthplace' or 'count(events) as n_events'. "
            "Without 'as', the response key is the expression's own text. "
            "A path may cross a relationship (Family->Person via 'father'/"
            "'mother', Person->Event via 'birth'/'death', Event->Place via "
            "'place', Citation->Source via 'source', Place->Place via "
            "'enclosed_by'), e.g. 'father.surname' or 'birth.date' (the full "
            "Date struct -- format/calendar/modifier/quality/dateval/text/"
            "sortval -- of the referenced event, or null if none is recorded). "
            "Every path is checked against Gramps' own schema for the type: an "
            "unknown field is a 422 naming the fields that exist, not a column "
            "of nulls. The same paths work in 'order_by' -- see there for the "
            "cost."
        },
    )
    where_expr = wf.Str(
        required=False,
        allow_none=True,
        metadata={
            "description": 'Which rows to return: an "almost Python" expression, '
            "e.g. \"gender == Person.MALE and surname == 'Smith'\". The grammar "
            "is gramps-object-query-language's; see its docs/where_expr.md. "
            "Omitted, every row is returned."
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
            "`where_expr` (and privacy), independent of `limit`/`after`, and return it "
            "in the `X-Total-Count` response header (the same convention used "
            "elsewhere in this API). Costs a second query, so it's opt-in."
        },
    )


def _parse_select_entry(raw: str, spec: ObjectTypeSpec) -> Tuple[SelectRef, str]:
    """Parse one `select` entry into `(column_ref, response_key)`, using
    `query_lang.parse_select_entry`: a flat column (`gramps_id`), a path
    (`birth.place.title`, `primary_name.surname_list[0].surname`), or a
    `count(relationship[, condition])` call, each optionally followed by
    `as <key>`.

    `as handle` is rejected unless the entry *is* the real `handle` column
    -- the response's `handle` key is what `next_after` is read from (see
    `post()`), so shadowing it would break pagination without any visible
    error.
    """
    try:
        column, key = parse_select_entry(spec, raw)
    except QueryLangError as error:
        raise QueryError(str(error)) from error
    _check_response_key(key, column)
    return column, key


def _check_response_key(key: str, column: SelectRef) -> None:
    """`handle` is reserved as a response key for anything that isn't the
    real `handle` column -- `post()` reads the cursor for `next_after` out
    of that key, so shadowing it would corrupt the caller's pagination with
    no visible error.
    """
    if key == "handle" and column != "handle":
        raise QueryError("'handle' is reserved as a response key")


def _check_no_duplicate_keys(parsed_select: Sequence[Tuple[SelectRef, str]]) -> None:
    seen: set = set()
    for _, key in parsed_select:
        if key in seen:
            raise QueryError(f"duplicate select key: {key!r}")
        seen.add(key)


def _build_where(args: dict, spec: ObjectTypeSpec):
    """Compile `where_expr`, if given, into a `query.py` WHERE expression.

    The parsing and translation are all GOQL's (`compile_expr_for_spec`);
    the endpoint already knows its own type from `self.spec`, so the client
    doesn't name it again.
    """
    where_expr = args.get("where_expr")
    if not where_expr:
        return None
    try:
        return compile_expr_for_spec(spec, where_expr)
    except (QueryLangError, QueryError) as error:
        abort_with_message(422, str(error))


def _resolve_after(
    basedb: Any,
    spec: ObjectTypeSpec,
    order_by: Sequence[OrderBy],
    after_handle: str,
    treeid: Optional[int] = None,
    dialect: Optional[Dialect] = None,
):
    """Resolve a client-supplied `after=<handle>` cursor into a value tuple.

    The sort-column values for the cursor row aren't known to the client, so
    the handle it supplies has to be looked up first. Compiled by
    `compile_after_lookup` rather than assembled here: a sort column may be
    a path (`birth.date.sortval`), which is a correlated subquery carrying
    bound parameters, not a name that can be interpolated into a `SELECT`
    list. Only ever called from `_post_sql`, which only ever runs against an
    unproxied database -- no privacy predicate needed here (see `query.py`'s
    module docstring).

    `treeid`, when given, restricts the lookup to the caller's own tree (see
    `_resolve_treeid`) -- without it, a handle from any other tree on a
    shared multi-tree backend would resolve just as well, leaking that row's
    column values (and confirming the handle's existence) across tenants
    even though the main paginated query stays properly scoped.
    """
    try:
        sql, params = compile_after_lookup(
            spec, order_by, after_handle, dialect=dialect, treeid=treeid
        )
    except QueryError as error:
        abort_with_message(422, str(error))
    basedb.dbapi.execute(sql, params)
    row = basedb.dbapi.fetchone()
    if row is None:
        abort_with_message(422, "Invalid 'after' cursor")
    return tuple(row)


def _resolve_after_proxied(
    db: Any, spec: ObjectTypeSpec, order_by: Sequence[OrderBy], after_handle: str
) -> Tuple[Any, ...]:
    """`_resolve_after`'s evaluator-path counterpart: resolves a client-
    supplied `after=<handle>` cursor into the same value-tuple shape
    (`after_columns(order_by)`), but by fetching the real (possibly
    proxied) object through `db` and reading its columns via
    `resolve_column_ref`, rather than a raw SQL lookup -- so a masked/
    sanitized value is used the same way it would be for any other row
    `run_query` evaluates, consistent with this path never running a
    second, unproxied query behind the caller's back.
    """
    getter = getattr(db, GETTER_BY_TABLE[spec.table])
    try:
        after_obj = getter(after_handle)
    except HandleError:
        # same as a hidden object, which the getter returns as None
        after_obj = None
    if after_obj is None:
        abort_with_message(422, "Invalid 'after' cursor")
    return tuple(
        resolve_column_ref(db, after_obj, column, spec)
        for column in after_columns(order_by)
    )


_DIALECT_BY_NAME: dict[str, Dialect] = {
    "sqlite": Dialect.SQLITE,
    "postgres": Dialect.POSTGRESQL,
    "postgresql": Dialect.POSTGRESQL,
}


class UnknownBackendError(Exception):
    """A database backend whose SQL dialect or tree scoping is unknown."""


def detect_dialect(basedb: Any) -> Dialect:
    """Backend SQL dialect, raising `UnknownBackendError` if unrecognized.

    See `_resolve_dialect` for the detection rules; callers choose their own
    failure policy (a 501 there, per-object evaluation in the GOQL filter rule).
    """
    name: Optional[str] = getattr(basedb, "dialect", None)
    if name:
        dialect = _DIALECT_BY_NAME.get(name)
        if dialect is not None:
            return dialect
    if is_sqlite(basedb):
        return Dialect.SQLITE
    class_name = type(basedb).__name__
    if class_name in (SINGLE_TREE_POSTGRES_CLASS_NAME, SHARED_POSTGRES_CLASS_NAME):
        return Dialect.POSTGRESQL
    raise UnknownBackendError(class_name)


def detect_treeid(basedb: Any) -> Optional[int]:
    """Current tree's ID, raising `UnknownBackendError` if undeterminable.

    See `_resolve_treeid` for why `None` must only ever mean "known
    single-tree backend", never "detection failed".
    """
    treeid = getattr(basedb.dbapi, "treeid", None)
    if treeid is not None:
        return treeid
    class_name = type(basedb).__name__
    if is_sqlite(basedb) or class_name == SINGLE_TREE_POSTGRES_CLASS_NAME:
        return None
    raise UnknownBackendError(class_name)


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
    outright, not just sort wrong. `SharedPostgreSQL` is likewise detected
    directly, by class name, for the versions of that addon which don't set
    `.dialect` yet.

    Anything else -- a backend this module has never seen, where a `.dialect`
    string didn't resolve and the class name matches neither known SQLite nor
    Postgres backend -- aborts with 501 rather than guessing PostgreSQL. A
    wrong guess here doesn't just sort oddly: it can render dialect-specific
    SQL (`::jsonb`, `jsonb_extract_path(...)`) against a connection that
    can't run it, or -- worse, for `_resolve_treeid`'s equivalent fallback --
    silently return another tenant's rows. Failing closed means a genuinely
    new backend needs this module updated before structured query works
    against it, rather than working by accident until it doesn't.

    The `SQLite`/`SharedPostgreSQL` checks (`is_sqlite`, in `db_backend.py`,
    shared with `_resolve_treeid` below and `util.py`'s
    `preload_event_backlinks`) are by class *name*, not `isinstance`,
    deliberately: Gramps' plugin loader imports database backend plugins
    (including core ones) as freestanding modules under a bare name
    (`sqlite`, not `gramps.plugins.db.dbapi.sqlite`) rather than via a
    normal package import, so a real request's `basedb` is a *different*
    class object than `db_backend.py`'s own `from
    gramps.plugins.db.dbapi.sqlite import SQLite` -- same name, same
    behavior, different identity. `isinstance(basedb, SQLite)` silently
    returns `False` for it every time, which was live (not just
    theoretically) confirmed to fall through to the `Dialect.POSTGRESQL`
    default for an actual SQLite deployment -- any dialect-sensitive SQL
    (`JsonPath`, `Exists`, `CollectionCount`) then renders
    `::jsonb`/`jsonb_extract_path(...)`/`jsonb_array_elements(...)` against a
    real SQLite connection and fails outright. A plain flat-column
    comparison (`Eq`/`Like`/...) never hits this branch at all, which is why
    the bug went unnoticed until an `exists(...)`/`count(...)` query
    actually exercised it. `isinstance` is kept first for `SQLite` since
    it's the correct, more specific check when it *does* match (e.g. a
    `SQLite()` constructed directly in-process, as this file's own tests do).
    """
    try:
        return detect_dialect(basedb)
    except UnknownBackendError as error:
        abort_with_message(
            501,
            f"Structured query does not recognize database backend {str(error)!r}",
        )


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

    Anything else -- a backend whose `.dbapi` has no `treeid` and isn't one
    of the known single-tree backends above -- aborts with 501 instead of
    treating the missing attribute as "no scoping needed". `None` here
    doesn't just mean "detection didn't find a value"; every caller downstream
    treats it as "this backend has no tenant concept, an unscoped query is
    fine" -- conflating that with "detection failed" would let an unscoped
    query against a genuinely shared backend succeed and return other
    tenants' rows instead of erroring.
    """
    try:
        return detect_treeid(basedb)
    except UnknownBackendError as error:
        abort_with_message(
            501,
            f"Structured query cannot determine tree scoping for database "
            f"backend {str(error)!r}",
        )


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
        if isinstance(db, (ProxyDbBase, RestrictedDb)):
            # Privacy (and any future proxy-applied rule) comes from `db`
            # itself here, not from a second, SQL-side reimplementation of
            # it -- see `proxied_query.py`'s module docstring. Not fast,
            # but correct for whatever proxy this is, current or future,
            # with nothing in this module needing to know its rules.
            return self._post_proxied(db, args)
        return self._post_sql(db, args)

    def _post_sql(self, basedb: Any, args: dict) -> Any:
        """Fast, SQL-pushed-down query -- only ever called with an unproxied
        `basedb`, so there is no privacy predicate to apply in the query
        itself. That's only safe because an unproxied `db` is supposed to
        imply the caller has `PERM_VIEW_PRIVATE` -- an invariant enforced
        two modules away, in `get_db_handle()`. Asserting it again here,
        redundantly, keeps that coupling local: if it's ever violated, this
        raises 403 instead of silently emitting private records with no
        privacy predicate at all.
        """
        require_permissions([PERM_VIEW_PRIVATE])
        if not hasattr(basedb, "dbapi"):
            abort_with_message(
                501, "Structured query is not supported on this database backend"
            )
        treeid = _resolve_treeid(basedb)

        try:
            # Resolved, not whitelist-checked: a sort column may be a path
            # (`birth.date.sortval`), which resolves exactly as the same text
            # does in `select`/`where_expr`. Unknown paths raise here.
            order_by = resolve_order_by(
                self.spec,
                [
                    OrderBy(item["column"], item.get("direction", "asc"))
                    for item in args.get("order_by") or []
                ],
            )
        except QueryError as error:
            abort_with_message(422, str(error))

        after = None
        if args.get("after"):
            after = _resolve_after(
                basedb,
                self.spec,
                order_by,
                args["after"],
                treeid,
                _resolve_dialect(basedb),
            )

        # `default=False`, deliberately: falling back to the system locale
        # here would apply COLLATE to every request, silently changing sort
        # order for callers who never asked for locale-aware sorting.
        # Locale-aware sorting is opt-in via an explicit `locale` param.
        locale = get_locale_for_language(args.get("locale"), default=False)
        collation = resolve_collation(basedb, locale) if locale is not None else None

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

            # Fetch one extra row beyond `limit` so a result set that's an
            # exact multiple of `limit` doesn't need a wasted follow-up
            # request just to learn there's no next page; the extra row is
            # trimmed back off below and never reaches the response.
            query = Query(
                select=fetch_refs,
                where=_build_where(args, self.spec),
                order_by=order_by,
                limit=args["limit"] + 1,
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
        has_more = len(rows) > args["limit"]
        rows = rows[: args["limit"]]

        headers = {}
        if count_sql is not None:
            basedb.dbapi.execute(count_sql, count_params)
            headers["X-Total-Count"] = str(basedb.dbapi.fetchone()[0])

        handle_index = fetch_refs.index("handle")
        # The database returns some values in its own form: a boolean as
        # 0/1, a JSON number or boolean as text on PostgreSQL, an object or
        # list as JSON text on SQLite. Normalized, each value has the type
        # Gramps' schema gives it, as on the proxied path.
        normalize = select_normalizer(self.spec, fetch_refs)
        items = [
            {
                key: val
                for key, val in zip(fetch_keys, normalize(row))
                if key in requested_keys
            }
            for row in rows
        ]
        next_after = rows[-1][handle_index] if has_more else None

        return {"items": items, "next_after": next_after}, 200, headers

    def _post_proxied(self, db: Any, args: dict) -> Any:
        """Same request/response contract as `_post_sql`, but for a proxied
        `db` -- delegates directly to `proxied_query.run_query_with_total`'s own
        `order_by`/`limit`/`after`/`select` support rather than
        reimplementing sort/seek/limit here: every candidate is still
        deserialized and tested in Python (no SQL push-down), so this is
        intentionally not fast -- see `proxied_query.py`'s module docstring.

        `order_by` is resolved via `resolve_order_by`, the same as the SQL
        path, so `OrderBy.column` may carry a `JsonPath`/`RelatedObject`
        path (e.g. `birth.date.sortval`) here too, not just a flat
        top-level column -- `run_query`'s own sort (`_sort_key_row`)
        resolves whatever it's given via `resolve_column_ref`. Locale-aware
        `COLLATE` sorting (the SQL path's `locale` param) has no equivalent
        here -- `run_query` sorts in NULL-safe Python comparisons that
        ASCII-case-fold text values, matching the SQL path's own NOCASE
        default (SQLite's built-in collation, applied when `locale` is
        unset -- see `_resolve_collation`), not full locale collation.
        Rather than silently returning a different sort order than the
        same request would get on the SQL path, an explicit `locale` is
        rejected outright below.
        """
        if args.get("locale"):
            abort_with_message(
                422,
                "locale-aware sorting is not supported on the proxied query "
                "path (no COLLATE equivalent there)",
            )
        try:
            order_by = resolve_order_by(
                self.spec,
                [
                    OrderBy(item["column"], item.get("direction", "asc"))
                    for item in args.get("order_by") or []
                ],
            )
            where = _build_where(args, self.spec)
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

        after = None
        if args.get("after"):
            after = _resolve_after_proxied(db, self.spec, order_by, args["after"])

        # `RestrictedDb` cleans raw data directly, so reading it raw skips
        # building an object per record. A Gramps proxy builds the object
        # anyway, so it keeps the default object reader.
        reader = RawDataReader(db) if isinstance(db, RestrictedDb) else None
        # See the matching comment in `_post_sql`: over-fetch by one row so
        # an exact-multiple-of-`limit` result set doesn't need a wasted
        # follow-up request to learn there's no next page. Every record is
        # read and tested to sort the matches anyway, so the total (which
        # ignores `after` and `limit`, like `count_sql`) comes from the same
        # pass rather than a second, unlimited one.
        rows, total = run_query_with_total(
            db,
            self.spec,
            where,
            order_by=order_by,
            limit=args["limit"] + 1,
            after=after,
            select=fetch_refs,
            reader=reader,
        )
        has_more = len(rows) > args["limit"]
        rows = rows[: args["limit"]]

        headers = {}
        if args["count"]:
            headers["X-Total-Count"] = str(total)

        handle_index = fetch_refs.index("handle")
        items = [
            {key: val for key, val in zip(fetch_keys, row) if key in requested_keys}
            for row in rows
        ]
        next_after = rows[-1][handle_index] if has_more else None

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
