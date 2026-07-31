#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

from typing import Any, Optional, Sequence

from gramps.gen.proxy.proxybase import ProxyDbBase
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
    Eq,
    Gt,
    Gte,
    In,
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
    compile_query,
)
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

    column = wf.Str(
        required=True, metadata={"description": "Column to compare, e.g. 'gramps_id'."}
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
        wf.Str(),
        required=False,
        metadata={
            "description": "Columns to return. Defaults to all available columns."
        },
    )
    where = wf.List(
        wf.Nested(QueryWhereConditionArgs),
        required=False,
        metadata={"description": "Leaf conditions, implicitly combined with AND."},
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


def _build_where(conditions: Optional[Sequence[dict]]):
    """Build a `query.py` WHERE expression from parsed leaf conditions."""
    if not conditions:
        return None
    exprs = []
    for condition in conditions:
        column = condition["column"]
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


def _resolve_after(
    basedb: Any,
    spec: ObjectTypeSpec,
    order_by: Sequence[OrderBy],
    after_handle: str,
    can_view_private: bool,
):
    """Resolve a client-supplied `after=<handle>` cursor into a value tuple.

    The sort-column values for the cursor row aren't known to the client, so
    the handle it supplies has to be looked up first. Columns were already
    validated by the caller, so this is safe to interpolate.
    """
    columns = after_columns(order_by)
    sql = f"SELECT {', '.join(columns)} FROM {spec.table} WHERE handle = ?"
    params = [after_handle]
    if spec.has_privacy and not can_view_private:
        sql += " AND private = 0"
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
        basedb = db.basedb if isinstance(db, ProxyDbBase) else db
        if not hasattr(basedb, "dbapi"):
            abort_with_message(
                501, "Structured query is not supported on this database backend"
            )

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
                basedb, self.spec, order_by, args["after"], can_view_private
            )

        # `default=False`, deliberately: falling back to the system locale
        # here would apply COLLATE to every request, silently changing sort
        # order for callers who never asked for locale-aware sorting.
        # Locale-aware sorting is opt-in via an explicit `locale` param.
        locale = get_locale_for_language(args.get("locale"), default=False)
        collation = _resolve_collation(basedb, locale) if locale is not None else None

        requested_columns = (
            list(args["select"]) if args.get("select") else sorted(self.spec.columns)
        )
        fetch_columns = (
            requested_columns
            if "handle" in requested_columns
            else requested_columns + ["handle"]
        )

        try:
            query = Query(
                select=fetch_columns,
                where=_build_where(args.get("where")),
                order_by=order_by,
                limit=args["limit"],
                after=after,
            )
            sql, params = compile_query(
                self.spec, query, can_view_private=can_view_private, collation=collation
            )
        except QueryError as error:
            abort_with_message(422, str(error))

        basedb.dbapi.execute(sql, params)
        rows = basedb.dbapi.fetchall()

        handle_index = fetch_columns.index("handle")
        requested = set(requested_columns)
        items = [
            {col: val for col, val in zip(fetch_columns, row) if col in requested}
            for row in rows
        ]
        next_after = rows[-1][handle_index] if len(rows) == args["limit"] else None

        return {"items": items, "next_after": next_after}


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
