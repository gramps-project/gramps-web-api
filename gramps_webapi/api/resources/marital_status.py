#
# Gramps Web API - marital status derivation
#
# Copyright (C) 2026  Sergey Sabalevskiy
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Marital-status derivation for Gramps Web API family profiles.

Two-layer design:

* ``compute_marital_status`` — pure core, zero Gramps imports.  Holds ALL
  decision logic and is unit-testable without a Gramps installation.

* ``get_marital_status`` — thin adapter that extracts primitives from Gramps
  objects and calls the core.  This is the only part that imports Gramps.

The result is one of: ``"married"``, ``"divorced"``, ``"widowed"``,
``"partners"``, ``"unknown"``.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Pure core — NO Gramps imports below this line
# ---------------------------------------------------------------------------


def compute_marital_status(
    marriage_sortvals: list[int],
    divorce_sortvals: list[int],
    rel_type: int,
    rel_type_married: int,
    rel_type_unmarried: int,
    rel_type_civil_union: int,
    father_has_death: bool,
    mother_has_death: bool,
) -> str:
    """Derive marital status from pre-extracted primitives.

    Parameters
    ----------
    marriage_sortvals:
        Sort-values (``date.get_sort_value()``) of all marriage-class events
        (MARRIAGE + fallbacks such as ENGAGEMENT / MARR_ALT) found on the
        family.  May be empty.  0 means undated.
    divorce_sortvals:
        Sort-values of all divorce-class events (DIVORCE, ANNULMENT,
        DIV_FILING, and other fallbacks).  May be empty.  0 means undated.
    rel_type:
        Integer value of the family's ``FamilyRelType``.
    rel_type_married:
        The integer value of ``FamilyRelType.MARRIED``.
    rel_type_unmarried:
        The integer value of ``FamilyRelType.UNMARRIED``.
    rel_type_civil_union:
        The integer value of ``FamilyRelType.CIVIL_UNION``.
    father_has_death:
        True when the father's profile (or DB fallback) records a death event
        with a known date.
    mother_has_death:
        Same for the mother.

    Returns
    -------
    str
        One of ``"married"``, ``"divorced"``, ``"widowed"``,
        ``"partners"``, ``"unknown"``.

    Algorithm
    ---------
    1. Base by relationship type:
       - UNMARRIED or CIVIL_UNION  → ``"partners"``
       - MARRIED *or* any marriage event present → ``"married"``
       - otherwise → ``"unknown"``

    2. Divorce wins if it is the latest terminal event by sort-value:
       if any divorce event exists AND (no marriage events OR
       ``max(divorce) >= max(marriage)``) → status = ``"divorced"``.
       This keeps m→d→m correctly as ``"married"`` when the remarriage
       sort-value is strictly later than the divorce.

       Known limitation: when ALL events are undated (sort-value == 0),
       ``max(divorce) >= max(marriage)`` is ``0 >= 0`` = True, so a
       fully-undated m→d→m sequence also yields ``"divorced"`` rather than
       ``"married"``.  This matches the rest of Gramps Web's behaviour for
       undated events.

    3. Widowhood applies ONLY to ``"married"`` (not to ``"partners"``):
       if status == ``"married"`` and either spouse has a recorded death
       with a date → status = ``"widowed"``.
    """
    # Step 1 — base status from relationship type and event presence
    if rel_type in (rel_type_unmarried, rel_type_civil_union):
        base = "partners"
    elif marriage_sortvals or rel_type == rel_type_married:
        base = "married"
    else:
        base = "unknown"

    # Step 2 — divorce wins if it is the latest terminal event.
    # Only applies to "married" / "unknown" base; "partners" is never
    # converted to "divorced" (a dissolved civil union stays "partners").
    if (
        base != "partners"
        and divorce_sortvals
        and (not marriage_sortvals or max(divorce_sortvals) >= max(marriage_sortvals))
    ):
        status = "divorced"
    else:
        status = base

    # Step 3 — widowhood, but ONLY for "married" (never "partners")
    if status == "married" and (father_has_death or mother_has_death):
        status = "widowed"

    return status


# ---------------------------------------------------------------------------
# Gramps adapter — imports Gramps here and nowhere above
# ---------------------------------------------------------------------------


def get_marital_status(
    db_handle: Any,
    family: Any,
    father_profile: dict | None,
    mother_profile: dict | None,
) -> str:
    """Return a marital-status string for *family*.

    Parameters
    ----------
    db_handle:
        Gramps database handle (read-only access suffices).
    family:
        A ``gramps.gen.lib.Family`` object.
    father_profile:
        The already-computed person profile dict for the father (may be empty
        dict or None if the father is unknown).  Used to detect death without
        an extra DB round-trip when the ``"death"`` key is present.
    mother_profile:
        Same for the mother.

    Notes
    -----
    The death-detection logic uses a two-tier approach:

    * If the profile dict contains a ``"death"`` key (even if its value is
      empty / ``{}``), that key is authoritative: a non-empty dict with a
      ``"date"`` sub-key means "has dated death", an empty dict or missing
      ``"date"`` means "no dated death recorded".

    * If the profile dict does NOT contain a ``"death"`` key at all (e.g.
      the caller passed ``args=[]`` so death was not included), we fall back
      to a direct DB look-up via ``get_death_or_fallback``.
    """
    # Local Gramps imports — isolated to this function/module section so that
    # compute_marital_status remains provably Gramps-free.
    from gramps.gen.errors import HandleError
    from gramps.gen.lib import EventType, FamilyRelType
    from gramps.gen.utils.db import PRIMARY_EVENT_ROLES, get_death_or_fallback

    # --- Collect event sort-values -------------------------------------------
    marriage_sortvals: list[int] = []
    divorce_sortvals: list[int] = []

    for event_ref in family.get_event_ref_list():
        if event_ref.get_role() not in PRIMARY_EVENT_ROLES:
            continue
        event = db_handle.get_event_from_handle(event_ref.ref)
        if event is None:
            continue
        etype = event.get_type()
        sortval = event.get_date_object().get_sort_value()

        if etype == EventType.MARRIAGE or etype.is_marriage_fallback():
            marriage_sortvals.append(sortval)
        elif etype == EventType.DIVORCE or etype.is_divorce_fallback():
            divorce_sortvals.append(sortval)

    # --- Relationship type ---------------------------------------------------
    # NB: Gramps ``Family`` exposes the relationship type via ``get_relationship()``
    # (there is no ``get_type()`` on Family — that exists on Event). The returned
    # FamilyRelType is int-coercible via GrampsType.__int__.
    rel_type = int(family.get_relationship())

    # --- Death flags ---------------------------------------------------------
    def _has_dated_death(profile: dict | None, handle: Any) -> bool:
        """True if the person has a recorded death with a known date.

        Two-tier contract:
        * Tier 1 — profile is not None AND contains a ``"death"`` key:
          the key is authoritative.  A sub-dict with a ``"date"`` entry
          means "has dated death"; an empty dict or absent ``"date"``
          means "no dated death recorded".  No DB look-up is performed.
        * Tier 2 — profile is None, OR the ``"death"`` key is absent
          (i.e. caller passed ``args=[]`` so death was not serialised):
          fall back to a direct DB look-up via ``get_death_or_fallback``.

        Note: an empty profile dict ``{}`` has no ``"death"`` key, so it
        falls through to Tier 2 — same as None.
        """
        if profile is not None and "death" in profile:
            # Tier 1: profile is authoritative.
            death = profile["death"]
            return bool(death and death.get("date"))
        # Tier 2: profile absent or built without death info — ask the DB.
        if handle is None:
            return False
        try:
            person = db_handle.get_person_from_handle(handle)
        except HandleError:
            return False
        if person is None:
            return False
        event = get_death_or_fallback(db_handle, person)
        if event is None:
            return False
        # Match the Tier 1 convention: an undated death (sort-value 0) does not
        # count, so both tiers agree regardless of which one a caller hits.
        return event.get_date_object().get_sort_value() != 0

    father_has_death = _has_dated_death(father_profile, family.get_father_handle())
    mother_has_death = _has_dated_death(mother_profile, family.get_mother_handle())

    return compute_marital_status(
        marriage_sortvals=marriage_sortvals,
        divorce_sortvals=divorce_sortvals,
        rel_type=rel_type,
        rel_type_married=int(FamilyRelType.MARRIED),
        rel_type_unmarried=int(FamilyRelType.UNMARRIED),
        rel_type_civil_union=int(FamilyRelType.CIVIL_UNION),
        father_has_death=father_has_death,
        mother_has_death=mother_has_death,
    )
