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

"""A small, closed query AST and SQL compiler for fast object queries.

This is not a general query language, not GraphQL, and not a raw-SQL
passthrough. Only `where` and `order_by` have tree structure; `select`,
`limit`, and `after` stay flat. Every column name is checked against a
fixed per-type whitelist (`ObjectTypeSpec.columns`, derived from the
secondary columns already flattened server-side for that object's table)
before the compiler ever touches it, and values are always bound as `?`
parameters -- there is no path from client input to a raw SQL string.

This module is pure and does no database access, so it is unit-testable
without a running server. Keyset pagination (`Query.after`) expects the
*resolved* sort-column values for the cursor row, not just a handle --
resolving a client-supplied handle into that tuple (one extra lookup) is
the caller's job; see `after_columns()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
    Tag,
)


@dataclass(frozen=True)
class ObjectTypeSpec:
    """Table + whitelist for one Gramps object type's flat secondary columns."""

    table: str
    columns: frozenset[str]
    text_columns: frozenset[str]
    has_privacy: bool


def _spec_for(cls: type, extra_columns: frozenset[str] = frozenset()) -> ObjectTypeSpec:
    """Build an `ObjectTypeSpec` from a Gramps object class's secondary fields.

    Kept in sync with core rather than hardcoded, since this *is* the set of
    columns that exist as real SQL columns on the table. `has_privacy` is
    derived rather than declared, since it's not universal -- `Tag` has no
    `private` column at all. `text_columns` (the subset eligible for a
    locale `COLLATE` clause -- see `compile_query`) is derived the same way:
    every `extra_columns` entry is text today (`given_name`/`surname`/
    `enclosed_by`), and `get_secondary_fields()` already tags each field's
    SQL type.
    """
    fields = list(cls.get_secondary_fields())
    columns = frozenset(field for field, _, _ in fields) | extra_columns
    text_columns = (
        frozenset(field for field, schema_type, _ in fields if schema_type == "string")
        | extra_columns
    )
    return ObjectTypeSpec(
        table=cls.__name__.lower(),
        columns=columns,
        text_columns=text_columns,
        has_privacy="private" in columns,
    )


# One spec per object type, each wired to a `.../query/` endpoint (see
# `resources/object_query.py`).
PERSON = _spec_for(Person, extra_columns=frozenset({"given_name", "surname"}))
FAMILY = _spec_for(Family)
EVENT = _spec_for(Event)
PLACE = _spec_for(Place, extra_columns=frozenset({"enclosed_by"}))
REPOSITORY = _spec_for(Repository)
SOURCE = _spec_for(Source)
CITATION = _spec_for(Citation)
MEDIA = _spec_for(Media)
NOTE = _spec_for(Note)
TAG = _spec_for(Tag)


class QueryError(ValueError):
    """Raised when a query references an unknown column or is malformed."""


def _check_column(column: str, whitelist: frozenset[str]) -> None:
    if column not in whitelist:
        raise QueryError(f"unknown or disallowed column: {column!r}")


# Column names that collide with reserved SQL words -- currently just
# `Media.desc` (PostgreSQL reserves DESC; SQLite doesn't). Mirrors
# addons-source's `PostgreSQL`/`SharedPostgreSQL` `_quote_column()` list (see
# PLAN grounding notes); remove once gramps core PR #2178 makes this
# core-provided instead of addon- and caller-side.
#
# Note: `SharedPostgreSQL`'s not-yet-migrated `Connection.execute()` still
# runs its own blind "desc" -> "desc_" string-replace on every query it
# receives (not just at schema-creation time) -- so a *plain, unquoted*
# logical column name like `description` is already transformed correctly
# into the real physical `desc_ription` by that pre-existing hack. Quoting
# survives it fine too (`"desc"` -> `"desc_"`, still a valid reference).
# Verified live against a real deployed instance -- see PLAN grounding
# notes. Do not add a compensating column-name override here: since the
# hack already runs once, layering a second correction on top double-
# corrupts the name (`desc_ription` -> `desc__ription`).
_RESERVED_SQL_WORDS = frozenset({"desc", "order", "where", "select"})


def _quote_column(column: str) -> str:
    """Quote a column identifier if it collides with a reserved SQL word.

    Not a general identifier-quoting scheme -- every whitelisted column not
    in `_RESERVED_SQL_WORDS` is emitted bare, matching prior output exactly.
    """
    return f'"{column}"' if column in _RESERVED_SQL_WORDS else column


# --- WHERE: comparison leaves -----------------------------------------------


class Comparison:
    """Base class for single-column comparison leaves (`Eq`, `Lt`, ...)."""

    op: str

    def __init__(self, column: str, value: Any):
        self.column = column
        self.value = value

    def compile(self, whitelist: frozenset[str]) -> Tuple[str, list]:
        _check_column(self.column, whitelist)
        return f"{_quote_column(self.column)} {self.op} ?", [self.value]

    def __eq__(self, other: object) -> bool:
        return (
            type(self) is type(other)
            and self.column == other.column  # type: ignore[attr-defined]
            and self.value == other.value  # type: ignore[attr-defined]
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.column!r}, {self.value!r})"


class Eq(Comparison):
    op = "="


class Ne(Comparison):
    op = "!="


class Lt(Comparison):
    op = "<"


class Lte(Comparison):
    op = "<="


class Gt(Comparison):
    op = ">"


class Gte(Comparison):
    op = ">="


class Like(Comparison):
    op = "LIKE"


class In:
    """WHERE column IN (values...)."""

    def __init__(self, column: str, values: Sequence[Any]):
        if not values:
            raise QueryError("In() requires at least one value")
        self.column = column
        self.values = list(values)

    def compile(self, whitelist: frozenset[str]) -> Tuple[str, list]:
        _check_column(self.column, whitelist)
        placeholders = ", ".join(["?"] * len(self.values))
        return f"{_quote_column(self.column)} IN ({placeholders})", list(self.values)

    def __eq__(self, other: object) -> bool:
        return (
            type(self) is type(other)
            and self.column == other.column  # type: ignore[attr-defined]
            and self.values == other.values  # type: ignore[attr-defined]
        )

    def __repr__(self) -> str:
        return f"In({self.column!r}, {self.values!r})"


# --- WHERE: boolean combinators ---------------------------------------------


class And:
    def __init__(self, *exprs: Any):
        if not exprs:
            raise QueryError("And() requires at least one expression")
        self.exprs = exprs

    def compile(self, whitelist: frozenset[str]) -> Tuple[str, list]:
        parts = []
        params: list = []
        for expr in self.exprs:
            sql, p = expr.compile(whitelist)
            parts.append(f"({sql})")
            params.extend(p)
        return " AND ".join(parts), params

    def __repr__(self) -> str:
        return f"And{self.exprs!r}"


class Or:
    def __init__(self, *exprs: Any):
        if not exprs:
            raise QueryError("Or() requires at least one expression")
        self.exprs = exprs

    def compile(self, whitelist: frozenset[str]) -> Tuple[str, list]:
        parts = []
        params: list = []
        for expr in self.exprs:
            sql, p = expr.compile(whitelist)
            parts.append(f"({sql})")
            params.extend(p)
        return " OR ".join(parts), params

    def __repr__(self) -> str:
        return f"Or{self.exprs!r}"


class Not:
    def __init__(self, expr: Any):
        self.expr = expr

    def compile(self, whitelist: frozenset[str]) -> Tuple[str, list]:
        sql, params = self.expr.compile(whitelist)
        return f"NOT ({sql})", params

    def __repr__(self) -> str:
        return f"Not({self.expr!r})"


# --- ORDER BY ----------------------------------------------------------------


@dataclass(frozen=True)
class OrderBy:
    column: str
    direction: str = "asc"

    def __post_init__(self) -> None:
        if self.direction not in ("asc", "desc"):
            raise QueryError(f"invalid sort direction: {self.direction!r}")


def _effective_order_by(order_by: Sequence[OrderBy]) -> Tuple[OrderBy, ...]:
    """`order_by` with a trailing `handle` tiebreaker appended if not present.

    Guarantees a stable, fully-determined order for both `ORDER BY` emission
    and keyset pagination, even when the caller specifies no sort at all.
    """
    if any(ob.column == "handle" for ob in order_by):
        return tuple(order_by)
    return tuple(order_by) + (OrderBy("handle", "asc"),)


def after_columns(order_by: Sequence[OrderBy]) -> Tuple[str, ...]:
    """Columns, in order, that a resolved `after` cursor tuple must supply.

    Wiring code turns a client-supplied `after=<handle>` into a `Query.after`
    tuple by looking up these columns for that row (one extra lookup) before
    compiling -- this module does no database access itself.
    """
    return tuple(ob.column for ob in _effective_order_by(order_by))


def check_columns(columns: Sequence[str], spec: ObjectTypeSpec) -> None:
    """Raise `QueryError` if any of `columns` is not in `spec.columns`.

    Exposed for wiring code that needs to validate columns before they can
    safely appear in a raw SQL fragment built outside `compile_query` --
    e.g. resolving an `after` cursor's row values, which necessarily happens
    before compilation.
    """
    for column in columns:
        _check_column(column, spec.columns)


# --- Top level ---------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    select: Optional[Sequence[str]] = None
    where: Optional[Any] = None
    order_by: Sequence[OrderBy] = ()
    limit: int = 50
    after: Optional[Sequence[Any]] = None

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit <= 0:
            raise QueryError(f"limit must be positive: {self.limit!r}")


def _column_expr(column: str, spec: ObjectTypeSpec, collation: Optional[str]) -> str:
    """Column reference, with a locale `COLLATE` clause when applicable.

    Only columns in `spec.text_columns` are collatable -- applying `COLLATE`
    to a non-text column (e.g. an integer) is a SQL error on PostgreSQL, so
    this is deliberately narrower than "every ORDER BY column".
    """
    quoted = _quote_column(column)
    if collation and column in spec.text_columns:
        return f'{quoted} COLLATE "{collation}"'
    return quoted


def _compile_keyset(
    effective_order_by: Sequence[OrderBy],
    after: Sequence[Any],
    spec: ObjectTypeSpec,
    collation: Optional[str],
) -> Tuple[str, list]:
    """Seek-method WHERE fragment for keyset pagination.

    Expands to an OR-of-ANDs (`(c1 > v1) OR (c1 = v1 AND c2 > v2) OR ...`)
    rather than a row-constructor comparison, so mixed asc/desc multi-column
    sorts stay correct on both SQLite and PostgreSQL. Comparisons use the
    same `COLLATE` clause as the matching `ORDER BY` column -- otherwise a
    row could satisfy a binary-comparison seek predicate while sorting
    differently under collation, corrupting page boundaries.
    """
    if len(after) != len(effective_order_by):
        raise QueryError(
            f"after cursor has {len(after)} values, expected "
            f"{len(effective_order_by)} ({', '.join(ob.column for ob in effective_order_by)})"
        )
    or_terms = []
    params: list = []
    for i, ob in enumerate(effective_order_by):
        and_terms = []
        for j in range(i):
            and_terms.append(
                f"{_column_expr(effective_order_by[j].column, spec, collation)} = ?"
            )
            params.append(after[j])
        op = ">" if ob.direction == "asc" else "<"
        and_terms.append(f"{_column_expr(ob.column, spec, collation)} {op} ?")
        params.append(after[i])
        or_terms.append("(" + " AND ".join(and_terms) + ")")
    return " OR ".join(or_terms), params


def compile_query(
    spec: ObjectTypeSpec,
    query: Query,
    *,
    can_view_private: bool = False,
    collation: Optional[str] = None,
) -> Tuple[str, list]:
    """Compile a `Query` into a parameterized `SELECT ... FROM <spec.table>` statement.

    Returns `(sql, params)` where `sql` uses `?` placeholders and `params` is
    the positional parameter list, matching `db.dbapi.execute(sql, params)`.

    `AND private = 0` is appended unless `can_view_private` is set or the
    type has no `private` column (`spec.has_privacy` is `False`, as for
    `Tag`) -- not a query option, baked in so it cannot be omitted by a
    malformed or malicious request.

    `collation`, if given, names a locale collation already ensured to exist
    on the connection (see `resources/object_query.py`'s `_resolve_collation`)
    and is applied to every text-typed `ORDER BY` column (and the matching
    keyset comparisons) via `COLLATE "<collation>"`.
    """
    columns = list(query.select) if query.select else sorted(spec.columns)
    for column in columns:
        _check_column(column, spec.columns)

    effective_order_by = _effective_order_by(query.order_by)
    for ob in effective_order_by:
        _check_column(ob.column, spec.columns)

    where_clauses = []
    params: list = []

    if query.where is not None:
        sql, p = query.where.compile(spec.columns)
        where_clauses.append(f"({sql})")
        params.extend(p)

    if spec.has_privacy and not can_view_private:
        where_clauses.append("private = 0")

    if query.after is not None:
        sql, p = _compile_keyset(effective_order_by, query.after, spec, collation)
        where_clauses.append(f"({sql})")
        params.extend(p)

    select_list = ", ".join(_quote_column(c) for c in columns)
    sql = f"SELECT {select_list} FROM {spec.table}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY " + ", ".join(
        f"{_column_expr(ob.column, spec, collation)} {ob.direction.upper()}"
        for ob in effective_order_by
    )
    if query.limit is not None:
        sql += " LIMIT ?"
        params.append(query.limit)

    return sql, params
