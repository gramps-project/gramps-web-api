#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2011       Paul Franklin
# Copyright (C) 2023       Oliver Lehmann
# Copyright (C) 2026       David Straub
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

"""
Genealogical data verification library.

GUI-free port of the Gramps "Verify the Data" tool.  Suitable for use
from the Gramps Web API or as an upstream helper that runs against any
Gramps database handle.

Usage::

    from gramps_webapi.verify_lib import run_verify, DEFAULT_OPTIONS

    results = run_verify(db_handle)
    results = run_verify(db_handle, {"oldage": 100, "estimate_age": True})
"""

import statistics

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import (
    ChildRefType,
    EventRoleType,
    EventType,
    FamilyRelType,
    NameType,
    Person,
)
from gramps.gen.lib.date import Today

_ = glocale.translation.sgettext

# ---------------------------------------------------------------------------
# Options — mirrors Gramps VerifyOptions without the tool.ToolOptions dependency
# ---------------------------------------------------------------------------


class VerifyOptions:
    """Holds the configurable thresholds for the verification rules.

    Instantiate with keyword overrides; all unspecified keys fall back to the
    class-level defaults.  The ``as_dict`` method returns the merged dict that
    ``run_verify`` / ``VerifyRunner.run`` expect.
    """

    defaults = {
        "oldage": 90,
        "hwdif": 30,
        "cspace": 8,
        "cbspan": 25,
        "yngmar": 17,
        "oldmar": 50,
        "oldmom": 48,
        "yngmom": 17,
        "yngdad": 18,
        "olddad": 65,
        "wedder": 3,
        "mxchildmom": 12,
        "mxchilddad": 15,
        "lngwdw": 30,
        "oldunm": 99,
        "estimate_age": False,
        "invdate": True,
    }

    help = {
        "oldage":     "Maximum age at death (years)",
        "hwdif":      "Maximum husband-wife age difference (years)",
        "cspace":     "Maximum years between consecutive children",
        "cbspan":     "Maximum total span of children's births (years)",
        "yngmar":     "Minimum age to marry (years)",
        "oldmar":     "Maximum age to marry (years)",
        "oldmom":     "Maximum age for a mother to bear a child (years)",
        "yngmom":     "Minimum age for a mother to bear a child (years)",
        "yngdad":     "Minimum age for a father (years)",
        "olddad":     "Maximum age for a father (years)",
        "wedder":     "Maximum number of spouses",
        "mxchildmom": "Maximum number of children for a woman",
        "mxchilddad": "Maximum number of children for a man",
        "lngwdw":     "Maximum consecutive years of widowhood before next marriage",
        "oldunm":     "Maximum age for an unmarried person (years)",
        "estimate_age": "Estimate missing or inexact dates",
        "invdate":    "Flag invalid date formats",
    }

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self.defaults)
        if unknown:
            raise ValueError(f"Unknown verify option(s): {', '.join(sorted(unknown))}")
        self._opts = {**self.defaults, **overrides}

    def as_dict(self):
        """Return a plain dict suitable for passing to ``run_verify``."""
        return dict(self._opts)

    def __getitem__(self, key):
        return self._opts[key]

    def __repr__(self):
        overrides = {k: v for k, v in self._opts.items() if v != self.defaults[k]}
        return f"VerifyOptions({overrides!r})"


# Keep the bare dict for backwards compatibility and for use as schema defaults.
DEFAULT_OPTIONS = VerifyOptions.defaults

# ---------------------------------------------------------------------------
# Lightweight summary objects
# ---------------------------------------------------------------------------


class VerifyFamily:
    def __init__(self, db, family):
        self.handle = ""
        self.marr_date = 0
        self.divo_date = 0
        self.events_in_wrong_order = False
        self.events_of_type_unknown = False
        self.name = ""
        self.mother_handle = ""
        self.father_handle = ""
        self.gramps_id = ""
        self.child_ref_list = {}
        self.relationship = None

        if family is None:
            return

        self.handle = family.get_handle()
        self.mother_handle = family.get_mother_handle()
        self.father_handle = family.get_father_handle()
        self.gramps_id = family.get_gramps_id()
        self.child_ref_list = family.get_child_ref_list()
        self.relationship = family.get_relationship()

        try:
            from gramps.gen.utils.db import family_name
            self.name = family_name(family, db)
        except Exception:
            self.name = self.gramps_id

        prev_date = 0
        for event_ref in family.get_event_ref_list():
            event = db.get_event_from_handle(event_ref.ref)
            date_obj = event.get_date_object()
            if date_obj and date_obj.get_day() != 0 and date_obj.get_month() != 0:
                if prev_date > date_obj.get_sort_value() > 0:
                    self.events_in_wrong_order = True
                prev_date = date_obj.get_sort_value()

            if event_ref.get_role() == EventRoleType.UNKNOWN:
                self.events_of_type_unknown = True
                continue
            if event_ref.get_role() in (
                EventRoleType.FAMILY,
                EventRoleType.PRIMARY,
            ):
                etype = event.get_type()
                date_obj = event.get_date_object()
                if etype == EventType.MARRIAGE:
                    self.marr_date = date_obj.get_sort_value()
                elif etype == EventType.DIVORCE:
                    self.divo_date = date_obj.get_sort_value()

    def get_marriage_date(self):
        return self.marr_date

    def get_divorce_date(self):
        return self.divo_date

    def get_mother_handle(self):
        return self.mother_handle

    def get_father_handle(self):
        return self.father_handle

    def is_events_of_type_unknown(self):
        return self.events_of_type_unknown

    def is_events_in_wrong_order(self):
        return self.events_in_wrong_order

    def get_name(self):
        return self.name

    def get_child_ref_list(self):
        return self.child_ref_list

    def get_relationship(self):
        return self.relationship

    def get_handle(self):
        return self.handle


class VerifyPerson:
    def __init__(self, db, person):
        self.handle = ""
        self.birth_date = [0, 0]
        self.death_date = [0, 0]
        self.bapt_date = [0, 0]
        self.bury_date = [0, 0]
        self.death = False
        self.birth_date_invalid = False
        self.death_date_invalid = False
        self.events_of_type_unknown = False
        self.name = ""
        self.surname = ""
        self.name_type = NameType.UNKNOWN
        self.gramps_id = ""
        self.gender = Person.UNKNOWN
        self.family_handle_list = {}
        self.parent_family_handle_list = {}
        self.events_in_wrong_order = False

        if person is None:
            return

        self.handle = person.get_handle()
        self.name = person.get_primary_name().get_name()
        self.surname = person.get_primary_name().get_surname()
        self.gramps_id = person.get_gramps_id()
        self.gender = person.get_gender()
        self.family_handle_list = person.get_family_handle_list()
        self.parent_family_handle_list = person.get_parent_family_handle_list()
        self.death = bool(person.get_death_ref())
        self.name_type = person.get_primary_name().get_type()

        prev_date = 0
        for event_ref in person.get_event_ref_list():
            event = db.get_event_from_handle(event_ref.ref)
            date_obj = event.get_date_object()
            if date_obj and date_obj.get_day() != 0 and date_obj.get_month() != 0:
                if prev_date > date_obj.get_sort_value() > 0:
                    self.events_in_wrong_order = True
                prev_date = date_obj.get_sort_value()

            if event and event_ref.get_role() == EventRoleType.UNKNOWN:
                self.events_of_type_unknown = True
                continue
            if event and event_ref.get_role() == EventRoleType.PRIMARY:
                etype = event.get_type()
                date_obj = event.get_date_object()
                if date_obj:
                    if date_obj.get_day() == 0 or date_obj.get_month() == 0:
                        exact_date = 0
                    else:
                        exact_date = date_obj.get_sort_value()

                    if etype == EventType.BAPTISM or (
                        etype == EventType.CHRISTEN and self.bapt_date[1] == 0
                    ):
                        self.bapt_date[0] = exact_date
                        self.bapt_date[1] = date_obj.get_sort_value()
                    elif etype == EventType.BURIAL:
                        self.bury_date[0] = exact_date
                        self.bury_date[1] = date_obj.get_sort_value()
                    elif etype == EventType.BIRTH:
                        if not date_obj.get_valid():
                            self.birth_date_invalid = True
                        self.birth_date[0] = exact_date
                        self.birth_date[1] = date_obj.get_sort_value()
                    elif etype == EventType.DEATH:
                        if not date_obj.get_valid():
                            self.death_date_invalid = True
                        self.death_date[0] = exact_date
                        self.death_date[1] = date_obj.get_sort_value()

    def get_birth_date(self, estimate=False):
        return self.birth_date[int(estimate)]

    def get_death_date(self, estimate=False):
        return self.death_date[int(estimate)]

    def get_bapt_date(self, estimate=False):
        return self.bapt_date[int(estimate)]

    def get_bury_date(self, estimate=False):
        return self.bury_date[int(estimate)]

    def get_name(self):
        return self.name

    def get_surname(self):
        return self.surname

    def get_name_type(self):
        return self.name_type

    def get_family_handle_list(self):
        return self.family_handle_list

    def get_gender(self):
        return self.gender

    def get_parent_family_handle_list(self):
        return self.parent_family_handle_list

    def get_death(self):
        return self.death

    def is_birth_date_invalid(self):
        return self.birth_date_invalid

    def is_death_date_invalid(self):
        return self.death_date_invalid

    def is_events_of_type_unknown(self):
        return self.events_of_type_unknown

    def is_events_in_wrong_order(self):
        return self.events_in_wrong_order

    def get_gramps_id(self):
        return self.gramps_id

    def get_handle(self):
        return self.handle


# ---------------------------------------------------------------------------
# Runner — holds per-call caches; replaces the module-level LRU globals
# ---------------------------------------------------------------------------


class VerifyRunner:
    """Runs all verification rules against a database, returning findings."""

    _PERSON_CACHE_LIMIT = 20000
    _FAMILY_CACHE_LIMIT = 10000

    def __init__(self, db):
        self.db = db
        self._person_cache: dict = {}
        self._family_cache: dict = {}

    def find_person(self, handle):
        if handle not in self._person_cache:
            person = self.db.get_person_from_handle(handle)
            self._person_cache[handle] = VerifyPerson(self.db, person)
        return self._person_cache[handle]

    def find_family(self, handle):
        if handle not in self._family_cache:
            family = self.db.get_family_from_handle(handle)
            self._family_cache[handle] = VerifyFamily(self.db, family)
        return self._family_cache[handle]

    def _preload(self):
        if self.db.get_number_of_people() <= self._PERSON_CACHE_LIMIT:
            for person in self.db.iter_people():
                self._person_cache[person.get_handle()] = VerifyPerson(
                    self.db, person
                )
        if self.db.get_number_of_families() <= self._FAMILY_CACHE_LIMIT:
            for family in self.db.iter_families():
                self._family_cache[family.get_handle()] = VerifyFamily(
                    self.db, family
                )

    def _check_person(self, verify_person, opts, today):
        rule_list = [
            BirthAfterBapt(self, verify_person),
            DeathBeforeBapt(self, verify_person),
            BirthAfterBury(self, verify_person),
            DeathAfterBury(self, verify_person),
            BirthAfterDeath(self, verify_person),
            BaptAfterBury(self, verify_person),
            OldAge(self, verify_person, opts["oldage"], opts["estimate_age"]),
            OldAgeButNoDeath(
                self, verify_person, opts["oldage"], opts["estimate_age"], today
            ),
            UnknownGender(self, verify_person),
            MultipleParents(self, verify_person),
            MarriedOften(self, verify_person, opts["wedder"]),
            OldUnmarried(
                self, verify_person, opts["oldunm"], opts["estimate_age"]
            ),
            TooManyChildren(
                self, verify_person, opts["mxchilddad"], opts["mxchildmom"]
            ),
            Disconnected(self, verify_person),
            InvalidBirthDate(self, verify_person, opts["invdate"]),
            InvalidDeathDate(self, verify_person, opts["invdate"]),
            BirthEqualsDeath(self, verify_person),
            BirthEqualsMarriage(self, verify_person),
            DeathEqualsMarriage(self, verify_person),
            BaptTooLate(self, verify_person),
            BuryTooLate(self, verify_person),
            FamilyOrderIncorrect(self, verify_person, opts["estimate_age"]),
            PersonHasEventsOfTypeUnknown(self, verify_person),
            PersonHasEventsInWrongOrder(self, verify_person),
        ]
        return [rule.report_itself() for rule in rule_list if rule.broken()]

    def _check_family(self, verify_family, opts):
        rule_list = [
            SameSexFamily(self, verify_family),
            FemaleHusband(self, verify_family),
            MaleWife(self, verify_family),
            SameSurnameFamily(self, verify_family),
            LargeAgeGapFamily(
                self, verify_family, opts["hwdif"], opts["estimate_age"]
            ),
            MarriageBeforeBirth(self, verify_family, opts["estimate_age"]),
            MarriageAfterDeath(self, verify_family, opts["estimate_age"]),
            EarlyMarriage(
                self, verify_family, opts["yngmar"], opts["estimate_age"]
            ),
            LateMarriage(
                self, verify_family, opts["oldmar"], opts["estimate_age"]
            ),
            OldParent(
                self,
                verify_family,
                opts["oldmom"],
                opts["olddad"],
                opts["estimate_age"],
            ),
            YoungParent(
                self,
                verify_family,
                opts["yngmom"],
                opts["yngdad"],
                opts["estimate_age"],
            ),
            UnbornParent(self, verify_family, opts["estimate_age"]),
            DeadParent(self, verify_family, opts["estimate_age"]),
            LargeChildrenSpan(
                self, verify_family, opts["cbspan"], opts["estimate_age"]
            ),
            LargeChildrenAgeDiff(
                self, verify_family, opts["cspace"], opts["estimate_age"]
            ),
            MarriedRelation(self, verify_family),
            ChildrenOrderIncorrect(self, verify_family, opts["estimate_age"]),
            FamilyHasEventsOfTypeUnknown(self, verify_family),
            FamilyHasEventsInWrongOrder(self, verify_family),
        ]
        return [rule.report_itself() for rule in rule_list if rule.broken()]

    def run(self, options=None):
        opts = {**DEFAULT_OPTIONS, **(options or {})}
        self._preload()
        today = Today().get_sort_value()

        results = []
        family_handles = set(self.db.get_family_handles())

        for person in self.db.iter_people():
            verify_person = VerifyPerson(self.db, person)
            self._person_cache[verify_person.get_handle()] = verify_person

            for family_handle in verify_person.get_family_handle_list():
                if family_handle in family_handles:
                    verify_family = self.find_family(family_handle)
                    results.extend(self._check_family(verify_family, opts))
                    family_handles.remove(family_handle)

            results.extend(self._check_person(verify_person, opts, today))

        for family_handle in family_handles:
            verify_family = self.find_family(family_handle)
            results.extend(self._check_family(verify_family, opts))

        return results


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_age_at_death(person, estimate):
    birth_date = person.get_birth_date(estimate)
    death_date = person.get_death_date(estimate)
    if (birth_date > 0) and (death_date > 0):
        return death_date - birth_date
    return 0


def _get_father(runner, family):
    if not family:
        return VerifyPerson(None, None)
    father_handle = family.get_father_handle()
    if father_handle:
        return runner.find_person(father_handle)
    return VerifyPerson(None, None)


def _get_mother(runner, family):
    if not family:
        return VerifyPerson(None, None)
    mother_handle = family.get_mother_handle()
    if mother_handle:
        return runner.find_person(mother_handle)
    return VerifyPerson(None, None)


def _get_child_birth_dates(runner, family, estimate):
    dates = []
    for child_ref in family.get_child_ref_list():
        child = runner.find_person(child_ref.ref)
        child_birth_date = child.get_birth_date(estimate)
        if child_birth_date > 0:
            dates.append(child_birth_date)
    return dates


def _get_n_children(runner, person):
    number = 0
    for family_handle in person.get_family_handle_list():
        family = runner.find_family(family_handle)
        if family:
            number += len(family.get_child_ref_list())
    return number


# ---------------------------------------------------------------------------
# Rule base classes
# ---------------------------------------------------------------------------


class Rule:
    ID = 0
    TYPE = ""

    ERROR = 1
    WARNING = 2
    SEVERITY = WARNING

    TYPE_PERSON = "Person"
    TYPE_FAMILY = "Family"

    def __init__(self, runner, obj):
        self.runner = runner
        self.db = runner.db
        self.obj = obj

    def broken(self):
        return False

    def get_message(self):
        raise NotImplementedError

    def get_name(self):
        return self.obj.get_name()

    def get_handle(self):
        return self.obj.get_handle()

    def get_id(self):
        return self.obj.gramps_id

    def _get_params(self):
        return tuple()

    def report_itself(self):
        return {
            "message": self.get_message(),
            "object_type": self.TYPE,
            "object_id": self.get_id(),
            "object_handle": self.get_handle(),
            "name": self.get_name(),
            "rule_id": self.ID,
            "rule_params": list(self._get_params()),
            "severity": "error" if self.SEVERITY == self.ERROR else "warning",
        }


class PersonRule(Rule):
    TYPE = Rule.TYPE_PERSON


class FamilyRule(Rule):
    TYPE = Rule.TYPE_FAMILY


# ---------------------------------------------------------------------------
# Person rules
# ---------------------------------------------------------------------------


class BirthAfterBapt(PersonRule):
    ID = 1
    SEVERITY = Rule.ERROR

    def broken(self):
        birth_date = self.obj.get_birth_date()
        bapt_date = self.obj.get_bapt_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        bapt_ok = bapt_date > 0 if bapt_date is not None else False
        return birth_ok and bapt_ok and birth_date > bapt_date

    def get_message(self):
        return _("Baptism before birth")


class DeathBeforeBapt(PersonRule):
    ID = 2
    SEVERITY = Rule.ERROR

    def broken(self):
        death_date = self.obj.get_death_date()
        bapt_date = self.obj.get_bapt_date()
        bapt_ok = bapt_date > 0 if bapt_date is not None else False
        death_ok = death_date > 0 if death_date is not None else False
        return death_ok and bapt_ok and bapt_date > death_date

    def get_message(self):
        return _("Death before baptism")


class BirthAfterBury(PersonRule):
    ID = 3
    SEVERITY = Rule.ERROR

    def broken(self):
        birth_date = self.obj.get_birth_date()
        bury_date = self.obj.get_bury_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        bury_ok = bury_date > 0 if bury_date is not None else False
        return birth_ok and bury_ok and birth_date > bury_date

    def get_message(self):
        return _("Burial before birth")


class DeathAfterBury(PersonRule):
    ID = 4
    SEVERITY = Rule.ERROR

    def broken(self):
        death_date = self.obj.get_death_date()
        bury_date = self.obj.get_bury_date()
        death_ok = death_date > 0 if death_date is not None else False
        bury_ok = bury_date > 0 if bury_date is not None else False
        return death_ok and bury_ok and death_date > bury_date

    def get_message(self):
        return _("Burial before death")


class BirthAfterDeath(PersonRule):
    ID = 5
    SEVERITY = Rule.ERROR

    def broken(self):
        birth_date = self.obj.get_birth_date()
        death_date = self.obj.get_death_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        death_ok = death_date > 0 if death_date is not None else False
        return birth_ok and death_ok and birth_date > death_date

    def get_message(self):
        return _("Death before birth")


class BaptAfterBury(PersonRule):
    ID = 6
    SEVERITY = Rule.ERROR

    def broken(self):
        bapt_date = self.obj.get_bapt_date()
        bury_date = self.obj.get_bury_date()
        bapt_ok = bapt_date > 0 if bapt_date is not None else False
        bury_ok = bury_date > 0 if bury_date is not None else False
        return bapt_ok and bury_ok and bapt_date > bury_date

    def get_message(self):
        return _("Burial before baptism")


class OldAge(PersonRule):
    ID = 7
    SEVERITY = Rule.WARNING

    def __init__(self, runner, person, old_age, est):
        PersonRule.__init__(self, runner, person)
        self.old_age = old_age
        self.est = est

    def _get_params(self):
        return (self.old_age, self.est)

    def broken(self):
        age_at_death = _get_age_at_death(self.obj, self.est)
        return age_at_death / 365 > self.old_age

    def get_message(self):
        return _("Old age at death")


class UnknownGender(PersonRule):
    ID = 8
    SEVERITY = Rule.WARNING

    def broken(self):
        return self.obj.get_gender() == Person.UNKNOWN

    def get_message(self):
        return _("Unknown gender")


class MultipleParents(PersonRule):
    ID = 9
    SEVERITY = Rule.WARNING

    def broken(self):
        return len(self.obj.get_parent_family_handle_list()) > 1

    def get_message(self):
        return _("Multiple parents")


class MarriedOften(PersonRule):
    ID = 10
    SEVERITY = Rule.WARNING

    def __init__(self, runner, person, wedder):
        PersonRule.__init__(self, runner, person)
        self.wedder = wedder

    def _get_params(self):
        return (self.wedder,)

    def broken(self):
        return len(self.obj.get_family_handle_list()) > self.wedder

    def get_message(self):
        return _("Married often")


class OldUnmarried(PersonRule):
    ID = 11
    SEVERITY = Rule.WARNING

    def __init__(self, runner, person, old_unm, est):
        PersonRule.__init__(self, runner, person)
        self.old_unm = old_unm
        self.est = est

    def _get_params(self):
        return (self.old_unm, self.est)

    def broken(self):
        age_at_death = _get_age_at_death(self.obj, self.est)
        n_spouses = len(self.obj.get_family_handle_list())
        return age_at_death / 365 > self.old_unm and n_spouses == 0

    def get_message(self):
        return _("Old and unmarried")


class TooManyChildren(PersonRule):
    ID = 12
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, mx_child_dad, mx_child_mom):
        PersonRule.__init__(self, runner, obj)
        self.mx_child_dad = mx_child_dad
        self.mx_child_mom = mx_child_mom

    def _get_params(self):
        return (self.mx_child_dad, self.mx_child_mom)

    def broken(self):
        n_child = _get_n_children(self.runner, self.obj)
        if self.obj.get_gender() == Person.MALE and n_child > self.mx_child_dad:
            return True
        if self.obj.get_gender() == Person.FEMALE and n_child > self.mx_child_mom:
            return True
        return False

    def get_message(self):
        return _("Too many children")


class Disconnected(PersonRule):
    ID = 28
    SEVERITY = Rule.WARNING

    def broken(self):
        return (
            len(self.obj.get_parent_family_handle_list())
            + len(self.obj.get_family_handle_list())
            == 0
        )

    def get_message(self):
        return _("Disconnected individual")


class InvalidBirthDate(PersonRule):
    ID = 29
    SEVERITY = Rule.ERROR

    def __init__(self, runner, person, invdate):
        PersonRule.__init__(self, runner, person)
        self._invdate = invdate

    def broken(self):
        if not self._invdate:
            return False
        return self.obj.is_birth_date_invalid()

    def get_message(self):
        return _("Invalid birth date")


class InvalidDeathDate(PersonRule):
    ID = 30
    SEVERITY = Rule.ERROR

    def __init__(self, runner, person, invdate):
        PersonRule.__init__(self, runner, person)
        self._invdate = invdate

    def broken(self):
        if not self._invdate:
            return False
        return self.obj.is_death_date_invalid()

    def get_message(self):
        return _("Invalid death date")


class OldAgeButNoDeath(PersonRule):
    ID = 32
    SEVERITY = Rule.WARNING

    def __init__(self, runner, person, old_age, est, today):
        PersonRule.__init__(self, runner, person)
        self.old_age = old_age
        self.est = est
        self._today = today

    def _get_params(self):
        return (self.old_age, self.est)

    def broken(self):
        birth_date = self.obj.get_birth_date(self.est)
        dead = self.obj.get_death()
        death_date = self.obj.get_death_date(True)
        if dead or death_date or not birth_date:
            return False
        return (self._today - birth_date) / 365 > self.old_age

    def get_message(self):
        return _("Old age but no death")


class BirthEqualsDeath(PersonRule):
    ID = 33
    SEVERITY = Rule.WARNING

    def broken(self):
        birth_date = self.obj.get_birth_date()
        death_date = self.obj.get_death_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        death_ok = death_date > 0 if death_date is not None else False
        return death_ok and birth_ok and birth_date == death_date

    def get_message(self):
        return _("Birth date equals death date")


class BirthEqualsMarriage(PersonRule):
    ID = 34
    SEVERITY = Rule.ERROR

    def broken(self):
        birth_date = self.obj.get_birth_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        for fhandle in self.obj.get_family_handle_list():
            family = self.runner.find_family(fhandle)
            marr_date = family.get_marriage_date()
            marr_ok = marr_date > 0 if marr_date is not None else False
            return marr_ok and birth_ok and birth_date == marr_date
        return False

    def get_message(self):
        return _("Birth date equals marriage date")


class DeathEqualsMarriage(PersonRule):
    ID = 35
    SEVERITY = Rule.WARNING

    def broken(self):
        death_date = self.obj.get_death_date()
        death_ok = death_date > 0 if death_date is not None else False
        for fhandle in self.obj.get_family_handle_list():
            family = self.runner.find_family(fhandle)
            marr_date = family.get_marriage_date()
            marr_ok = marr_date > 0 if marr_date is not None else False
            return marr_ok and death_ok and death_date == marr_date
        return False

    def get_message(self):
        return _("Death date equals marriage date")


class BaptTooLate(PersonRule):
    ID = 36
    SEVERITY = Rule.WARNING

    def broken(self):
        parents = self.obj.get_parent_family_handle_list()
        if len(parents) != 1:
            return False
        family = self.runner.find_family(parents[0])
        if not family:
            return False
        children = family.get_child_ref_list()
        if len(children) <= 1:
            return False

        birth_date = self.obj.get_birth_date()
        bapt_date = self.obj.get_bapt_date()
        birth_ok = birth_date > 0 if birth_date is not None else False
        bapt_ok = bapt_date > 0 if bapt_date is not None else False
        if not birth_ok or not bapt_ok or bapt_date < birth_date:
            return False
        birth_bapt_distance = bapt_date - birth_date

        child_birth_bapt_distances = []
        for childref in children:
            if int(childref.get_mother_relation()) == ChildRefType.BIRTH:
                child = self.runner.find_person(childref.ref)
                if self.obj.get_gramps_id() == child.get_gramps_id():
                    continue
                c_birth = child.get_birth_date()
                c_bapt = child.get_bapt_date()
                c_birth_ok = c_birth > 0 if c_birth is not None else False
                c_bapt_ok = c_bapt > 0 if c_bapt is not None else False
                if c_birth_ok and c_bapt_ok and c_bapt >= c_birth:
                    child_birth_bapt_distances.append(c_bapt - c_birth)

        if not child_birth_bapt_distances:
            return False
        return birth_bapt_distance > statistics.median(child_birth_bapt_distances) + 120

    def get_message(self):
        return _("Baptism too late according to family tradition")


class BuryTooLate(PersonRule):
    ID = 37
    SEVERITY = Rule.WARNING

    def broken(self):
        death_date = self.obj.get_death_date()
        bury_date = self.obj.get_bury_date()
        death_ok = death_date > 0 if death_date is not None else False
        bury_ok = bury_date > 0 if bury_date is not None else False
        if not death_ok or not bury_ok or bury_date < death_date:
            return False
        return (bury_date - death_date) > 14

    def get_message(self):
        return _("Burial too late")


class FamilyOrderIncorrect(PersonRule):
    ID = 39
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, est):
        PersonRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        families = self.obj.get_family_handle_list()
        if len(families) < 2:
            return False

        prev_compare_date = 0
        for fhandle in families:
            family = self.runner.find_family(fhandle)
            if not family:
                continue

            compare_date = 0
            marr_date = family.get_marriage_date()
            marr_ok = marr_date > 0 if marr_date is not None else False
            if marr_ok:
                compare_date = marr_date
            else:
                div_date = family.get_divorce_date()
                div_ok = div_date > 0 if div_date is not None else False
                if div_ok:
                    compare_date = div_date
                else:
                    for childref in family.get_child_ref_list():
                        if int(childref.get_mother_relation()) == ChildRefType.BIRTH:
                            child = self.runner.find_person(childref.ref)
                            birth_date = child.get_birth_date(self.est)
                            birth_ok = (
                                birth_date > 0 if birth_date is not None else False
                            )
                            if birth_ok and (
                                birth_date < compare_date or compare_date == 0
                            ):
                                compare_date = birth_date
            if compare_date != 0 and compare_date < prev_compare_date:
                return True
            prev_compare_date = compare_date
        return False

    def get_message(self):
        return _("Families are not in chronological order")


class PersonHasEventsOfTypeUnknown(PersonRule):
    ID = 41
    SEVERITY = Rule.ERROR

    def broken(self):
        return self.obj.is_events_of_type_unknown()

    def get_message(self):
        return _("Person has events with role Unknown")


class PersonHasEventsInWrongOrder(PersonRule):
    ID = 43
    SEVERITY = Rule.ERROR

    def broken(self):
        return self.obj.is_events_in_wrong_order()

    def get_message(self):
        return _("Person events are not in chronological order")


# ---------------------------------------------------------------------------
# Family rules
# ---------------------------------------------------------------------------


class SameSexFamily(FamilyRule):
    ID = 13
    SEVERITY = Rule.WARNING

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        same_sex = mother and father and (mother.get_gender() == father.get_gender())
        unknown_sex = mother and (mother.get_gender() == Person.UNKNOWN)
        return same_sex and not unknown_sex

    def get_message(self):
        return _("Same sex marriage")


class FemaleHusband(FamilyRule):
    ID = 14
    SEVERITY = Rule.WARNING

    def broken(self):
        father = _get_father(self.runner, self.obj)
        return father and (father.get_gender() == Person.FEMALE)

    def get_message(self):
        return _("Female husband")


class MaleWife(FamilyRule):
    ID = 15
    SEVERITY = Rule.WARNING

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        return mother and (mother.get_gender() == Person.MALE)

    def get_message(self):
        return _("Male wife")


class SameSurnameFamily(FamilyRule):
    ID = 16
    SEVERITY = Rule.WARNING

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        if not (mother and father):
            return False
        mname = mother.get_surname()
        fname = father.get_surname()
        if (
            mother.get_name_type() == NameType.BIRTH
            and father.get_name_type() == NameType.BIRTH
            and len(mname) != 0
            and len(fname) != 0
            and mname == fname
        ):
            return True
        return False

    def get_message(self):
        return _("Husband and wife with the same surname")


class LargeAgeGapFamily(FamilyRule):
    ID = 17
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, hw_diff, est):
        FamilyRule.__init__(self, runner, obj)
        self.hw_diff = hw_diff
        self.est = est

    def _get_params(self):
        return (self.hw_diff, self.est)

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)
        mother_birth_date_ok = mother_birth_date > 0
        father_birth_date_ok = father_birth_date > 0
        large_diff = (
            abs(father_birth_date - mother_birth_date) / 365 > self.hw_diff
        )
        return mother_birth_date_ok and father_birth_date_ok and large_diff

    def get_message(self):
        return _("Large age difference between spouses")


class MarriageBeforeBirth(FamilyRule):
    ID = 18
    SEVERITY = Rule.ERROR

    def __init__(self, runner, obj, est):
        FamilyRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        marr_date = self.obj.get_marriage_date()
        marr_date_ok = marr_date > 0
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)
        father_broken = (
            father_birth_date > 0
            and marr_date_ok
            and (father_birth_date > marr_date)
        )
        mother_broken = (
            mother_birth_date > 0
            and marr_date_ok
            and (mother_birth_date > marr_date)
        )
        return father_broken or mother_broken

    def get_message(self):
        return _("Marriage before birth")


class MarriageAfterDeath(FamilyRule):
    ID = 19
    SEVERITY = Rule.ERROR

    def __init__(self, runner, obj, est):
        FamilyRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        marr_date = self.obj.get_marriage_date()
        marr_date_ok = marr_date > 0
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_death_date = mother.get_death_date(self.est)
        father_death_date = father.get_death_date(self.est)
        father_broken = (
            father_death_date > 0
            and marr_date_ok
            and (father_death_date < marr_date)
        )
        mother_broken = (
            mother_death_date > 0
            and marr_date_ok
            and (mother_death_date < marr_date)
        )
        return father_broken or mother_broken

    def get_message(self):
        return _("Marriage after death")


class EarlyMarriage(FamilyRule):
    ID = 20
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, yng_mar, est):
        FamilyRule.__init__(self, runner, obj)
        self.yng_mar = yng_mar
        self.est = est

    def _get_params(self):
        return (self.yng_mar, self.est)

    def broken(self):
        marr_date = self.obj.get_marriage_date()
        marr_date_ok = marr_date > 0
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)
        father_broken = (
            father_birth_date > 0
            and marr_date_ok
            and father_birth_date < marr_date
            and ((marr_date - father_birth_date) / 365 < self.yng_mar)
        )
        mother_broken = (
            mother_birth_date > 0
            and marr_date_ok
            and mother_birth_date < marr_date
            and ((marr_date - mother_birth_date) / 365 < self.yng_mar)
        )
        return father_broken or mother_broken

    def get_message(self):
        return _("Early marriage")


class LateMarriage(FamilyRule):
    ID = 21
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, old_mar, est):
        FamilyRule.__init__(self, runner, obj)
        self.old_mar = old_mar
        self.est = est

    def _get_params(self):
        return (self.old_mar, self.est)

    def broken(self):
        marr_date = self.obj.get_marriage_date()
        marr_date_ok = marr_date > 0
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)
        father_broken = (
            father_birth_date > 0
            and marr_date_ok
            and ((marr_date - father_birth_date) / 365 > self.old_mar)
        )
        mother_broken = (
            mother_birth_date > 0
            and marr_date_ok
            and ((marr_date - mother_birth_date) / 365 > self.old_mar)
        )
        return father_broken or mother_broken

    def get_message(self):
        return _("Late marriage")


class OldParent(FamilyRule):
    ID = 22
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, old_mom, old_dad, est):
        FamilyRule.__init__(self, runner, obj)
        self.old_mom = old_mom
        self.old_dad = old_dad
        self.est = est

    def _get_params(self):
        return (self.old_mom, self.old_dad, self.est)

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)

        for child_ref in self.obj.get_child_ref_list():
            child = self.runner.find_person(child_ref.ref)
            child_birth_date = child.get_birth_date(self.est)
            if not child_birth_date > 0:
                continue
            if father_birth_date > 0 and (
                (child_birth_date - father_birth_date) / 365 > self.old_dad
            ):
                self._msg = _("Old father")
                return True
            if mother_birth_date > 0 and (
                (child_birth_date - mother_birth_date) / 365 > self.old_mom
            ):
                self._msg = _("Old mother")
                return True
        return False

    def get_message(self):
        return self._msg


class YoungParent(FamilyRule):
    ID = 23
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, yng_mom, yng_dad, est):
        FamilyRule.__init__(self, runner, obj)
        self.yng_dad = yng_dad
        self.yng_mom = yng_mom
        self.est = est

    def _get_params(self):
        return (self.yng_mom, self.yng_dad, self.est)

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)

        for child_ref in self.obj.get_child_ref_list():
            child = self.runner.find_person(child_ref.ref)
            child_birth_date = child.get_birth_date(self.est)
            if not child_birth_date > 0:
                continue
            if father_birth_date > 0 and (
                (child_birth_date - father_birth_date) / 365 < self.yng_dad
            ):
                self._msg = _("Young father")
                return True
            if mother_birth_date > 0 and (
                (child_birth_date - mother_birth_date) / 365 < self.yng_mom
            ):
                self._msg = _("Young mother")
                return True
        return False

    def get_message(self):
        return self._msg


class UnbornParent(FamilyRule):
    ID = 24
    SEVERITY = Rule.ERROR

    def __init__(self, runner, obj, est):
        FamilyRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_birth_date = mother.get_birth_date(self.est)
        father_birth_date = father.get_birth_date(self.est)

        for child_ref in self.obj.get_child_ref_list():
            child = self.runner.find_person(child_ref.ref)
            child_birth_date = child.get_birth_date(self.est)
            if not child_birth_date > 0:
                continue
            if father_birth_date > 0 and father_birth_date > child_birth_date:
                self._msg = _("Unborn father")
                return True
            if mother_birth_date > 0 and mother_birth_date > child_birth_date:
                self._msg = _("Unborn mother")
                return True
        return False

    def get_message(self):
        return self._msg


class DeadParent(FamilyRule):
    ID = 25
    SEVERITY = Rule.ERROR

    def __init__(self, runner, obj, est):
        FamilyRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        mother = _get_mother(self.runner, self.obj)
        father = _get_father(self.runner, self.obj)
        mother_death_date = mother.get_death_date(self.est)
        father_death_date = father.get_death_date(self.est)

        for child_ref in self.obj.get_child_ref_list():
            child = self.runner.find_person(child_ref.ref)
            child_birth_date = child.get_birth_date(self.est)
            if not child_birth_date > 0:
                continue
            has_birth_rel_to_father = child_ref.frel == ChildRefType.BIRTH
            has_birth_rel_to_mother = child_ref.mrel == ChildRefType.BIRTH
            if (
                has_birth_rel_to_father
                and father_death_date > 0
                and (father_death_date + 294) < child_birth_date
            ):
                self._msg = _("Dead father")
                return True
            if (
                has_birth_rel_to_mother
                and mother_death_date > 0
                and mother_death_date < child_birth_date
            ):
                self._msg = _("Dead mother")
                return True
        return False

    def get_message(self):
        return self._msg


class LargeChildrenSpan(FamilyRule):
    ID = 26
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, cb_span, est):
        FamilyRule.__init__(self, runner, obj)
        self.cbs = cb_span
        self.est = est

    def _get_params(self):
        return (self.cbs, self.est)

    def broken(self):
        dates = sorted(_get_child_birth_dates(self.runner, self.obj, self.est))
        return dates and (dates[-1] - dates[0]) / 365 > self.cbs

    def get_message(self):
        return _("Large year span for all children")


class LargeChildrenAgeDiff(FamilyRule):
    ID = 27
    SEVERITY = Rule.WARNING

    def __init__(self, runner, obj, c_space, est):
        FamilyRule.__init__(self, runner, obj)
        self.c_space = c_space
        self.est = est

    def _get_params(self):
        return (self.c_space, self.est)

    def broken(self):
        dates = _get_child_birth_dates(self.runner, self.obj, self.est)
        diffs = [dates[i + 1] - dates[i] for i in range(len(dates) - 1)]
        return diffs and max(diffs) / 365 > self.c_space

    def get_message(self):
        return _("Large age differences between children")


class MarriedRelation(FamilyRule):
    ID = 31
    SEVERITY = Rule.WARNING

    def broken(self):
        marr_date = self.obj.get_marriage_date()
        marr_date_ok = marr_date > 0
        married = self.obj.get_relationship() in (
            FamilyRelType.MARRIED,
            FamilyRelType.CIVIL_UNION,
        )
        return not married and marr_date_ok

    def get_message(self):
        return _("Marriage date but not married")


class ChildrenOrderIncorrect(FamilyRule):
    ID = 38
    SEVERITY = Rule.ERROR

    def __init__(self, runner, obj, est):
        FamilyRule.__init__(self, runner, obj)
        self.est = est

    def _get_params(self):
        return (self.est,)

    def broken(self):
        children = self.obj.get_child_ref_list()
        if len(children) <= 1:
            return False
        prev_birth_date = 0
        for childref in children:
            if int(childref.get_mother_relation()) == ChildRefType.BIRTH:
                child = self.runner.find_person(childref.ref)
                birth_date = child.get_birth_date(self.est)
                birth_ok = birth_date > 0 if birth_date is not None else False
                if birth_ok and birth_date < prev_birth_date:
                    return True
                prev_birth_date = birth_date
        return False

    def get_message(self):
        return _("Children are not in chronological order")


class FamilyHasEventsOfTypeUnknown(FamilyRule):
    ID = 40
    SEVERITY = Rule.ERROR

    def broken(self):
        return self.obj.is_events_of_type_unknown()

    def get_message(self):
        return _("Family has events with role Unknown")


class FamilyHasEventsInWrongOrder(FamilyRule):
    ID = 42
    SEVERITY = Rule.ERROR

    def broken(self):
        return self.obj.is_events_in_wrong_order()

    def get_message(self):
        return _("Family events are not in chronological order")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_verify(db, options=None):
    """Run all verification rules against *db* and return a list of findings.

    *options* may be a ``VerifyOptions`` instance, a plain dict of overrides,
    or ``None`` to use all defaults.

    Each finding is a dict with keys: message, object_type, object_id,
    object_handle, name, rule_id, rule_params, severity.
    """
    if isinstance(options, VerifyOptions):
        options = options.as_dict()
    runner = VerifyRunner(db)
    return runner.run(options)
