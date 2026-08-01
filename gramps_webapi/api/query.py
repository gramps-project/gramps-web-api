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
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

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
class ColumnIndex:
    """A `JsonPath` segment whose integer value comes from another column
    on the *current* row, not a compile-time literal -- e.g.
    `event_ref_list[N]` where `N` is this row's `birth_ref_index`. Only
    meaningful inside a `RelatedObject.handle_ref` (see there). `-1` means
    "no such entry" by Gramps' own convention for `birth_ref_index`/
    `death_ref_index`, so rendering code guards this column with `>= 0` --
    required, not defensive: confirmed live that PostgreSQL's `->`
    operator treats a negative array index as "count from the end" rather
    than invalid -- without the guard, a row with no such entry but
    *something else* in the list would silently resolve to that unrelated
    entry.
    """

    column: str


@dataclass(frozen=True)
class JsonPath:
    """A path into a JSON-blob secondary column (default: `json_data`).

    Not whitelisted against a fixed column list the way a plain column name
    is -- `json_data` is a real column on every table, but its *content* is
    arbitrary. Safety instead comes from every path segment being
    individually type-checked (`str` keys, non-bool `int` array indices, or
    a `ColumnIndex` -- see there) and, for `str`/`int` segments, always
    bound as a query parameter, never interpolated into SQL text -- see
    `_render_json_path`. (A `ColumnIndex` segment is inherently a raw SQL
    column reference, not a bindable value -- see `_render_handle_ref`,
    the only place a `JsonPath` containing one is ever rendered; its
    `column` always comes from the fixed internal `_RELATIONSHIPS`
    registry, never from parsed user input, so this is safe.)

    Not (yet) usable in `order_by`/keyset pagination -- only `select` and
    `where`. `ObjectTypeSpec.text_columns`-based `COLLATE` selection also
    doesn't apply to it: the JSON value's type isn't known ahead of time.
    """

    segments: Tuple[Union[str, int, ColumnIndex], ...]
    base_column: str = "json_data"

    def __post_init__(self) -> None:
        if not self.segments:
            raise QueryError("JsonPath requires at least one segment")
        for segment in self.segments:
            if isinstance(segment, ColumnIndex):
                continue
            if isinstance(segment, bool) or not isinstance(segment, (str, int)):
                raise QueryError(f"invalid JsonPath segment: {segment!r}")


@dataclass(frozen=True)
class RelatedObject:
    """A field reached by following a relationship from the current row to
    another table -- a `Family`'s father (-> `Person`), a `Person`'s birth
    event (-> `Event`), an `Event`'s place (-> `Place`), and so on.
    Resolved via a *correlated scalar subquery*, not a `JOIN`: each
    `RelatedObject`'s subquery is a fully independent SQL scope with its
    own `FROM <target.table>`, correlated back to whatever row it's
    reached from by that table's own (never aliased) name -- confirmed
    live this composes correctly at any depth: sibling subqueries hitting
    the same table (father vs. mother, both `FROM person`) don't collide,
    and chains (nested subqueries, for `birth.place.title`-style paths)
    correlate correctly across levels regardless of nesting -- see
    `_render_related_object`.

    `name`: the relationship's name as used in a path (`"birth"`,
        `"father"`, ...) -- kept for error messages and deriving a default
        response key (`"birth.date.sortval"`); not used by the SQL itself.
    `target`: the `ObjectTypeSpec` of the related table.
    `handle_ref`: how to find the related row's handle on the row this
        `RelatedObject` is reached from -- a plain column name for a
        direct foreign key (`"father_handle"`), or a `JsonPath` with
        exactly one `ColumnIndex` segment for a dynamic, per-row index
        (`event_ref_list[<ref_index_column>].ref`).
    `field`: what to pull from the related row once found -- a plain
        (whitelisted) column name, a `JsonPath` into its `json_data`, or
        another `RelatedObject` to keep chaining.

    Not (yet) usable in `order_by`/keyset pagination: `handle_ref` may be
    a per-row dynamic index, fine for a one-off extraction but not
    threaded through machinery that assumes every comparable value lives
    in the base table.
    """

    name: str
    target: ObjectTypeSpec
    handle_ref: ColumnRef
    field: ColumnRef


# Registry of relationship roots, keyed by the *current* table -- the only
# thing that varies per relationship is which table it targets and how to
# find the related row's handle; what to extract from that row (`field`) is
# supplied by whatever's left of the path once the relationship name is
# consumed (see `resolve_column_path`). Adding a new relationship (e.g. a
# Citation's source) is one registry entry, not new rendering code.
_RELATIONSHIPS: dict[str, dict[str, Tuple[ObjectTypeSpec, ColumnRef]]] = {
    PERSON.table: {
        "birth": (
            EVENT,
            JsonPath(("event_ref_list", ColumnIndex("birth_ref_index"), "ref")),
        ),
        "death": (
            EVENT,
            JsonPath(("event_ref_list", ColumnIndex("death_ref_index"), "ref")),
        ),
    },
    FAMILY.table: {
        "father": (PERSON, "father_handle"),
        "mother": (PERSON, "mother_handle"),
    },
    EVENT.table: {
        "place": (PLACE, "place"),
    },
}


def resolve_column_path(
    spec: ObjectTypeSpec, segments: Sequence[Union[str, int]]
) -> ColumnRef:
    """Resolve a dotted/indexed path against `spec` into a `ColumnRef`.

    Recursively walks relationship roots (`_RELATIONSHIPS`) as far as the
    path goes -- `birth.date.sortval` consumes `"birth"` as a relationship
    (`Person` -> `Event`), then resolves the remaining `("date", "sortval")`
    against `EVENT`, which isn't a relationship there, so it becomes a
    `JsonPath`. `birth.place.title` keeps going: `"place"` is *also* a
    relationship (`Event` -> `Place`), consumed the same way, leaving just
    `("title",)` to resolve against `PLACE` (a real flat column there).

    `select`/`where`/`where_expr` (`object_query.py`, `query_lang.py`) all
    funnel through this one resolver, so a path means the same thing
    everywhere it's written.

    A relationship name with nothing after it (`segments == ("birth",)`)
    is rejected explicitly -- there's no value to return for "the related
    row itself", only for a field of it.
    """
    if not segments:
        raise QueryError("empty column path")
    head, *rest = segments
    relationships = _RELATIONSHIPS.get(spec.table, {})
    if isinstance(head, str) and head in relationships:
        if not rest:
            raise QueryError(
                f"{head!r} is a relationship on {spec.table!r}, not a value on its "
                f"own -- use {head}.<field>, e.g. {head}.gramps_id"
            )
        target_spec, handle_ref = relationships[head]
        field = resolve_column_path(target_spec, rest)
        return RelatedObject(name=head, target=target_spec, handle_ref=handle_ref, field=field)
    if len(segments) == 1 and isinstance(head, str) and head in spec.columns:
        return head
    return JsonPath(tuple(segments))


# A column reference is either a plain (whitelisted) column name, a path
# into one column's JSON content, or a field reached via a relationship
# (see `RelatedObject`/`resolve_column_path`) -- `field: ColumnRef` on
# `RelatedObject` makes this recursive, so a chain like `birth.place.title`
# is itself a valid `ColumnRef`.
ColumnRef = Union[str, JsonPath, RelatedObject]
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


def _sqlite_handle_ref_path_sql(
    segments: Sequence[Union[str, int, ColumnIndex]], outer_table: str
) -> str:
    """Build the SQL expression for a JSONPath string used as a `handle_ref`,
    substituting any `ColumnIndex` segment with the live value of that
    column via `||` concatenation, e.g.
    `'$.event_ref_list[' || person.birth_ref_index || '].ref'`. A path with
    no `ColumnIndex` segment collapses to a single literal string, same as
    a normal compile-time-static path.
    """
    fragments: list = []
    literal = "$"
    for segment in segments:
        if isinstance(segment, ColumnIndex):
            literal += "["
            fragments.append(f"'{literal}'")
            fragments.append(f"{outer_table}.{segment.column}")
            literal = "]"
        elif isinstance(segment, int):
            literal += f"[{segment}]"
        else:
            literal += f".{segment}"
    fragments.append(f"'{literal}'")
    return " || ".join(fragments)


def _postgresql_handle_ref_path_sql(
    segments: Sequence[Union[str, int, ColumnIndex]], outer_table: str
) -> str:
    """Build the `->`/`->>` chain for a `handle_ref`, substituting any
    `ColumnIndex` segment with the *unquoted* live value of that column --
    PostgreSQL's `->` operator needs an actual integer (not a quoted
    string) to use its array-index overload rather than its object-key
    overload, confirmed live; a plain `int` literal segment gets the same
    treatment for the same reason.
    """
    expr = f"{outer_table}.json_data::jsonb"
    last_index = len(segments) - 1
    for i, segment in enumerate(segments):
        op = "->>" if i == last_index else "->"
        if isinstance(segment, ColumnIndex):
            expr += f" {op} {outer_table}.{segment.column}"
        elif isinstance(segment, int):
            expr += f" {op} {segment}"
        else:
            expr += f" {op} '{segment}'"
    return expr


def _render_handle_ref(
    handle_ref: ColumnRef, outer_table: str, dialect: Dialect
) -> Tuple[str, Optional[str]]:
    """Render the SQL expression that finds a related row's handle from the
    current row, plus the name of the column to guard with `>= 0` if
    `handle_ref` uses a dynamic `ColumnIndex` segment (`None` for a direct
    foreign key -- a `NULL` handle already fails the equality comparison
    naturally, confirmed live, no guard needed).
    """
    if isinstance(handle_ref, str):
        return f"{outer_table}.{_quote_column(handle_ref)}", None
    if isinstance(handle_ref, JsonPath):
        index_columns = [
            segment.column
            for segment in handle_ref.segments
            if isinstance(segment, ColumnIndex)
        ]
        if len(index_columns) > 1:
            raise QueryError(
                "a handle reference supports at most one dynamic index segment"
            )
        guard_column = index_columns[0] if index_columns else None
        if dialect == Dialect.SQLITE:
            path_expr = _sqlite_handle_ref_path_sql(handle_ref.segments, outer_table)
            return f"json_extract({outer_table}.json_data, {path_expr})", guard_column
        if dialect == Dialect.POSTGRESQL:
            return (
                _postgresql_handle_ref_path_sql(handle_ref.segments, outer_table),
                guard_column,
            )
        raise QueryError(f"unsupported dialect: {dialect!r}")
    raise QueryError(f"invalid handle reference: {handle_ref!r}")


def _guarded_handle_ref_sql(
    handle_ref: ColumnRef, outer_table: str, dialect: Dialect
) -> str:
    """`_render_handle_ref`'s SQL expression, with the dynamic-index `>= 0`
    guard already applied when needed -- the one piece `_render_related_object`
    and `_related_object_privacy_guards` both need identically.
    """
    handle_sql, guard_column = _render_handle_ref(handle_ref, outer_table, dialect)
    if guard_column is not None:
        handle_sql = (
            f"CASE WHEN {outer_table}.{guard_column} >= 0 THEN {handle_sql} ELSE NULL END"
        )
    return handle_sql


def _chain_has_privacy(column: ColumnRef) -> bool:
    """Does `column`'s relationship chain cross any privacy-bearing target,
    at any depth? Guards `Comparison.compile` doing any extra work at all
    for a chain that could never be privacy-masked in the first place.
    """
    while isinstance(column, RelatedObject):
        if column.target.has_privacy:
            return True
        column = column.field
    return False


def _related_object_visible_sql(
    related: RelatedObject, outer_table: str, dialect: Dialect, treeid: Optional[int]
) -> Tuple[str, list]:
    """A scalar subquery evaluating to `0` if some *existing* row along
    `related`'s chain is privacy-blocked, `1`/`NULL` otherwise (`NULL`
    specifically when the chain bottoms out at a handle that doesn't
    resolve to any row at all -- genuinely missing data, not blocked).

    Mirrors `_render_related_object`'s own nesting exactly, level for
    level: each hop's subquery is lexically nested inside its parent's own
    `SELECT`, so it correlates back to that parent's `FROM` the same way
    the field-value fetch already does (confirmed live -- a flat,
    top-level list of per-hop guard clauses instead of this nesting
    referenced an out-of-scope table for any hop past the first, e.g.
    `event.place` with no `event` in the outer query's `FROM` at all).
    See `Comparison.compile`'s use of this for `=`/`!=`.
    """
    target_table = related.target.table
    handle_sql = _guarded_handle_ref_sql(related.handle_ref, outer_table, dialect)
    if isinstance(related.field, RelatedObject):
        nested_sql, nested_params = _related_object_visible_sql(
            related.field, target_table, dialect, treeid
        )
        nested_expr = f"COALESCE(({nested_sql}), 1)"
    else:
        nested_expr, nested_params = "1", []
    select_expr = (
        f"CASE WHEN {target_table}.private = 1 THEN 0 ELSE {nested_expr} END"
        if related.target.has_privacy
        else nested_expr
    )
    where = [f"{target_table}.handle = ({handle_sql})"]
    params: list = []
    if treeid is not None:
        where.append(f"{target_table}.treeid = ?")
        params.append(treeid)
    subquery = f"(SELECT {select_expr} FROM {target_table} WHERE {' AND '.join(where)} LIMIT 1)"
    return subquery, params + nested_params


def _render_related_object(
    related: RelatedObject,
    outer_table: str,
    dialect: Optional[Dialect],
    can_view_private: bool,
    treeid: Optional[int],
    value: Any = None,
) -> Tuple[str, list]:
    """Render a `RelatedObject` as a correlated scalar subquery.

    ```sql
    (SELECT <field extraction> FROM <target.table>
     WHERE <target.table>.handle = <handle_ref, CASE-guarded if dynamic>
       AND <target.table>.private = 0    -- unless can_view_private
       AND <target.table>.treeid = ?     -- when treeid is given
     LIMIT 1)
    ```

    Not a `JOIN` -- a self-contained SQL scope with its own `FROM`,
    correlated back to `outer_table` by name, never aliased. Confirmed
    live this composes correctly at any depth: sibling subqueries
    referencing the same table (father vs. mother, both `FROM person`)
    don't collide with each other, and a chain (nested `SELECT`s, for a
    path like `birth.place.title`) correlates correctly across levels --
    each `RelatedObject`'s subquery is an independent scope regardless of
    how deep it's nested.

    Privacy/`treeid` scoping apply to *this* subquery's own row, not the
    outer query -- a private related row with no view permission makes
    this field come back `null`, not exclude the outer row from the
    results entirely.

    `value` (a `where`-comparison's right-hand value, `None` for `select`)
    only affects rendering when `field` is a `JsonPath` -- forwarded to
    `_render_json_path` for the same numeric/boolean cast selection
    already used for a plain `JsonPath` column. A `field` that's a plain
    column ignores it (no text-vs-numeric ambiguity for a real column); a
    `field` that's another (chained) `RelatedObject` forwards it one more
    level down to wherever the leaf comparison actually happens.
    """
    if dialect is None:
        raise QueryError(
            f"a dialect is required to compile a relationship path ({related.name!r}), "
            "but none was given"
        )
    target_table = related.target.table

    handle_sql = _guarded_handle_ref_sql(related.handle_ref, outer_table, dialect)

    if isinstance(related.field, RelatedObject):
        field_sql, field_params = _render_related_object(
            related.field, target_table, dialect, can_view_private, treeid, value
        )
    elif isinstance(related.field, JsonPath):
        field_sql, field_params = _render_json_path(related.field, dialect, value)
    else:
        _check_column(related.field, related.target.columns)
        field_sql, field_params = _quote_column(related.field), []

    subquery_where = [f"{target_table}.handle = ({handle_sql})"]
    where_params: list = []
    if related.target.has_privacy and not can_view_private:
        subquery_where.append(f"{target_table}.private = 0")
    if treeid is not None:
        subquery_where.append(f"{target_table}.treeid = ?")
        where_params.append(treeid)

    subquery = (
        f"(SELECT {field_sql} FROM {target_table} "
        f"WHERE {' AND '.join(subquery_where)} LIMIT 1)"
    )
    return subquery, field_params + where_params


def _render_column(
    column: ColumnRef,
    spec: ObjectTypeSpec,
    dialect: Optional[Dialect],
    value: Any = None,
    can_view_private: bool = False,
    treeid: Optional[int] = None,
) -> Tuple[str, list]:
    """Render a column reference (plain name, `JsonPath`, or `RelatedObject`).

    Used for both `SELECT` list entries (no right-hand value to bind,
    `value` stays `None`) and `WHERE` comparisons. `value`, when given, is
    the comparison's right-hand Python value -- used only to pick a
    `JsonPath`/`RelatedObject` cast (see `_render_json_path`/
    `_render_related_object`); ignored for plain column names.
    `can_view_private`/`treeid` are only used by `RelatedObject`, whose
    correlated subquery needs its own privacy/tree-scoping independent of
    the outer query's.
    """
    if isinstance(column, RelatedObject):
        return _render_related_object(
            column, spec.table, dialect, can_view_private, treeid, value
        )
    if isinstance(column, JsonPath):
        return _render_json_path(column, _require_dialect(dialect, column), value)
    _check_column(column, spec.columns)
    return _quote_column(column), []


# --- WHERE: comparison leaves -----------------------------------------------


#: Operators for which a field-vs-field comparison gets a numeric-cast hint
#: (see `Comparison.compile`) -- ordering only, not equality.
_ORDERING_OPS = frozenset({"<", "<=", ">", ">="})

#: `=`/`!=` render as `IS [NOT] DISTINCT FROM` instead -- NULL-safe
#: equality, so a missing value is treated as a distinct, comparable value
#: rather than "unknown" (SQL's default three-valued-logic behavior for
#: `=`/`!=`, which silently drops any row where either side is NULL from
#: *both* an `eq` and an `ne` count). This matters most for field-vs-field
#: comparisons -- "born and died in different places" should include
#: "died in an unknown place", not silently exclude it -- but applies
#: uniformly to literal comparisons too, for the same reason. Requires
#: SQLite 3.39+ (2022-06-25); standard, unconditionally supported on
#: PostgreSQL.
_NULL_SAFE_OPS = {"=": "IS NOT DISTINCT FROM", "!=": "IS DISTINCT FROM"}


class Comparison:
    """Base class for single-column comparison leaves (`Eq`, `Lt`, ...).

    `value` is normally a literal, always bound as a `?` parameter. It can
    also be another `JsonPath`/`RelatedObject` -- a *field-vs-field*
    comparison, e.g. "families where the mother's death date is before the
    father's" (`Lt(mother_death_sortval, father_death_sortval)`). Plain
    `str` is deliberately never treated as a field reference here (only
    `JsonPath`/`RelatedObject` are) -- a bare string is exactly as likely
    to be a literal value (`Eq("surname", "Smith")`) as a column name, and
    there's no way to tell which was meant; `JsonPath`/`RelatedObject`
    carry no such ambiguity; nothing constructs one to represent a literal.
    """

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
        is_field_comparison = isinstance(self.value, (JsonPath, RelatedObject))
        # A field-vs-field comparison has no literal runtime value to infer
        # a numeric/boolean cast from (unlike field-vs-value) -- pick it
        # structurally instead: an *ordering* comparison between two paths
        # is overwhelmingly a numeric/date comparison in practice (e.g. two
        # `sortval`s), so hint numeric via a dummy int (only its *type* is
        # inspected by `_render_json_path`/`_render_related_object`, never
        # its value). Equality doesn't need this: an exact TEXT match is
        # correct whether the underlying value is numeric or textual, as
        # long as both sides extract the same way -- which they do, so
        # `cast_hint` naturally falls back to `self.value` there (a
        # JsonPath/RelatedObject instance, neither bool nor numeric, so it
        # still renders as TEXT on both sides via the existing type checks).
        cast_hint = 0 if is_field_comparison and self.op in _ORDERING_OPS else self.value
        sql_op = _NULL_SAFE_OPS.get(self.op, self.op)
        column_sql, column_params = _render_column(
            self.column,
            spec,
            dialect,
            value=cast_hint,
            can_view_private=can_view_private,
            treeid=treeid,
        )
        if is_field_comparison:
            value_sql, value_params = _render_column(
                self.value,
                spec,
                dialect,
                value=cast_hint,
                can_view_private=can_view_private,
                treeid=treeid,
            )
            comparison_sql = f"{column_sql} {sql_op} {value_sql}"
            comparison_params = column_params + value_params
        else:
            comparison_sql = f"{column_sql} {sql_op} ?"
            comparison_params = column_params + [self.value]

        if self.op not in _NULL_SAFE_OPS or can_view_private:
            # Ordering/LIKE/etc. already exclude a privacy-masked NULL via
            # standard SQL three-valued logic -- no guard needed. Nor is
            # one needed at all if the caller can see private data anyway.
            return comparison_sql, comparison_params

        # `=`/`!=` are NULL-safe, so a privacy-masked field must be
        # explicitly excluded here rather than left to participate as
        # comparable data -- see `_related_object_visible_sql`.
        guards: List[str] = []
        guard_params: list = []
        for ref in [self.column] + ([self.value] if is_field_comparison else []):
            if isinstance(ref, RelatedObject) and _chain_has_privacy(ref):
                assert dialect is not None  # already required to have rendered `ref` itself
                visible_sql, visible_params = _related_object_visible_sql(
                    ref, spec.table, dialect, treeid
                )
                guards.append(f"COALESCE(({visible_sql}), 1) = 1")
                guard_params.extend(visible_params)
        if not guards:
            return comparison_sql, comparison_params
        # A blocked comparison must become SQL NULL (unknown), not a
        # hardcoded FALSE -- `(guard) AND (comparison)` reads as a
        # definite FALSE when blocked, and `NOT FALSE` is TRUE, which
        # flips a wrapping `Not(...)` into wrongly matching (confirmed
        # live: `Not(Eq(masked_field, 'real value'))` matched a row it
        # should have excluded). NULL propagates correctly through NOT,
        # AND, and OR on its own via SQL's native three-valued logic --
        # `NOT NULL`, `NULL AND x`, and `x OR NULL` all stay non-TRUE
        # (except `TRUE OR NULL`, correctly still TRUE: an independently
        # visible, genuinely-matching sibling condition should still be
        # able to confirm a match) -- so no per-combinator special-casing
        # is needed, just picking the right "blocked" value here.
        return (
            f"CASE WHEN {' AND '.join(guards)} THEN ({comparison_sql}) ELSE NULL END",
            guard_params + comparison_params,
        )

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
    or `where` entry that's a `JsonPath` or a `RelatedObject` (see
    `_render_json_path`/`_render_related_object`) rather than a plain
    column name. Not needed, and may be omitted, for plain-column-only
    queries -- `order_by`/keyset pagination support neither yet, so
    `dialect` never affects them.
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
