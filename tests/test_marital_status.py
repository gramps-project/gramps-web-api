#
# Gramps Web API - A RESTful API for the Gramps genealogy program
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

"""Pure-core unit tests for ``compute_marital_status``.

Gramps is NOT imported here — these tests run in any plain Python environment.

Representative constants (do NOT hard-code real Gramps values in assertions;
pass them explicitly so the test is agnostic about the actual integer).
"""

from gramps_webapi.api.resources.marital_status import compute_marital_status

# Representative FamilyRelType constants, passed explicitly to the function.
# These match the real Gramps values (MARRIED=0, UNMARRIED=1, CIVIL_UNION=2)
# but the tests never rely on that fact — they always pass the constants.
REL_MARRIED = 0
REL_UNMARRIED = 1
REL_CIVIL_UNION = 2
REL_UNKNOWN = 3  # Some "other" int — not any of the three recognised types


def call(
    marriage_sortvals=None,
    divorce_sortvals=None,
    rel_type=REL_MARRIED,
    father_has_death=False,
    mother_has_death=False,
):
    """Helper with sane defaults for brevity in test bodies."""
    return compute_marital_status(
        marriage_sortvals=marriage_sortvals or [],
        divorce_sortvals=divorce_sortvals or [],
        rel_type=rel_type,
        rel_type_married=REL_MARRIED,
        rel_type_unmarried=REL_UNMARRIED,
        rel_type_civil_union=REL_CIVIL_UNION,
        father_has_death=father_has_death,
        mother_has_death=mother_has_death,
    )


# ---------------------------------------------------------------------------
# Simple married — rel=MARRIED, no events
# ---------------------------------------------------------------------------


def test_married_by_rel_type_no_events():
    """rel=MARRIED with no events → 'married'."""
    assert call(rel_type=REL_MARRIED) == "married"


# ---------------------------------------------------------------------------
# Married via event only — rel type is not MARRIED
# ---------------------------------------------------------------------------


def test_married_via_event_unknown_rel():
    """A marriage event present with a non-MARRIED rel type → 'married'."""
    assert call(marriage_sortvals=[20010101], rel_type=REL_UNKNOWN) == "married"


# ---------------------------------------------------------------------------
# Divorced — marriage then later divorce
# ---------------------------------------------------------------------------


def test_divorced_later_divorce():
    """divorce sortval > marriage sortval → 'divorced'."""
    assert call(marriage_sortvals=[20010101], divorce_sortvals=[20101201]) == "divorced"


def test_divorced_same_sortval():
    """divorce sortval == marriage sortval (edge case) → 'divorced'
    (>= comparison, so equal counts as divorce winning)."""
    assert call(marriage_sortvals=[20010101], divorce_sortvals=[20010101]) == "divorced"


# ---------------------------------------------------------------------------
# Marriage → divorce → remarriage: remarriage date later than divorce
# ---------------------------------------------------------------------------


def test_remarriage_after_divorce_stays_married():
    """m→d→m where remarriage sortval > divorce sortval → 'married'."""
    # divorce=2010, remarriage=2015 → max(marriage)=2015 > max(divorce)=2010
    assert (
        call(marriage_sortvals=[20010101, 20150601], divorce_sortvals=[20101201])
        == "married"
    )


def test_remarriage_after_divorce_remarriage_earlier_stays_divorced():
    """m→d→m where remarriage sortval < divorce sortval → 'divorced'.

    This is an unusual / data-entry-error case but the algorithm handles it
    consistently: the latest event wins.
    """
    assert (
        call(marriage_sortvals=[20010101, 20081201], divorce_sortvals=[20101201])
        == "divorced"
    )


# ---------------------------------------------------------------------------
# Widowed — married + a spouse has a death
# ---------------------------------------------------------------------------


def test_widowed_father_death():
    """married + father death → 'widowed'."""
    assert call(rel_type=REL_MARRIED, father_has_death=True) == "widowed"


def test_widowed_mother_death():
    """married + mother death → 'widowed'."""
    assert call(rel_type=REL_MARRIED, mother_has_death=True) == "widowed"


def test_widowed_both_spouses_dead():
    """married + both spouses dead → 'widowed'."""
    assert (
        call(rel_type=REL_MARRIED, father_has_death=True, mother_has_death=True)
        == "widowed"
    )


def test_widowed_via_marriage_event_not_rel_type():
    """married-via-event (not rel type) + death → 'widowed'."""
    assert (
        call(
            marriage_sortvals=[20010101],
            rel_type=REL_UNKNOWN,
            father_has_death=True,
        )
        == "widowed"
    )


# ---------------------------------------------------------------------------
# Partners — rel=UNMARRIED or rel=CIVIL_UNION
# ---------------------------------------------------------------------------


def test_partners_unmarried():
    """rel=UNMARRIED → 'partners'."""
    assert call(rel_type=REL_UNMARRIED) == "partners"


def test_partners_civil_union():
    """rel=CIVIL_UNION → 'partners'."""
    assert call(rel_type=REL_CIVIL_UNION) == "partners"


# ---------------------------------------------------------------------------
# Partners NOT widowed even if a spouse has died
# ---------------------------------------------------------------------------


def test_partners_not_widowed_despite_death():
    """'partners' is NOT upgraded to 'widowed' even when a spouse died."""
    assert call(rel_type=REL_UNMARRIED, father_has_death=True) == "partners"


def test_partners_civil_union_not_widowed():
    """Civil union with a death → still 'partners', not 'widowed'."""
    assert call(rel_type=REL_CIVIL_UNION, mother_has_death=True) == "partners"


# ---------------------------------------------------------------------------
# Unknown — rel is some-other-int, no events
# ---------------------------------------------------------------------------


def test_unknown_no_events_other_rel():
    """rel is some unrecognised integer, no marriage events → 'unknown'."""
    assert call(rel_type=REL_UNKNOWN) == "unknown"


# ---------------------------------------------------------------------------
# Fully undated divorce (all sortvals == 0)
# ---------------------------------------------------------------------------


def test_fully_undated_divorce_yields_divorced():
    """All events undated (sortval=0): 0 >= 0 → divorce wins → 'divorced'.

    Known limitation: an undated m→d→m scenario also yields 'divorced'
    because the algorithm cannot distinguish event order without dates.
    This matches the rest of Gramps Web's handling of undated events.
    """
    assert call(marriage_sortvals=[0], divorce_sortvals=[0]) == "divorced"


def test_fully_undated_divorce_no_marriage_events():
    """Divorce event present (undated), no marriage events → 'divorced'."""
    assert call(divorce_sortvals=[0], rel_type=REL_MARRIED) == "divorced"


# ---------------------------------------------------------------------------
# Divorce-only (no marriage event), rel=MARRIED
# ---------------------------------------------------------------------------


def test_divorced_no_marriage_event_rel_married():
    """Divorce event with a date, no marriage event, rel=MARRIED → 'divorced'.

    max(divorce) >= max(marriage) is trivially True when marriage list is empty.
    """
    assert call(divorce_sortvals=[20100601], rel_type=REL_MARRIED) == "divorced"


# ---------------------------------------------------------------------------
# Divorced does NOT trigger widowhood
# ---------------------------------------------------------------------------


def test_divorced_with_death_stays_divorced():
    """After divorce, a spouse death does NOT change status to 'widowed'."""
    assert (
        call(
            marriage_sortvals=[20010101],
            divorce_sortvals=[20101201],
            father_has_death=True,
        )
        == "divorced"
    )


# ---------------------------------------------------------------------------
# Partners with divorce event AND spouse death → still "partners"
# ---------------------------------------------------------------------------


def test_partners_with_divorce_and_death_stays_partners():
    """rel=UNMARRIED + divorce event + spouse death → still 'partners'.

    Confirms that both the divorce-to-'divorced' path and the
    death-to-'widowed' path leave 'partners' untouched: partners is never
    upgraded to 'divorced' or 'widowed' regardless of events or deaths.
    """
    assert (
        call(
            divorce_sortvals=[20101201],
            rel_type=REL_UNMARRIED,
            father_has_death=True,
        )
        == "partners"
    )
