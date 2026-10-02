#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2003-2005  Donald N. Allingham
# Copyright (C) 2026       Gramps Development Team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""Fix exponential relationship search under pedigree collapse.

Backport of https://github.com/gramps-project/gramps/pull/2526 to the
Gramps version currently pinned by Gramps Web API. The methods below are
copied verbatim from that PR and grafted onto
`gramps.gen.relationship.RelationshipCalculator` by `apply_patch`.

The class defined here is deliberately named `RelationshipCalculator` so
that Python's name mangling of the double-underscore attributes it uses
(`self.__max_depth`, `self.__apply_filter`, ...) matches the original
class.

Remove this module once the pinned Gramps version contains the fix.
"""

from gramps.gen import relationship
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import ChildRefType

_ = glocale.translation.sgettext


class RelationshipCalculator:
    """Methods to be patched into Gramps' RelationshipCalculator."""

    # upstream sets this in `__init__`
    max_common_results = 2000

    def set_max_common_results(self, max_common_results):
        """
        Bound how many distinct non-dominated common-ancestor paths
        `get_relationship_distance_new(all_dist=True)` will compute
        before stopping, nearest-relationship-first. `None` means
        unbounded (the original, pre-cap behavior) -- only appropriate
        for a tree known not to have extreme pedigree collapse, since an
        unbounded search can be combinatorial on one that does.
        """
        self.max_common_results = max_common_results

    def get_max_common_results(self):
        """
        Obtain the current cap on common-ancestor paths searched by
        `get_relationship_distance_new(all_dist=True)` -- see
        `set_max_common_results`.
        """
        return self.max_common_results

    @staticmethod
    def _prefix_minimal(pairs):
        """`pairs`: a list of (rel_str, other_value) tuples, all paths
        from the same person to the same target, as accumulated in a
        `pmap` entry. Returns the subset (in original relative order)
        whose `rel_str` is not properly prefixed by another `rel_str` in
        the same list.

        This is a safe reduction of the input to `get_relationship_distance_new`'s
        `common`-list computation below, not a change to its output:
        if some path B is properly prefixed by another path A to the same
        target, then for *any* partner path P paired with B (rank =
        len(B)+len(P)), the corresponding pairing of A with that same P
        (rank = len(A)+len(P), strictly smaller) already satisfies that
        computation's own domination test against B's pairing -- A is a
        prefix of B (given) and P is trivially a "prefix" of itself. So a
        B-pairing can never survive that computation regardless of what
        else is being compared, and generating it at all (let alone
        comparing it against every other candidate one by one) is
        wasted, sometimes catastrophically so under heavy pedigree
        collapse -- a single pair on a real 100,000-person tree was
        observed with 696,320 candidate pairings for one shared ancestor
        alone before this reduction.
        """
        order = sorted(range(len(pairs)), key=lambda i: (pairs[i][0], i))
        keep = set()
        last_kept = None
        for i in order:
            rel_str = pairs[i][0]
            if (
                last_kept is not None
                and len(last_kept) < len(rel_str)
                and rel_str.startswith(last_kept)
            ):
                continue
            keep.add(i)
            last_kept = rel_str
        return [pairs[i] for i in sorted(keep)]

    def get_relationship_distance_new(
        self,
        db,
        orig_person,
        other_person,
        all_families=False,
        all_dist=False,
        only_birth=True,
    ):
        """
        Return if all_dist == True a 'tuple, string':
        (rank, person handle, firstRel_str, firstRel_fam,
        secondRel_str, secondRel_fam), msg
        or if all_dist == True a 'list of tuple, string':
        [.....], msg:

        .. note:: _new can be removed once all rel_xx modules no longer
                  overwrite get_relationship_distance

        The tuple or list of tuples consists of:

        ==============  =====================================================
        Element         Description
        ==============  =====================================================
        rank            Total number of generations from common ancestor to
                        the two persons, rank is -1 if no relations found
        person_handle   The Common ancestor
        firstRel_str    String with the path to the common ancestor
                        from orig Person
        firstRel_fam    Family numbers along the path as a list, eg [0,0,1].
                        For parent in multiple families, eg [0. [0, 2], 1]
        secondRel_str   String with the path to the common ancestor
                        from otherPerson
        secondRel_fam   Family numbers along the path, eg [0,0,1].
                        For parent in multiple families, eg [0. [0, 2], 1]
        msg             List of messages indicating errors. Empyt list if no
                        errors.
        ==============  =====================================================

        Example:  firstRel_str = 'ffm' and firstRel_fam = [2,0,1] means
        common ancestor is mother of the second family of the father of the
        first family of the father of the third family.

        Note that the same person might be present twice if the person is
        reached via a different branch too. Path (firstRel_str and
        secondRel_str) will of course be different.

        :param db: database to work on
        :param orig_person: first person
        :type orig_person: Person Obj
        :param other_person: second person, relation is sought between
                             first and second person
        :type other_person:  Person Obj
        :param all_families: if False only Main family is searched, otherwise
                             all families are used
        :type all_families: bool
        :param all_dist: if False only the shortest distance is returned,
                         otherwise all relationships
        :type all_dist:  bool
        :param only_birth: if True only parents with birth relation are
                           considered
        :type only_birth:  bool
        """
        # data storage to communicate with recursive functions
        self.__max_depth_reached = False
        self.__loop_detected = False
        self.__max_depth = self.get_depth()
        self.__all_families = all_families
        self.__all_dist = all_dist
        self.__only_birth = only_birth
        self.__crosslinks = False  # no crosslinks

        first_rel = -1
        second_rel = -1
        self.__msg = []

        common = []
        first_map = {}
        second_map = {}
        rank = 9999999

        try:
            if (
                self.storemap
                and self.stored_map is not None
                and self.map_handle == orig_person.handle
                and not self.dirtymap
            ):
                first_map = self.stored_map
                (
                    self.__max_depth_reached,
                    self.__loop_detected,
                    self.__all_families,
                    self.__all_dist,
                    self.__only_birth,
                    self.__crosslinks,
                    self.__msg,
                ) = self.map_meta
                self.__msg = list(self.__msg)
            else:
                self.__apply_filter(db, orig_person, "", [], first_map)
                self.map_meta = (
                    self.__max_depth_reached,
                    self.__loop_detected,
                    self.__all_families,
                    self.__all_dist,
                    self.__only_birth,
                    self.__crosslinks,
                    list(self.__msg),
                )
            self.__apply_filter(
                db, other_person, "", [], second_map, stoprecursemap=first_map
            )
        except RuntimeError:
            return (-1, None, -1, [], -1, []), [
                _("Relationship loop detected")
            ] + self.__msg

        if self.storemap:
            self.stored_map = first_map
            self.dirtymap = False
            self.map_handle = orig_person.handle

        # Build `common` as the minimal (non-dominated) set of paths to
        # every common ancestor -- the same "drop a path that's a
        # same-or-nearer path's extension on both sides" rule the
        # original code applied via a linear scan/insert/delete against
        # the whole `common` list built so far for every single
        # candidate (O(candidates x final size), and observed to make a
        # single relationship() call intractable on a real
        # 100,000-person tree under heavy pedigree collapse -- 696,320
        # candidate path pairs for one shared ancestor alone). Every
        # `rel_str` here is bounded by `self.__max_depth` generations
        # (the same cap that already bounds recursion elsewhere in this
        # class), so indexing by exact-prefix-string keeps each
        # candidate's domination check to at most `self.__max_depth`
        # lookups instead of a scan of everything found so far.
        #
        # `exact_rel1`: rel1-string -> list of candidate records sharing
        #   that exact rel1 (a `rel1` string deterministically identifies
        #   both the ancestor handle and the route to it, so two records
        #   sharing an exact rel1 differ only in their rel2 pairing).
        # `prefix_to_rel1`: rel1-string P -> set of exact rel1-strings
        #   that have P as a prefix -- the reverse index needed to find
        #   already-kept, farther records a new, nearer-or-equal record
        #   makes redundant.
        exact_rel1 = {}
        prefix_to_rel1 = {}
        seq = 0
        alive_count = 0
        cap = self.get_max_common_results()
        # Process common ancestors nearest-first, and stop once `cap`
        # non-dominated paths have been kept -- gramps-core's own
        # `all_dist=True` contract promises literally every distinct
        # non-dominated path, but a heavily pedigree-collapsed tree can
        # have combinatorially many of those to a single shared ancestor
        # (measured: 122,880 non-dominated paths for one pair on a real
        # 100,000-person tree), and every one of them costs real work to
        # check. Capped, nearest-first, this is a deliberate, documented
        # behavior change (see `set_max_common_results`) -- not a change
        # to the earlier `__apply_filter` fix's byte-identical guarantee,
        # which this cap sits downstream of.
        handles_by_min_rank = sorted(
            (h for h in second_map if h in first_map),
            key=lambda h: min(len(s) for s in first_map[h][0])
            + min(len(s) for s in second_map[h][0]),
        )
        capped = False
        for person_handle in handles_by_min_rank:
            if capped:
                break
            first_pairs = self._prefix_minimal(
                list(zip(first_map[person_handle][0], first_map[person_handle][1]))
            )
            second_pairs = self._prefix_minimal(
                list(zip(second_map[person_handle][0], second_map[person_handle][1]))
            )
            for rel1, fam1 in first_pairs:
                if capped:
                    break
                for rel2, fam2 in second_pairs:
                    rank = len(rel1) + len(rel2)
                    dominated = False
                    for cut in range(len(rel1) + 1):
                        for rec in exact_rel1.get(rel1[:cut], ()):
                            if not rec["alive"]:
                                continue
                            other_rel2 = rec["rel2"]
                            if (
                                rec["rank"] <= rank
                                and other_rel2 == rel2[: len(other_rel2)]
                            ):
                                dominated = True
                                break
                        if dominated:
                            break
                    if dominated:
                        continue
                    rec = {
                        "alive": True,
                        "rank": rank,
                        "handle": person_handle,
                        "rel1": rel1,
                        "fam1": fam1,
                        "rel2": rel2,
                        "fam2": fam2,
                        "seq": seq,
                    }
                    seq += 1
                    exact_rel1.setdefault(rel1, []).append(rec)
                    for cut in range(len(rel1) + 1):
                        prefix_to_rel1.setdefault(rel1[:cut], set()).add(rel1)
                    # this new (nearer-or-equal) record may make an
                    # already-kept, farther record redundant -- mirrors
                    # the original's own "superset deletion" step
                    for other_exact in prefix_to_rel1.get(rel1, ()):
                        for other in exact_rel1.get(other_exact, ()):
                            if (
                                other is not rec
                                and other["alive"]
                                and other["rank"] >= rank
                                and rel2 == other["rel2"][: len(rel2)]
                            ):
                                other["alive"] = False
                                alive_count -= 1
                    alive_count += 1
                    if cap is not None and alive_count >= cap:
                        capped = True
                        break
        all_records = [r for recs in exact_rel1.values() for r in recs if r["alive"]]
        # rank ascending, ties broken by generation order -- reconstructs
        # the exact ordering the original's insertion-sort produced
        all_records.sort(key=lambda r: (r["rank"], r["seq"]))
        common = [
            (r["rank"], r["handle"], r["rel1"], r["fam1"], r["rel2"], r["fam2"])
            for r in all_records
        ]
        # check for extra messages
        if self.__max_depth_reached:
            self.__msg += [
                _(
                    "Family Tree reaches back more than the maximum "
                    "%d generations searched.\nIt is possible that "
                    "relationships have been missed"
                )
                % (self.__max_depth)
            ]

        if common and not self.__all_dist:
            rank = common[0][0]
            person_handle = common[0][1]
            first_rel = common[0][2]
            first_fam = common[0][3]
            second_rel = common[0][4]
            second_fam = common[0][5]
            return (
                rank,
                person_handle,
                first_rel,
                first_fam,
                second_rel,
                second_fam,
            ), self.__msg
        if common:
            # list with tuples (rank, handle person,rel_str_orig,rel_fam_orig,
            #       rel_str_other,rel_fam_str) and messages
            return common, self.__msg
        if not self.__all_dist:
            return (-1, None, "", [], "", []), self.__msg
        else:
            return [(-1, None, "", [], "", [])], self.__msg

    def _pmap_append_checked(self, memo, pmap, handle, rel_str, rel_fam, person):
        """Append `rel_str`/`rel_fam` to `pmap[handle]` (already known to
        be present -- a crosslink) and run the same loop-detection check
        `__apply_filter` always ran inline: a genuine cycle in the data
        shows up as one recorded path to `handle` being a strict prefix
        of another. The original re-scanned `pmap[handle][0]` in full on
        every single append to check this, making one handle's own
        accumulation O(n^3) in the number of distinct paths that reach
        it -- independent of, and left exposed by, the exponential-
        recursion fix elsewhere in this method (observed: ~2s for one
        handle accumulating ~500 paths on a real 100,000-person tree).
        This does the same check via a per-handle prefix index bounded
        by generation depth instead.

        Only checks the new entry against previously-seen ones for this
        handle, not all pairs -- sufficient, because the original
        `return`s the instant a loop is found, so by the time a new
        entry is being added, no loop can exist among the entries
        already there (else this call would have already stopped).

        Returns True if a loop was detected (caller should stop, as the
        original does via its own `return`).
        """
        idx = memo["pmap_loop_index"].setdefault(handle, {"exact": set(), "prefix": {}})
        exact, prefix = idx["exact"], idx["prefix"]
        loop = False
        shorter_existing = None
        for cut in range(len(rel_str)):
            if rel_str[:cut] in exact:
                loop = True
                shorter_existing = rel_str[:cut]
                break
        longer_existing = None
        if not loop:
            for other in prefix.get(rel_str, ()):
                if len(other) > len(rel_str):
                    loop = True
                    longer_existing = other
                    break
        pmap[handle][0] += [rel_str]
        pmap[handle][1] += [rel_fam]
        if loop:
            self.__loop_detected = True
            relation = (
                rel_str[len(shorter_existing) :]
                if shorter_existing is not None
                else longer_existing[len(rel_str) :]
            )
            self.__msg += [
                _("Relationship loop detected:")
                + " "
                + _("Person %(person)s connects to himself via %(relation)s")
                % {
                    "person": person.get_primary_name().get_name(),
                    "relation": relation,
                }
            ]
        exact.add(rel_str)
        for cut in range(len(rel_str) + 1):
            prefix.setdefault(rel_str[:cut], set()).add(rel_str)
        return loop

    def __apply_filter(
        self,
        db,
        person,
        rel_str,
        rel_fam,
        pmap,
        depth=1,
        stoprecursemap=None,
        memo=None,
    ):
        """
        Typically this method is called recursively in two ways:
        First method is stoprecursemap= None
        In this case a recursemap is builded by storing all data.

        Second method is with a stoprecursemap given
        In this case parents are recursively looked up. If present in
        stoprecursemap, a common ancestor is found, and the method can
        stop looking further. If however self.__crosslinks == True, the data
        of first contains loops, and parents
        will be looked up anyway an stored if common. At end the doubles
        are filtered out

        `memo` is per-outermost-call state: a person's set of reachable
        ancestors (and any siblings injected along the way -- see the
        "family without parents" case below) is memoized the first time
        it is fully derived from the database, and replayed from memory
        on a later revisit within the same outermost call instead of
        being re-derived. Without this, a person reached a second time
        via a different branch (pedigree collapse, or simply a large
        tree) triggers a full second walk of everything above them,
        which is what makes this method exponential in the number of
        such revisits. Callers never pass `memo` explicitly; it is
        created fresh on the outermost call and threaded through the
        recursion below.
        """
        if memo is None:
            memo = {"closure": {}, "open": [], "pmap_loop_index": {}}

        if person is None or not person.handle:
            return

        if depth > self.__max_depth:
            self.__max_depth_reached = True
            # print('Maximum ancestor generations ('+str(depth)+') reached', \
            #            '(' + rel_str + ').',\
            #            'Stopping relation algorithm.')
            return
        depth += 1

        commonancestor = False
        store = True  # normally we store all parents
        if stoprecursemap:
            store = False  # but not if a stop map given
            if person.handle in stoprecursemap:
                commonancestor = True
                store = True

        # add person to the map, take into account that person can be obtained
        # from different sides
        if person.handle in pmap:
            # person is already a grandparent in another branch, we already have
            # had lookup of all parents, we call that a crosslink
            if not stoprecursemap:
                self.__crosslinks = True
            if self._pmap_append_checked(
                memo, pmap, person.handle, rel_str, rel_fam, person
            ):
                return
        elif store:
            pmap[person.handle] = [[rel_str], [rel_fam]]

        # record this visit against every ancestor-closure currently being
        # assembled further up the call stack (see `memo` above), so it
        # can be replayed later without touching the database again
        for rec in memo["open"]:
            rec["deltas"].append(
                ("v", rel_str[rec["base_str"] :], rel_fam[rec["base_fam"] :], person)
            )

        # having added person to the pmap, we only look up recursively to
        # parents if this person is not common relative
        # if however the first map has crosslinks, we need to continue reduced
        if commonancestor and not self.__crosslinks:
            # don't continue search, great speedup!
            return

        family_handles = []
        main = person.get_main_parents_family_handle()
        if main:
            family_handles = [main]
        if self.__all_families:
            family_handles = person.get_parent_family_handle_list()

        # Memoization only covers the (overwhelmingly common) case of a
        # person with at most one parent family -- with more than one,
        # `rel_fam` entries can merge into nested per-family-index lists
        # (see the `parentstodo` update below), which a cached, replayed
        # closure would need to reproduce exactly; simpler and safer to
        # just not memoize that rarer case and let it re-derive from the
        # database every time it's revisited, same as before this change.
        only_one_family = len(family_handles) <= 1
        # A 1-hop child of this node is called with this (already-
        # incremented) `depth` and is itself accepted iff `depth <=
        # max_depth`; an L-hop descendant is accepted iff `depth + L - 1
        # <= max_depth`. So the longest reachable suffix from here is
        # `max_depth - depth + 1`, not `max_depth - depth`.
        budget_needed = self.__max_depth - depth + 1
        if only_one_family:
            cached = memo["closure"].get(person.handle)
            if cached is not None and cached["budget"] >= budget_needed:
                # REPLAY: `cached["entries"]` is already the *complete*,
                # flattened set of everything reachable from this handle
                # (built once, the first time it was fully expanded) --
                # so each entry is applied directly here (the same
                # pmap-add-or-crosslink-append/loop-detection bookkeeping
                # the top of this method does for a freshly-visited
                # person) and NOT by recursing back into __apply_filter,
                # which would re-expand descendants that are already
                # separately present as their own entries in this same
                # closure.
                for kind, suffix_str, suffix_fam, target in cached["entries"]:
                    if len(suffix_str) > budget_needed:
                        continue
                    full_str = rel_str + suffix_str
                    full_fam = rel_fam + suffix_fam
                    if kind == "v":
                        target_handle = target.handle
                        store = True
                        if stoprecursemap:
                            store = target_handle in stoprecursemap
                        if target_handle in pmap:
                            if not stoprecursemap:
                                self.__crosslinks = True
                            if self._pmap_append_checked(
                                memo, pmap, target_handle, full_str, full_fam, target
                            ):
                                return
                        elif store:
                            pmap[target_handle] = [[full_str], [full_fam]]
                        for rec in memo["open"]:
                            rec["deltas"].append(
                                (
                                    "v",
                                    full_str[rec["base_str"] :],
                                    full_fam[rec["base_fam"] :],
                                    target,
                                )
                            )
                    else:  # "s": a sibling injected via the no-recorded-
                        # parents case below, a direct pmap write in the
                        # original (never recursed into, and never gated
                        # by `store`/`stoprecursemap`), replayed the same
                        # unconditional way here
                        if target in pmap:
                            pmap[target][0] += [full_str]
                            pmap[target][1] += [full_fam]
                        else:
                            pmap[target] = [[full_str], [full_fam]]
                        for rec in memo["open"]:
                            rec["deltas"].append(
                                (
                                    "s",
                                    full_str[rec["base_str"] :],
                                    full_fam[rec["base_fam"] :],
                                    target,
                                )
                            )
                return

        recorder = None
        if only_one_family:
            recorder = {
                "base_str": len(rel_str),
                "base_fam": len(rel_fam),
                "deltas": [],
            }
            memo["open"].append(recorder)

        try:
            parentstodo = {}
            fam = 0
            for family_handle in family_handles:
                rel_fam_new = rel_fam + [fam]
                family = db.get_family_from_handle(family_handle)
                if not family:
                    continue
                # obtain childref for this person
                childrel = [
                    (ref.get_mother_relation(), ref.get_father_relation())
                    for ref in family.get_child_ref_list()
                    if ref.ref == person.handle
                ]
                # Add this check
                if not childrel:
                    continue  # Skip to the next family if childrel is empty
                fhandle = family.father_handle
                mhandle = family.mother_handle
                for data in [
                    (
                        fhandle,
                        self.REL_FATHER,
                        self.REL_FATHER_NOTBIRTH,
                        childrel[0][1],
                    ),
                    (
                        mhandle,
                        self.REL_MOTHER,
                        self.REL_MOTHER_NOTBIRTH,
                        childrel[0][0],
                    ),
                ]:
                    if data[0] and data[0] not in parentstodo:
                        persontodo = db.get_person_from_handle(data[0])
                        if data[3] == ChildRefType.BIRTH:
                            addstr = data[1]
                        elif not self.__only_birth:
                            addstr = data[2]
                        else:
                            addstr = ""
                        if addstr:
                            parentstodo[data[0]] = (
                                persontodo,
                                rel_str + addstr,
                                rel_fam_new,
                            )
                    elif data[0] and data[0] in parentstodo:
                        # this person is already scheduled to research
                        # update family list
                        famlist = parentstodo[data[0]][2]
                        if not isinstance(famlist[-1], list) and fam != famlist[-1]:
                            famlist = famlist[:-1] + [[famlist[-1]]]
                        if isinstance(famlist[-1], list) and fam not in famlist[-1]:
                            famlist = famlist[:-1] + [famlist[-1] + [fam]]
                            parentstodo[data[0]] = (
                                parentstodo[data[0]][0],
                                parentstodo[data[0]][1],
                                famlist,
                            )
                if not fhandle and not mhandle and stoprecursemap is None:
                    # family without parents, add brothers for orig person
                    # other person has recusemap, and will stop when seeing
                    # the brother.
                    child_list = [
                        ref.ref
                        for ref in family.get_child_ref_list()
                        if ref.ref != person.handle
                    ]
                    addstr = self.REL_SIBLING
                    for chandle in child_list:
                        if chandle in pmap:
                            pmap[chandle][0] += [rel_str + addstr]
                            pmap[chandle][1] += [rel_fam_new]
                            # person is already a grandparent in another branch
                        else:
                            pmap[chandle] = [[rel_str + addstr], [rel_fam_new]]
                        for rec in memo["open"]:
                            rec["deltas"].append(
                                (
                                    "s",
                                    (rel_str + addstr)[rec["base_str"] :],
                                    rel_fam_new[rec["base_fam"] :],
                                    chandle,
                                )
                            )
                fam += 1

            for handle, data in parentstodo.items():
                self.__apply_filter(
                    db, data[0], data[1], data[2], pmap, depth, stoprecursemap, memo
                )
        except:
            import traceback

            traceback.print_exc()
            if recorder is not None:
                memo["open"].pop()
            return
        else:
            if recorder is not None:
                memo["open"].pop()
                memo["closure"][person.handle] = {
                    "budget": budget_needed,
                    "entries": recorder["deltas"],
                }


_PATCHED_ATTRIBUTES = [
    "max_common_results",
    "set_max_common_results",
    "get_max_common_results",
    "_prefix_minimal",
    "get_relationship_distance_new",
    "_pmap_append_checked",
    "_RelationshipCalculator__apply_filter",
]


def apply_patch() -> None:
    """Patch Gramps' RelationshipCalculator, unless it already has the fix."""
    target = relationship.RelationshipCalculator
    if hasattr(target, "set_max_common_results"):
        return
    for name in _PATCHED_ATTRIBUTES:
        setattr(target, name, RelationshipCalculator.__dict__[name])
