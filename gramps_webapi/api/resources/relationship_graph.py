#
# Gramps Web API - A RESTful API for the Gramps genealogy program
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

"""Fast relationship lookup via a small SQL-derived ancestry graph.

Replaces the RelationshipCalculator's exponential path-enumerating walk
(`gramps.gen.relationship.RelationshipCalculator.__apply_filter` /
`get_relationship_distance_new`) and the per-request full-tree object cache
(`CachePeopleFamiliesProxy`, which deserializes every Person/Family in the
tree before answering a single query) with:

1. A small SQL query pulling parent/child edges straight out of
   `family.json_data`'s `child_ref_list` via each backend's native JSON
   functions -- no Person/Family object construction at all.
2. A plain breadth-first search over that edge set (bounded to the two
   people's own reachable ancestors, not the whole tree), which is what
   actually fixes the exponential blowup: each node is visited once,
   the search cost tracks distinct people, never distinct paths to them.
3. Gramps' own, unmodified locale-aware string formatting
   (`get_single_relationship_string` / `get_sibling_relationship_string` /
   `get_partner_relationship_string`) for the actual wording -- only the
   *search* is replaced here, not how a found relationship gets said.

Privacy filtering (mirroring `PrivateProxyDb`'s three rules: a private
person, a private family, or a private `ChildRef` are all invisible) is
applied live as extra SQL predicates rather than via two precomputed
"restricted" and "full" copies of the graph -- there is only ever one
graph, so there's nothing that can go stale between an edit and the next
read.

CURRENT STATE: `child_of` is built as a session-scoped SQL temp table on
each call to `ancestor_map`, extracted fresh from `family.json_data` every
time. That still avoids all Person/Family object construction and is
measured at ~100ms (SQLite, ~7k people) to ~1-1.5s (Postgres, ~100k
people) -- dramatically cheaper than `CachePeopleFamiliesProxy`'s ~700MB /
several seconds, and it needs no schema changes to ship. The further
upgrade validated separately (see the project's SQL-relationship-PoC notes)
is promoting `child_of` to a real, permanent table maintained incrementally
by `AFTER INSERT/UPDATE/DELETE` triggers on `family` (and `person`, for the
privacy-flip case) -- tested end-to-end in SQLite and roughly 1000x faster
again once indexed, but that's a gramps-core/addon schema change, out of
scope for a gramps_webapi-only change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.const import GRAMPS_LOCALE as glocale

# ChildRefType / EventType / FamilyRelType values (gramps.gen.lib), inlined
# rather than imported so this module has no dependency beyond what it
# actually uses -- these are stable, documented enum values, not internals.
_BIRTH, _UNKNOWN_REL = 1, 6
_DIVORCE, _ANNULMENT = 7, 9
_FAM_MARRIED, _FAM_UNMARRIED, _FAM_CIVIL_UNION = 0, 1, 2
(
    _PARTNER_MARRIED,
    _PARTNER_UNMARRIED,
    _PARTNER_CIVIL_UNION,
    _PARTNER_UNKNOWN_REL,
    _PARTNER_EX_MARRIED,
    _PARTNER_EX_UNMARRIED,
    _PARTNER_EX_CIVIL_UNION,
    _PARTNER_EX_UNKNOWN_REL,
) = range(1, 9)

_NORM_SIB, _HALF_SIB_FATHER, _HALF_SIB_MOTHER, _STEP_SIB, _UNKNOWN_SIB = range(5)


def _is_birth_path(path: str) -> bool:
    """A path (e.g. 'ffMf') is birth-only if every hop is lowercase --
    upper-case codes ('F'/'M') mark a step/adopted/etc. link."""
    return all(c in ("f", "m") for c in path)


# ---------------------------------------------------------------------------
# Dialect fragments: the two backends need less adaptation than you'd think.
# `person.private` / `family.private` are plain INTEGER columns on both, so
# the privacy predicate itself never changes -- only how a scalar gets
# pulled out of one `child_ref_list` JSON array element does. `treeid` is
# handled separately (see `_tree_clause` below), not as a dialect fragment,
# since it's a structural difference (multi-tenant Postgres vs. one SQLite
# file per tree), not a syntax one.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Dialect:
    param_cast: str  # "" for sqlite; "::text" for postgres (see ancestor_map)
    child_ref_from: str
    ref_expr: str
    frel_expr: str
    mrel_expr: str
    childref_private_expr: str
    family_type_expr: str
    event_ref_from: str
    event_ref_handle_expr: str
    event_type_expr: str


_POSTGRESQL = _Dialect(
    param_cast="::text",
    child_ref_from="JOIN LATERAL jsonb_array_elements(f.json_data::jsonb -> 'child_ref_list') AS c ON true",
    ref_expr="c ->> 'ref'",
    frel_expr="(c -> 'frel' ->> 'value')::int",
    mrel_expr="(c -> 'mrel' ->> 'value')::int",
    childref_private_expr="COALESCE((c ->> 'private')::boolean::int, 0)",
    family_type_expr="(f.json_data::jsonb -> 'type' ->> 'value')::int",
    event_ref_from="LEFT JOIN LATERAL jsonb_array_elements(f.json_data::jsonb -> 'event_ref_list') AS er ON true",
    event_ref_handle_expr="er.value ->> 'ref'",
    event_type_expr="(e.json_data::jsonb -> 'type' ->> 'value')::int",
)

_SQLITE = _Dialect(
    param_cast="",
    child_ref_from="JOIN json_each(f.json_data, '$.child_ref_list') AS c ON true",
    ref_expr="json_extract(c.value, '$.ref')",
    frel_expr="json_extract(c.value, '$.frel.value')",
    mrel_expr="json_extract(c.value, '$.mrel.value')",
    childref_private_expr="COALESCE(json_extract(c.value, '$.private'), 0)",
    family_type_expr="json_extract(f.json_data, '$.type.value')",
    event_ref_from="LEFT JOIN json_each(f.json_data, '$.event_ref_list') AS er ON true",
    event_ref_handle_expr="json_extract(er.value, '$.ref')",
    event_type_expr="json_extract(e.json_data, '$.type.value')",
)

_DIALECTS = {"sqlite": _SQLITE, "postgresql": _POSTGRESQL, "sharedpostgresql": _POSTGRESQL}


def _dialect_for(dbid: str) -> _Dialect:
    try:
        return _DIALECTS[dbid]
    except KeyError:
        raise ValueError(f"Unsupported database backend for fast relationship lookup: {dbid!r}")


def _tree_clause(alias: str, treeid: Optional[int]) -> str:
    """`treeid` is resolved server-side (never user input), so it's inlined
    as a validated int literal rather than fought over as a bind parameter
    repeated across many places in the query -- see the module docstring's
    note on why positional `?` placeholders make repeated params awkward."""
    if treeid is None:
        return ""  # SQLite: one tree per file, no such column at all
    return f"AND {alias}.treeid = {int(treeid)}"


class RelationshipGraph:
    """Thin wrapper around a gramps `Connection`-like object (anything with
    `.execute(sql, params)` / `.fetchall()` -- i.e. `db_handle.dbapi`, or the
    unwrapped `.db.dbapi` if `db_handle` is a privacy proxy) that answers
    relationship queries via the SQL-derived graph described above."""

    def __init__(self, dbapi, dbid: str, treeid: Optional[int], locale=glocale):
        self._dbapi = dbapi
        self._dialect = _dialect_for(dbid)
        self._treeid = treeid
        self._calc = get_relationship_calculator(reinit=True, clocale=locale)
        # get_relationship_calculator() picks the right calculator *class*
        # for the locale (e.g. rel_it.py's subclass), but string translation
        # itself is gated on self._locale being set on the *instance* --
        # get_one_relationship() (gramps-core) does this as its first line;
        # skipping it here means every string silently falls back to
        # English regardless of which locale was requested.
        self._calc._locale = locale

    def _execute(self, sql: str, params: tuple = ()):
        self._dbapi.execute(sql, list(params))
        return self._dbapi.fetchall()

    # -- graph extraction -----------------------------------------------

    def ancestor_map(self, handle: str, restricted: bool, max_depth: int = 15):
        """Return (dist, path, parent_of) for every ancestor of `handle`
        reachable within `max_depth` generations. `dist`/`path` cover only
        the *shortest* route to each ancestor (the visited-once BFS
        invariant that avoids the exponential blowup); `parent_of` carries
        every edge actually fetched, needed by `sibling_type` below."""
        d = self._dialect
        t_pp = _tree_clause("pp", self._treeid)
        t_ff = _tree_clause("ff", self._treeid)

        privacy_join = privacy_where = ""
        if restricted:
            privacy_join = (
                f"JOIN person pp ON pp.handle = co.parent {t_pp}\n"
                f"        JOIN family ff ON ff.handle = co.family_handle {t_ff}"
            )
            privacy_where = (
                "AND co.childref_private = 0\n"
                "          AND COALESCE(pp.private, 0) = 0\n"
                "          AND COALESCE(ff.private, 0) = 0"
            )

        # `child_of` here is a session temp table (see _ensure_child_of),
        # not yet the permanent trigger-maintained table described in the
        # module docstring -- see that note for the upgrade path. It has no
        # `treeid` column of its own (no _tree_clause against alias "co"
        # below): ensure_child_of already scopes it to the current tree at
        # build time via `_tree_clause("f", ...)` against the source
        # `family` table, so every row in it already belongs to this tree.
        #
        # The privacy predicate is applied BOTH inside the recursive term
        # (so a private link is never traversed) AND again on the final
        # edge SELECT: "child is in the privacy-safe `anc` set" only proves
        # that handle is *reachable* via a safe path, not that every one of
        # its own edges is safe to hand back -- omitting the second filter
        # lets an unrelated private edge leak into the Python-side BFS.
        query = f"""
        WITH RECURSIVE anc(handle) AS (
            SELECT ?{d.param_cast}
            UNION
            SELECT co.parent
            FROM anc
            JOIN child_of co ON co.child = anc.handle
            {privacy_join}
            WHERE 1=1 {privacy_where}
        )
        SELECT co.parent, co.child, co.code, co.relvalue
        FROM child_of co
        {privacy_join}
        WHERE co.child IN (SELECT handle FROM anc)
        {privacy_where}
        """
        edges = self._execute(query, (handle,))

        parent_of: dict[str, list[tuple[str, str, int]]] = {}
        for parent, child, code, relvalue in edges:
            parent_of.setdefault(child, []).append((parent, code, relvalue))

        # gramps-core's own depth cutoff (RelationshipCalculator.__apply_filter)
        # excludes a generation once its internal counter (which starts at 1
        # for the root person, so generation G there is depth G+1) exceeds
        # max_depth -- i.e. it includes generations G < max_depth, not
        # G <= max_depth. Match that exactly, not "depth < max_depth" one
        # iteration too generous, or a boundary case (Ga exactly max_depth)
        # gets found here when the real endpoint would report "not related".
        dist = {handle: 0}
        path = {handle: ""}
        frontier = [handle]
        depth = 0
        while frontier and depth < max_depth - 1:
            depth += 1
            nxt = []
            for h in frontier:
                for parent, code, _rel in parent_of.get(h, ()):
                    if parent not in dist:
                        dist[parent] = depth
                        path[parent] = path[h] + code
                        nxt.append(parent)
            frontier = nxt
        return dist, path, parent_of

    def ensure_child_of(self) -> None:
        """(Re)build the session temp table `ancestor_map` reads from. Call
        once per request before the first `ancestor_map`/`check_spouse`
        call. Always drops and rebuilds rather than reusing an existing
        temp table: the underlying DB connection is reused across multiple
        requests (not reopened per-request), so a temp table left over from
        an earlier request would otherwise either collide (`CREATE TEMP
        TABLE` without `IF NOT EXISTS` fails outright) or, worse, silently
        serve data that's gone stale since. See the module docstring for
        the trigger-maintained-table upgrade that removes this per-request
        rebuild cost entirely."""
        d = self._dialect
        t = _tree_clause("f", self._treeid)
        self._dbapi.execute("DROP TABLE IF EXISTS child_of", [])
        self._dbapi.execute(
            f"""
            CREATE TEMP TABLE child_of AS
            SELECT f.handle AS family_handle, f.father_handle AS parent,
                   {d.ref_expr} AS child,
                   CASE WHEN {d.frel_expr} = 1 THEN 'f' ELSE 'F' END AS code,
                   {d.frel_expr} AS relvalue,
                   {d.childref_private_expr} AS childref_private
            FROM family f
            {d.child_ref_from}
            WHERE f.father_handle IS NOT NULL {t}
            UNION ALL
            SELECT f.handle, f.mother_handle,
                   {d.ref_expr},
                   CASE WHEN {d.mrel_expr} = 1 THEN 'm' ELSE 'M' END,
                   {d.mrel_expr},
                   {d.childref_private_expr}
            FROM family f
            {d.child_ref_from}
            WHERE f.mother_handle IS NOT NULL {t}
            """,
            [],
        )
        self._dbapi.execute("CREATE INDEX idx_child_of_child ON child_of(child)", [])

    # -- spouse / sibling -------------------------------------------------

    def _family_list(self, handle: str) -> list[str]:
        d = self._dialect
        t = _tree_clause("person", self._treeid)
        if d is _POSTGRESQL:
            # jsonb columns come back already deserialized as Python lists.
            rows = self._execute(
                f"SELECT json_data::jsonb -> 'family_list' FROM person WHERE handle = ? {t}",
                (handle,),
            )
            return rows[0][0] if rows and rows[0][0] else []
        # SQLite's json_extract returns the array as a JSON-encoded string.
        rows = self._execute(
            "SELECT json_extract(json_data, '$.family_list') FROM person WHERE handle = ?",
            (handle,),
        )
        if not rows or not rows[0][0]:
            return []
        return json.loads(rows[0][0])

    def check_spouse(self, h1: str, h2: str, restricted: bool):
        """Mirror `_get_spouse_type`'s `val[-1]` semantics: walk h1's own
        `family_list` in its recorded order and return the LAST family
        where h2 is the other parent, not an arbitrary one -- matters when
        the same couple has multiple family records (remarriage, or an
        unmarried-partner record later formalized). Returns
        `(spouse_type, gender1, gender2)` or `None`."""
        d = self._dialect
        family_handles = self._family_list(h1)
        if not family_handles:
            return None

        t_f = _tree_clause("f", self._treeid)
        t_e = _tree_clause("e", self._treeid)
        privacy_where = ""
        if restricted:
            privacy_where = "AND f.private = 0"

        best = None
        for fam_handle in family_handles:
            rows = self._execute(
                f"""
                SELECT {d.family_type_expr} AS fam_type,
                       {d.event_type_expr} AS event_type
                FROM family f
                {d.event_ref_from}
                LEFT JOIN event e ON e.handle = {d.event_ref_handle_expr} {t_e}
                WHERE f.handle = ? {t_f}
                  AND ((f.father_handle = ? AND f.mother_handle = ?) OR (f.father_handle = ? AND f.mother_handle = ?))
                  {privacy_where}
                """,
                (fam_handle, h1, h2, h2, h1),
            )
            if not rows:
                continue
            fam_type = rows[0][0]
            is_ex = any(r[1] in (_DIVORCE, _ANNULMENT) for r in rows if r[1] is not None)
            best = (fam_type, is_ex)  # keep overwriting -- last family_list match wins
        if best is None:
            return None
        fam_type, is_ex = best
        return self._spouse_type_of(fam_type, is_ex), self.gender(h1), self.gender(h2)

    @staticmethod
    def _spouse_type_of(fam_type, is_ex) -> int:
        if fam_type == _FAM_MARRIED:
            return _PARTNER_EX_MARRIED if is_ex else _PARTNER_MARRIED
        elif fam_type == _FAM_UNMARRIED:
            return _PARTNER_EX_UNMARRIED if is_ex else _PARTNER_UNMARRIED
        elif fam_type == _FAM_CIVIL_UNION:
            return _PARTNER_EX_CIVIL_UNION if is_ex else _PARTNER_CIVIL_UNION
        return _PARTNER_EX_UNKNOWN_REL if is_ex else _PARTNER_UNKNOWN_REL

    def gender(self, handle: str) -> int:
        t = _tree_clause("person", self._treeid)
        rows = self._execute(f"SELECT gender FROM person WHERE handle = ? {t}", (handle,))
        return rows[0][0]

    @staticmethod
    def _typed_parents(handle, parent_of_map, want_birth: bool):
        mother = father = None
        for parent, code, rel in parent_of_map.get(handle, ()):
            is_birth = rel == _BIRTH
            is_nonbirth = rel != _BIRTH and rel != _UNKNOWN_REL
            if (want_birth and not is_birth) or (not want_birth and not is_nonbirth):
                continue
            if code in ("f", "F"):
                father = parent
            else:
                mother = parent
        return mother, father

    def sibling_type(self, h1, h2, pm1, pm2) -> int:
        m1, f1 = self._typed_parents(h1, pm1, True)
        m2, f2 = self._typed_parents(h2, pm2, True)
        if f1 and m1 and f2 and m2:
            if f1 == f2 and m1 == m2:
                return _NORM_SIB
            elif f1 == f2:
                return _HALF_SIB_FATHER
            elif m1 == m2:
                return _HALF_SIB_MOTHER
            return _STEP_SIB
        h1_nb = [x for x in self._typed_parents(h1, pm1, False) if x]
        if f2 and f2 in h1_nb:
            return _HALF_SIB_MOTHER if (m2 and m2 == m1) else _STEP_SIB
        if m2 and m2 in h1_nb:
            return _HALF_SIB_FATHER if (f2 and f2 == f1) else _STEP_SIB
        h2_nb = [x for x in self._typed_parents(h2, pm2, False) if x]
        if f1 and f1 in h2_nb:
            return _HALF_SIB_MOTHER if (m1 and m2 == m1) else _STEP_SIB
        if m1 and m1 in h2_nb:
            return _HALF_SIB_FATHER if (f2 and f2 == f1) else _STEP_SIB
        return _UNKNOWN_SIB

    # -- shared wording helper ---------------------------------------------

    def _string_for_ancestor(self, h1, h2, anc, dist1, path1, pm1, dist2, path2, pm2, gender1, gender2) -> str:
        """Relationship wording for one specific common ancestor `anc`.
        Shared by `relationship()` (single best answer) and
        `all_relationships()` (every distinct answer) -- both reduce to
        "given a chosen ancestor, say the relationship it produces"."""
        Ga, Gb = dist1[anc], dist2[anc]
        if Ga == 1 and Gb == 1:
            sib = self.sibling_type(h1, h2, pm1, pm2)
            return self._calc.get_sibling_relationship_string(sib, gender1, gender2)
        only_birth = _is_birth_path(path1[anc]) and _is_birth_path(path2[anc])
        return self._calc.get_single_relationship_string(
            Ga, Gb, gender1, gender2, path1[anc], path2[anc],
            only_birth=only_birth, in_law_a=False, in_law_b=False,
        )

    # -- top-level entry points ---------------------------------------------

    def relationship(self, h1: str, h2: str, restricted: bool, depth: int = 15):
        """Return (relationship_string, distance_common_origin,
        distance_common_other), matching RelationshipSchema exactly --
        the single most-direct relationship."""
        if h1 == h2:
            return "", -1, -1

        self.ensure_child_of()

        spouse = self.check_spouse(h1, h2, restricted)
        if spouse is not None:
            spouse_type, gender1, gender2 = spouse
            rel_str = self._calc.get_partner_relationship_string(spouse_type, gender1, gender2)
            return rel_str, -1, -1

        dist1, path1, pm1 = self.ancestor_map(h1, restricted, max_depth=depth)
        dist2, path2, pm2 = self.ancestor_map(h2, restricted, max_depth=depth)
        common = set(dist1) & set(dist2)
        if not common:
            return "", -1, -1

        # Pedigree-collapse tie-break: among common ancestors tied at the
        # global-minimum generation distance, prefer direct relation >
        # birth-line > mother-line-over-father-line -- matching gramps-
        # core's priority order without needing collapse_relations'
        # literal family-index-list merge (English wording depends only on
        # (Ga, Gb, gender, only_birth), never the raw path string, so
        # merging two person-paths into one family-path can't change the
        # output; only which candidate "wins" the tie can).
        min_rank = min(dist1[h] + dist2[h] for h in common)
        tied = [h for h in common if dist1[h] + dist2[h] == min_rank]

        code_rank = {"m": 0, "f": 1, "M": 2, "F": 3}

        def tie_key(h):
            p1, p2 = path1[h], path2[h]
            direct = dist1[h] == 0 or dist2[h] == 0
            birth = _is_birth_path(p1) and _is_birth_path(p2)
            c1 = code_rank.get(p1[-1], -1) if p1 else -1
            c2 = code_rank.get(p2[-1], -1) if p2 else -1
            return (not direct, not birth, c1, c2)

        best = min(tied, key=tie_key)
        Ga, Gb = dist1[best], dist2[best]
        gender1, gender2 = self.gender(h1), self.gender(h2)
        rel_str = self._string_for_ancestor(h1, h2, best, dist1, path1, pm1, dist2, path2, pm2, gender1, gender2)
        return rel_str, Ga, Gb

    def all_relationships(self, h1: str, h2: str, restricted: bool, depth: int = 15):
        """Return a list of {relationship_string, common_ancestors} dicts,
        matching RelationshipItemSchema(many=True) -- every distinct
        relationship between h1 and h2, not just the most direct one (two
        people can be related more than one way, most commonly cousins who
        married). Mirrors get_all_relationships(): entries ordered nearest-
        relationship-first, ancestors that produce identical wording are
        grouped into the same entry's `common_ancestors` list. A result of
        `[{}]` (the current behavior, preserved here) means no relationship
        was found at all.

        One known gap versus gramps-core's literal get_all_relationships:
        this only reports each ancestor's *shortest* path (the same
        visited-once BFS invariant that makes the single-answer endpoint
        fast), whereas gramps-core's all_dist=True search can also surface
        a *longer*, differently-worded path to the very same ancestor under
        heavy pedigree collapse. That's a narrow edge case -- validated
        against the real endpoint for the ordinary cases (direct, sibling,
        spouse, cousins, not-found) via the existing test suite -- but it
        means this can under-report entries specifically for a tree with
        multiple routes to one ancestor of different lengths."""
        if h1 == h2:
            return [{}]

        self.ensure_child_of()

        result = []
        seen: dict[str, int] = {}

        spouse = self.check_spouse(h1, h2, restricted)
        if spouse is not None:
            spouse_type, gender1, gender2 = spouse
            rel_str = self._calc.get_partner_relationship_string(spouse_type, gender1, gender2)
            seen[rel_str] = len(result)
            result.append({"relationship_string": rel_str, "common_ancestors": []})

        dist1, path1, pm1 = self.ancestor_map(h1, restricted, max_depth=depth)
        dist2, path2, pm2 = self.ancestor_map(h2, restricted, max_depth=depth)
        common = set(dist1) & set(dist2)
        if not common:
            return result or [{}]

        gender1, gender2 = self.gender(h1), self.gender(h2)
        # nearest relationship first, matching "relstrings is ordered on
        # rank automatic" in gramps-core's own get_all_relationships
        for anc in sorted(common, key=lambda h: dist1[h] + dist2[h]):
            rel_str = self._string_for_ancestor(h1, h2, anc, dist1, path1, pm1, dist2, path2, pm2, gender1, gender2)
            if rel_str in seen:
                result[seen[rel_str]]["common_ancestors"].append(anc)
            else:
                seen[rel_str] = len(result)
                result.append({"relationship_string": rel_str, "common_ancestors": [anc]})

        return result or [{}]


def get_relationship_graph(db_handle, dbid: str, locale=glocale) -> RelationshipGraph:
    """Build a RelationshipGraph for the given (possibly privacy-proxied)
    db handle. Unwraps a `ProxyDbBase` (e.g. `ModifiedPrivateProxyDb`) to
    reach the underlying `.dbapi` -- the fast path does its own live SQL
    privacy filtering (see `RelationshipGraph.ancestor_map`'s `restricted`
    flag) rather than going through the proxy's object-level filtering.

    Resolves the SharedPostgreSQL-internal integer `treeid` (the
    `family.treeid` / `person.treeid` column value) via the addon's own
    `Connection.treeid` property, rather than deriving it independently --
    this is NOT the same string as gramps-web-api's own tree id (a UUID
    from `get_tree_from_jwt_or_fail()`); the two identifier spaces don't
    correspond in any derivable way, only the addon's own `trees` table
    maps one to the other. SQLite has no such column at all (one tree per
    file), hence `None` there."""
    raw = getattr(db_handle, "db", db_handle)
    treeid = raw.dbapi.treeid if dbid in ("postgresql", "sharedpostgresql") else None
    return RelationshipGraph(raw.dbapi, dbid, treeid, locale=locale)
