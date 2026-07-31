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

import enum
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, Tuple, Union

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
from gramps.gen.lib.tableobj import TableObject


@dataclass(frozen=True)
class ObjectTypeSpec:
    """Table + whitelist for one Gramps object type's flat secondary columns."""

    table: str
    columns: frozenset[str]
    text_columns: frozenset[str]
    has_privacy: bool


def _spec_for(
    cls: type[TableObject], extra_columns: frozenset[str] = frozenset()
) -> ObjectTypeSpec:
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


class Dialect(str, enum.Enum):
    """SQL dialect for backend-specific rendering.

    `JsonPath` is the first thing this compiler emits that needs to know
    which backend it's talking to -- everything else (`?`-parameterized
    comparisons, `AND`/`OR`, keyset seek expressions, `COLLATE`) is
    dialect-neutral SQL that already works unchanged on both backends.
    """

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


@dataclass(frozen=True)
class JsonPath:
    """A path into a JSON-blob secondary column (default: `json_data`).

    Not whitelisted against a fixed column list the way a plain column name
    is -- `json_data` is a real column on every table, but its *content* is
    arbitrary. Safety instead comes from every path segment being
    individually type-checked (`str` keys or non-bool `int` array indices
    only) and always bound as a query parameter, never interpolated into
    SQL text -- see `_render_json_path`.

    Not (yet) usable in `order_by`/keyset pagination -- only `select` and
    `where`. `ObjectTypeSpec.text_columns`-based `COLLATE` selection also
    doesn't apply to it: the JSON value's type isn't known ahead of time.
    """

    segments: Tuple[Union[str, int], ...]
    base_column: str = "json_data"

    def __post_init__(self) -> None:
        if not self.segments:
            raise QueryError("JsonPath requires at least one segment")
        for segment in self.segments:
            if isinstance(segment, bool) or not isinstance(segment, (str, int)):
                raise QueryError(f"invalid JsonPath segment: {segment!r}")


@dataclass(frozen=True)
class RelatedEventDate:
    """Virtual field: something extracted from the `date` of the event
    referenced by a `Person`'s `birth_ref_index`/`death_ref_index`.

    `Person` has no date of its own -- only an index (`ref_index_column`)
    into `event_ref_list` saying which entry is the birth/death event; the
    actual date lives on that separate `Event` row. Resolved via a
    *correlated scalar subquery*, not a `JOIN`: the subquery is a fully
    independent scope with its own `FROM event`, so it needs no changes to
    how the rest of this compiler emits column references (everything
    outside the subquery stays exactly as unqualified as it is today) --
    see `_render_related_event_date`.

    `extract` is the path within the event's `date` struct to pull out --
    `("date",)` (the default, used by `BIRTH_DATE`/`DEATH_DATE`) returns
    the whole struct, for `select`. `("date", "sortval")` (used by
    `BIRTH_DATE_SORTVAL`/`DEATH_DATE_SORTVAL`) returns just the comparable
    Julian-day integer, for `where` -- `sortval` is deliberately the only
    sub-field exposed for comparisons: it's the one property Gramps itself
    treats as chronologically orderable. (`dateval`'s raw
    `(day, month, year, slash)` tuple isn't safely comparable as a whole --
    SQL would sort by day first, not year -- and `modifier`/`quality`,
    which distinguish "before"/"about"/exact, collapse to the same
    `sortval` regardless, so a range query can't currently tell those
    apart; a known, accepted limitation, not fixed by this.)

    Not (yet) usable in `order_by`/keyset pagination -- same reasoning as
    `JsonPath` there: the join key (`ref_index_column`'s value) is a
    *per-row* dynamic JSON array index, fine for a one-off extraction but
    not threaded through machinery that assumes every comparable value
    lives in the base table.
    """

    ref_index_column: str
    extract: Tuple[str, ...] = ("date",)


BIRTH_DATE = RelatedEventDate("birth_ref_index")
DEATH_DATE = RelatedEventDate("death_ref_index")
BIRTH_DATE_SORTVAL = RelatedEventDate("birth_ref_index", extract=("date", "sortval"))
DEATH_DATE_SORTVAL = RelatedEventDate("death_ref_index", extract=("date", "sortval"))


# A column reference is either a plain (whitelisted) column name, a path
# into one column's JSON content, or a related event's date (or a field of
# it) -- the latter select-only in its `BIRTH_DATE`/`DEATH_DATE` (whole
# struct) form, but usable in `where` too via `BIRTH_DATE_SORTVAL`/
# `DEATH_DATE_SORTVAL`.
ColumnRef = Union[str, JsonPath, RelatedEventDate]
SelectRef = ColumnRef


def _require_dialect(dialect: Optional[Dialect], path: JsonPath) -> Dialect:
    if dialect is None:
        raise QueryError(
            f"a dialect is required to compile a JsonPath ({path!r}), but none was given"
        )
    return dialect


def _render_json_path(
    path: JsonPath, dialect: Dialect, value: Any = None
) -> Tuple[str, list]:
    """Render a `JsonPath` into a dialect-specific SQL expression + bound params.

    SQLite: `json_extract(json_data, ?)` with a single bound JSONPath-syntax
    string (`$.primary_name.surname_list[0].surname`). SQLite's `json_extract`
    already returns a properly-typed SQLite value (INTEGER/REAL/TEXT) matching
    the JSON value's own type, so no cast is needed here for correct ordering
    comparisons.

    PostgreSQL: `jsonb_extract_path_text(json_data::jsonb, ?, ?, ...)` with
    one bound parameter per path segment -- `json_data` is stored as `TEXT`
    on both backends (no native `jsonb` column), hence the cast. Confirmed
    live against a real PostgreSQL 16 instance: `jsonb_extract_path_text`
    treats a numeric-looking text segment (e.g. `"0"`) as a JSON array
    index, so integer segments are simply stringified, not cast separately.

    `jsonb_extract_path_text` always returns `TEXT`, though, which is wrong
    for `Lt`/`Gt`/etc. against a numeric or boolean `value` -- PostgreSQL
    compares text lexicographically, not numerically (`'10' < '9'` is true).
    `value` -- the Python value already in hand on the comparison, e.g.
    `Gt(json_path, 5).value` -- picks the cast: `bool` -> `BOOLEAN`, `int`/
    `float` -> `NUMERIC` (via the non-`_text` `jsonb_extract_path` + `CAST`,
    mirroring the pattern in gramps' `SQLiteWithSelect` addon's
    `sql_generator.py`), otherwise `TEXT` as before. This is driven by the
    already-known comparison value rather than a separate static
    type-inference pass.
    """
    if dialect == Dialect.SQLITE:
        jsonpath = "$" + "".join(
            f"[{segment}]" if isinstance(segment, int) else f".{segment}"
            for segment in path.segments
        )
        return f"json_extract({path.base_column}, ?)", [jsonpath]
    if dialect == Dialect.POSTGRESQL:
        placeholders = ", ".join(["?"] * len(path.segments))
        params = [str(segment) for segment in path.segments]
        if isinstance(value, bool):
            extract = f"jsonb_extract_path({path.base_column}::jsonb, {placeholders})"
            return f"CAST({extract} AS BOOLEAN)", params
        if isinstance(value, (int, float)):
            extract = f"jsonb_extract_path({path.base_column}::jsonb, {placeholders})"
            return f"CAST({extract} AS NUMERIC)", params
        return (
            f"jsonb_extract_path_text({path.base_column}::jsonb, {placeholders})",
            params,
        )
    raise QueryError(f"unsupported dialect: {dialect!r}")


def _render_related_event_date(
    related: RelatedEventDate,
    spec: ObjectTypeSpec,
    dialect: Optional[Dialect],
    can_view_private: bool,
    treeid: Optional[int],
    value: Any = None,
) -> Tuple[str, list]:
    """Render a `RelatedEventDate` as a correlated scalar subquery.

    ```sql
    (SELECT <extraction of related.extract> FROM event
     WHERE event.handle = (CASE WHEN person.birth_ref_index >= 0
                                 THEN <dynamic index extraction>
                                 ELSE NULL END)
       AND event.private = 0          -- unless can_view_private
       AND event.treeid = ?           -- when treeid is given
     LIMIT 1)
    ```

    The `CASE WHEN ... >= 0` guard is required, not defensive: `-1` means
    "no such event recorded", and confirmed live against PostgreSQL 16,
    its `->` operator treats a negative array index as "count from the
    end" rather than "invalid" -- without the guard, a person with no
    birth event but *some* other event would silently get that unrelated
    event's date reported as their birth date. SQLite has no such failure
    mode (a negative `json_extract` array index simply yields no match),
    but the guard is dialect-neutral so both paths stay identical.

    Privacy and `treeid` scoping are applied to the *subquery*'s `event`
    row, not the outer query -- a private birth event with no view
    permission must make this field come back `null`, not exclude the
    person from the results entirely, which a top-level `WHERE` would do.

    Uses a correlated subquery rather than a `JOIN` specifically so this
    needs no `JOIN`/alias support anywhere else in this compiler: the
    subquery is a fully independent SQL scope with its own `FROM event`,
    correlated back to the outer query via the outer table's own
    (unaliased) name -- confirmed live on both SQLite and PostgreSQL that
    an unaliased table's own name is a valid correlation reference from a
    nested subquery.

    `value`, when given (a `where`-comparison's right-hand value, never
    set for `select`), picks the cast for the *last* segment of
    `related.extract` the same way `_render_json_path` does: `bool` ->
    `BOOLEAN`, `int`/`float` -> `NUMERIC` (via a non-text PostgreSQL `->`
    + `CAST`, since `->>`'s `TEXT` result compares lexicographically, not
    numerically), otherwise left as-is -- matching the existing `select`
    (`value=None`) rendering exactly, so `BIRTH_DATE`/`DEATH_DATE`'s
    output is unaffected by this parameter's addition.
    """
    if related.ref_index_column not in spec.columns:
        raise QueryError(
            f"{related.ref_index_column!r} is not a column on {spec.table!r} -- "
            "RelatedEventDate is only valid for Person (birth_ref_index/death_ref_index)"
        )
    if dialect is None:
        raise QueryError(
            f"a dialect is required to compile a RelatedEventDate ({related!r}), "
            "but none was given"
        )
    outer_table = spec.table
    ref_col = related.ref_index_column
    params: list = []
    if dialect == Dialect.SQLITE:
        index_extract = (
            f"json_extract({outer_table}.json_data, "
            f"'$.event_ref_list[' || {outer_table}.{ref_col} || '].ref')"
        )
        json_path_str = "$." + ".".join(related.extract)
        date_extract = f"json_extract({EVENT.table}.json_data, '{json_path_str}')"
    elif dialect == Dialect.POSTGRESQL:
        index_extract = (
            f"{outer_table}.json_data::jsonb -> 'event_ref_list' -> "
            f"{outer_table}.{ref_col} ->> 'ref'"
        )
        if value is None:
            chain = " -> ".join(f"'{segment}'" for segment in related.extract)
            date_extract = f"{EVENT.table}.json_data::jsonb -> {chain}"
        else:
            *prefix_segments, last_segment = related.extract
            prefix_chain = "".join(f" -> '{segment}'" for segment in prefix_segments)
            base = f"{EVENT.table}.json_data::jsonb{prefix_chain}"
            if isinstance(value, bool):
                date_extract = f"CAST(({base} -> '{last_segment}') AS BOOLEAN)"
            elif isinstance(value, (int, float)):
                date_extract = f"CAST(({base} -> '{last_segment}') AS NUMERIC)"
            else:
                date_extract = f"({base} ->> '{last_segment}')"
    else:
        raise QueryError(f"unsupported dialect: {dialect!r}")

    ref_handle_sql = (
        f"CASE WHEN {outer_table}.{ref_col} >= 0 THEN {index_extract} ELSE NULL END"
    )
    subquery_where = [f"{EVENT.table}.handle = ({ref_handle_sql})"]
    if not can_view_private:
        subquery_where.append(f"{EVENT.table}.private = 0")
    if treeid is not None:
        subquery_where.append(f"{EVENT.table}.treeid = ?")
        params.append(treeid)

    subquery = (
        f"(SELECT {date_extract} FROM {EVENT.table} "
        f"WHERE {' AND '.join(subquery_where)} LIMIT 1)"
    )
    return subquery, params


def _render_column(
    column: ColumnRef,
    spec: ObjectTypeSpec,
    dialect: Optional[Dialect],
    value: Any = None,
    can_view_private: bool = False,
    treeid: Optional[int] = None,
) -> Tuple[str, list]:
    """Render a column reference (plain name, `JsonPath`, or `RelatedEventDate`).

    Used for both `SELECT` list entries (no right-hand value to bind,
    `value` stays `None`) and `WHERE` comparisons. `value`, when given, is
    the comparison's right-hand Python value -- used only to pick a
    `JsonPath`/`RelatedEventDate` cast (see `_render_json_path`/
    `_render_related_event_date`); ignored for plain column names.
    `can_view_private`/`treeid` are only used by `RelatedEventDate`, whose
    correlated subquery needs its own privacy/tree-scoping independent of
    the outer query's.
    """
    if isinstance(column, RelatedEventDate):
        return _render_related_event_date(
            column, spec, dialect, can_view_private, treeid, value
        )
    if isinstance(column, JsonPath):
        return _render_json_path(column, _require_dialect(dialect, column), value)
    _check_column(column, spec.columns)
    return _quote_column(column), []


# --- WHERE: comparison leaves -----------------------------------------------


class Comparison:
    """Base class for single-column comparison leaves (`Eq`, `Lt`, ...)."""

    op: str

    def __init__(self, column: ColumnRef, value: Any):
        self.column = column
        self.value = value

    def compile(
        self,
        spec: ObjectTypeSpec,
        dialect: Optional[Dialect] = None,
        can_view_private: bool = False,
        treeid: Optional[int] = None,
    ) -> Tuple[str, list]:
        column_sql, column_params = _render_column(
            self.column,
            spec,
            dialect,
            value=self.value,
            can_view_private=can_view_private,
            treeid=treeid,
        )
        return f"{column_sql} {self.op} ?", column_params + [self.value]

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

    def __init__(self, column: ColumnRef, values: Sequence[Any]):
        if not values:
            raise QueryError("In() requires at least one value")
        self.column = column
        self.values = list(values)

    def compile(
        self,
        spec: ObjectTypeSpec,
        dialect: Optional[Dialect] = None,
        can_view_private: bool = False,
        treeid: Optional[int] = None,
    ) -> Tuple[str, list]:
        column_sql, column_params = _render_column(
            self.column,
            spec,
            dialect,
            value=self.values[0],
            can_view_private=can_view_private,
            treeid=treeid,
        )
        placeholders = ", ".join(["?"] * len(self.values))
        return f"{column_sql} IN ({placeholders})", column_params + list(self.values)

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

    def compile(
        self,
        spec: ObjectTypeSpec,
        dialect: Optional[Dialect] = None,
        can_view_private: bool = False,
        treeid: Optional[int] = None,
    ) -> Tuple[str, list]:
        parts = []
        params: list = []
        for expr in self.exprs:
            sql, p = expr.compile(spec, dialect, can_view_private, treeid)
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

    def compile(
        self,
        spec: ObjectTypeSpec,
        dialect: Optional[Dialect] = None,
        can_view_private: bool = False,
        treeid: Optional[int] = None,
    ) -> Tuple[str, list]:
        parts = []
        params: list = []
        for expr in self.exprs:
            sql, p = expr.compile(spec, dialect, can_view_private, treeid)
            parts.append(f"({sql})")
            params.extend(p)
        return " OR ".join(parts), params

    def __repr__(self) -> str:
        return f"Or{self.exprs!r}"


class Not:
    def __init__(self, expr: Any):
        self.expr = expr

    def compile(
        self,
        spec: ObjectTypeSpec,
        dialect: Optional[Dialect] = None,
        can_view_private: bool = False,
        treeid: Optional[int] = None,
    ) -> Tuple[str, list]:
        sql, params = self.expr.compile(spec, dialect, can_view_private, treeid)
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


def check_columns(columns: Iterable[str], spec: ObjectTypeSpec) -> None:
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
    select: Optional[Sequence[SelectRef]] = None
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


def _where_clauses(
    spec: ObjectTypeSpec,
    where: Optional[Any],
    can_view_private: bool,
    dialect: Optional[Dialect] = None,
    treeid: Optional[int] = None,
) -> Tuple[list, list]:
    """Shared `WHERE`-clause + privacy/tree-scoping predicate building.

    Used by both `compile_query` and `compile_count_query`, so the two can't
    drift on how privacy or tree-scoping is enforced.

    `treeid`, when given, appends `AND treeid = ?` -- required on shared
    multi-tree backends (`SharedPostgreSQL`), whose tables hold every tree's
    rows together with `treeid` as part of the primary key. Nothing applies
    this filter automatically at the connection level; every one of
    `SharedDBAPI`'s own query methods (`get_person_handles`, etc.) adds it
    by hand, so this compiler must too, or it silently returns rows from
    every tree sharing the instance -- not just the caller's own. `None`
    (the default) omits the clause entirely, for single-tree-per-database
    backends (`SQLite`, the single-user `PostgreSQL` addon) that have no
    `treeid` column at all -- see `resources/object_query.py`'s
    `_resolve_treeid`.
    """
    clauses = []
    params: list = []
    if where is not None:
        sql, p = where.compile(spec, dialect, can_view_private, treeid)
        clauses.append(f"({sql})")
        params.extend(p)
    if spec.has_privacy and not can_view_private:
        clauses.append("private = 0")
    if treeid is not None:
        clauses.append("treeid = ?")
        params.append(treeid)
    return clauses, params


def compile_query(
    spec: ObjectTypeSpec,
    query: Query,
    *,
    can_view_private: bool = False,
    collation: Optional[str] = None,
    dialect: Optional[Dialect] = None,
    treeid: Optional[int] = None,
) -> Tuple[str, list]:
    """Compile a `Query` into a parameterized `SELECT ... FROM <spec.table>` statement.

    Returns `(sql, params)` where `sql` uses `?` placeholders and `params` is
    the positional parameter list, matching `db.dbapi.execute(sql, params)`.

    `AND private = 0` is appended unless `can_view_private` is set or the
    type has no `private` column (`spec.has_privacy` is `False`, as for
    `Tag`) -- not a query option, baked in so it cannot be omitted by a
    malformed or malicious request. `AND treeid = ?` is appended the same
    non-optional way whenever `treeid` is given -- see `_where_clauses`.

    `collation`, if given, names a locale collation already ensured to exist
    on the connection (see `resources/object_query.py`'s `_resolve_collation`)
    and is applied to every text-typed `ORDER BY` column (and the matching
    keyset comparisons) via `COLLATE "<collation>"`.

    `dialect` selects which backend-specific SQL to render for any `select`
    or `where` entry that's a `JsonPath`, or any `select` entry that's a
    `RelatedEventDate` (see `_render_json_path`/`_render_related_event_date`)
    rather than a plain column name. Not needed, and may be omitted, for
    plain-column-only queries -- `order_by`/keyset pagination support
    neither yet, so `dialect` never affects them.
    """
    columns = list(query.select) if query.select else sorted(spec.columns)

    effective_order_by = _effective_order_by(query.order_by)
    for ob in effective_order_by:
        _check_column(ob.column, spec.columns)

    select_parts = []
    params: list = []
    for column in columns:
        sql_frag, p = _render_column(
            column, spec, dialect, can_view_private=can_view_private, treeid=treeid
        )
        select_parts.append(sql_frag)
        params.extend(p)

    where_clauses, where_params = _where_clauses(
        spec, query.where, can_view_private, dialect, treeid
    )
    params.extend(where_params)

    if query.after is not None:
        sql, p = _compile_keyset(effective_order_by, query.after, spec, collation)
        where_clauses.append(f"({sql})")
        params.extend(p)

    sql = f"SELECT {', '.join(select_parts)} FROM {spec.table}"
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


def compile_count_query(
    spec: ObjectTypeSpec,
    query: Query,
    *,
    can_view_private: bool = False,
    dialect: Optional[Dialect] = None,
    treeid: Optional[int] = None,
) -> Tuple[str, list]:
    """Compile a `Query` into a parameterized `SELECT COUNT(*) FROM <spec.table>`.

    Uses the same `where`, privacy, and tree-scoping logic as `compile_query`
    -- see there for details -- but ignores `select`/`order_by`/`limit`/
    `after`, since a count has no columns, sort order, or page to return. In
    particular this is a count of *all* matching rows, not of just the
    current keyset page.
    """
    where_clauses, params = _where_clauses(
        spec, query.where, can_view_private, dialect, treeid
    )
    sql = f"SELECT COUNT(*) FROM {spec.table}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    return sql, params
