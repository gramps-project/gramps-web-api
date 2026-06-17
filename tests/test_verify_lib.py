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

"""Unit tests for gramps_webapi.verify_lib."""

import unittest

from gramps.gen.lib import Person

from gramps_webapi.verify_lib import (
    DEFAULT_OPTIONS,
    VerifyOptions,
    BaptAfterBury,
    BirthAfterBapt,
    BirthAfterBury,
    BirthAfterDeath,
    BirthEqualsDeath,
    ChildrenOrderIncorrect,
    DeadParent,
    DeathAfterBury,
    DeathBeforeBapt,
    EarlyMarriage,
    FamilyHasEventsInWrongOrder,
    FamilyHasEventsOfTypeUnknown,
    FamilyOrderIncorrect,
    FemaleHusband,
    InvalidBirthDate,
    LargeAgeGapFamily,
    LargeChildrenAgeDiff,
    LargeChildrenSpan,
    LateMarriage,
    MaleWife,
    MarriageAfterDeath,
    MarriageBeforeBirth,
    MarriedOften,
    MarriedRelation,
    MultipleParents,
    OldAge,
    OldAgeButNoDeath,
    OldParent,
    OldUnmarried,
    PersonHasEventsInWrongOrder,
    PersonHasEventsOfTypeUnknown,
    SameSexFamily,
    TooManyChildren,
    UnbornParent,
    UnknownGender,
    VerifyFamily,
    VerifyPerson,
    YoungParent,
    run_verify,
)

from tests import ExampleDbInMemory


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------


class _FakePerson(VerifyPerson):
    """VerifyPerson constructed without a DB."""

    def __init__(self, **kwargs):
        super().__init__(None, None)
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeFamily(VerifyFamily):
    """VerifyFamily constructed without a DB."""

    def __init__(self, **kwargs):
        super().__init__(None, None)
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockRunner:
    """Minimal runner stub — returns empty objects by default."""

    db = None

    def __init__(self, persons=None, families=None):
        self._persons = persons or {}
        self._families = families or {}

    def find_person(self, handle):
        return self._persons.get(handle, _FakePerson())

    def find_family(self, handle):
        return self._families.get(handle, _FakeFamily())


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run(rule_cls, obj, runner=None, **kwargs):
    """Instantiate a rule and return (broken, result_dict)."""
    r = runner or _MockRunner()
    rule = rule_cls(r, obj, **kwargs)
    broken = rule.broken()
    result = rule.report_itself() if broken else None
    return broken, result


# ---------------------------------------------------------------------------
# VerifyOptions tests
# ---------------------------------------------------------------------------


class TestVerifyOptions(unittest.TestCase):

    def test_defaults_match_module_constant(self):
        self.assertEqual(VerifyOptions.defaults, DEFAULT_OPTIONS)

    def test_default_instantiation(self):
        opts = VerifyOptions()
        self.assertEqual(opts.as_dict(), VerifyOptions.defaults)

    def test_override_applied(self):
        opts = VerifyOptions(oldage=100)
        self.assertEqual(opts["oldage"], 100)
        self.assertEqual(opts["hwdif"], VerifyOptions.defaults["hwdif"])

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            VerifyOptions(nonexistent=42)

    def test_all_options_have_help(self):
        self.assertEqual(set(VerifyOptions.defaults), set(VerifyOptions.help))

    def test_repr(self):
        opts = VerifyOptions(oldage=100)
        self.assertIn("oldage", repr(opts))

    def test_as_dict_is_copy(self):
        opts = VerifyOptions()
        d = opts.as_dict()
        d["oldage"] = 999
        self.assertEqual(opts["oldage"], VerifyOptions.defaults["oldage"])


# ---------------------------------------------------------------------------
# Person-rule tests
# ---------------------------------------------------------------------------


class TestPersonRules(unittest.TestCase):

    def test_birth_after_bapt_broken(self):
        p = _FakePerson(birth_date=[200, 200], bapt_date=[100, 100])
        broken, res = _run(BirthAfterBapt, p)
        self.assertTrue(broken)
        self.assertEqual(res["rule_id"], 1)
        self.assertEqual(res["severity"], "error")
        self.assertEqual(res["object_type"], "Person")

    def test_birth_after_bapt_ok(self):
        p = _FakePerson(birth_date=[100, 100], bapt_date=[200, 200])
        broken, _ = _run(BirthAfterBapt, p)
        self.assertFalse(broken)

    def test_birth_after_bapt_missing_dates(self):
        p = _FakePerson(birth_date=[0, 0], bapt_date=[0, 0])
        broken, _ = _run(BirthAfterBapt, p)
        self.assertFalse(broken)

    def test_death_before_bapt_broken(self):
        p = _FakePerson(death_date=[100, 100], bapt_date=[200, 200])
        broken, res = _run(DeathBeforeBapt, p)
        self.assertTrue(broken)
        self.assertEqual(res["rule_id"], 2)

    def test_birth_after_bury_broken(self):
        p = _FakePerson(birth_date=[300, 300], bury_date=[100, 100])
        broken, _ = _run(BirthAfterBury, p)
        self.assertTrue(broken)

    def test_death_after_bury_broken(self):
        p = _FakePerson(death_date=[300, 300], bury_date=[100, 100])
        broken, _ = _run(DeathAfterBury, p)
        self.assertTrue(broken)

    def test_birth_after_death_broken(self):
        p = _FakePerson(birth_date=[300, 300], death_date=[100, 100])
        broken, res = _run(BirthAfterDeath, p)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "error")

    def test_bapt_after_bury_broken(self):
        p = _FakePerson(bapt_date=[300, 300], bury_date=[100, 100])
        broken, _ = _run(BaptAfterBury, p)
        self.assertTrue(broken)

    def test_old_age_broken(self):
        # 400 years in sort-value days
        p = _FakePerson(birth_date=[0, 100], death_date=[0, 100 + 400 * 365])
        broken, res = _run(OldAge, p, old_age=90, est=True)
        self.assertTrue(broken)
        self.assertEqual(res["rule_id"], 7)
        self.assertEqual(res["severity"], "warning")

    def test_old_age_ok(self):
        p = _FakePerson(birth_date=[0, 100], death_date=[0, 100 + 50 * 365])
        broken, _ = _run(OldAge, p, old_age=90, est=True)
        self.assertFalse(broken)

    def test_unknown_gender_broken(self):
        p = _FakePerson(gender=Person.UNKNOWN)
        broken, _ = _run(UnknownGender, p)
        self.assertTrue(broken)

    def test_unknown_gender_ok(self):
        p = _FakePerson(gender=Person.MALE)
        broken, _ = _run(UnknownGender, p)
        self.assertFalse(broken)

    def test_multiple_parents_broken(self):
        p = _FakePerson(parent_family_handle_list=["fam1", "fam2"])
        broken, _ = _run(MultipleParents, p)
        self.assertTrue(broken)

    def test_multiple_parents_ok(self):
        p = _FakePerson(parent_family_handle_list=["fam1"])
        broken, _ = _run(MultipleParents, p)
        self.assertFalse(broken)

    def test_married_often_broken(self):
        p = _FakePerson(family_handle_list=["f1", "f2", "f3", "f4"])
        broken, _ = _run(MarriedOften, p, wedder=3)
        self.assertTrue(broken)

    def test_married_often_ok(self):
        p = _FakePerson(family_handle_list=["f1", "f2"])
        broken, _ = _run(MarriedOften, p, wedder=3)
        self.assertFalse(broken)

    def test_old_unmarried_broken(self):
        p = _FakePerson(
            birth_date=[0, 100], death_date=[0, 100 + 150 * 365],
            family_handle_list=[]
        )
        broken, _ = _run(OldUnmarried, p, old_unm=99, est=True)
        self.assertTrue(broken)

    def test_too_many_children_male_broken(self):
        fam = _FakeFamily(child_ref_list=list(range(20)))
        runner = _MockRunner(families={"f1": fam})
        p = _FakePerson(gender=Person.MALE, family_handle_list=["f1"])
        broken, _ = _run(TooManyChildren, p, runner=runner,
                         mx_child_dad=15, mx_child_mom=12)
        self.assertTrue(broken)

    def test_birth_equals_death_broken(self):
        p = _FakePerson(birth_date=[500, 500], death_date=[500, 500])
        broken, _ = _run(BirthEqualsDeath, p)
        self.assertTrue(broken)

    def test_invalid_birth_date_broken(self):
        p = _FakePerson(birth_date_invalid=True)
        broken, _ = _run(InvalidBirthDate, p, invdate=True)
        self.assertTrue(broken)

    def test_invalid_birth_date_skipped(self):
        p = _FakePerson(birth_date_invalid=True)
        broken, _ = _run(InvalidBirthDate, p, invdate=False)
        self.assertFalse(broken)

    def test_old_age_but_no_death_broken(self):
        today = 100 + 200 * 365
        p = _FakePerson(birth_date=[100, 100], death_date=[0, 0], death=False)
        broken, _ = _run(OldAgeButNoDeath, p, old_age=90, est=True, today=today)
        self.assertTrue(broken)

    def test_old_age_but_no_death_ok_when_dead(self):
        today = 100 + 200 * 365
        p = _FakePerson(birth_date=[100, 100], death_date=[0, 0], death=True)
        broken, _ = _run(OldAgeButNoDeath, p, old_age=90, est=True, today=today)
        self.assertFalse(broken)

    def test_person_events_unknown_broken(self):
        p = _FakePerson(events_of_type_unknown=True)
        broken, res = _run(PersonHasEventsOfTypeUnknown, p)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "error")

    def test_person_events_wrong_order_broken(self):
        p = _FakePerson(events_in_wrong_order=True)
        broken, _ = _run(PersonHasEventsInWrongOrder, p)
        self.assertTrue(broken)


# ---------------------------------------------------------------------------
# Family-rule tests
# ---------------------------------------------------------------------------


class TestFamilyRules(unittest.TestCase):

    def _couple(self, father_gender=Person.MALE, mother_gender=Person.FEMALE,
                father_birth=0, mother_birth=0,
                father_death=0, mother_death=0):
        father = _FakePerson(
            gender=father_gender,
            birth_date=[father_birth, father_birth],
            death_date=[father_death, father_death],
        )
        mother = _FakePerson(
            gender=mother_gender,
            birth_date=[mother_birth, mother_birth],
            death_date=[mother_death, mother_death],
        )
        fam = _FakeFamily(
            father_handle="dad",
            mother_handle="mom",
        )
        runner = _MockRunner(
            persons={"dad": father, "mom": mother}
        )
        return fam, runner

    def test_same_sex_family_broken(self):
        fam, runner = self._couple(father_gender=Person.FEMALE, mother_gender=Person.FEMALE)
        broken, _ = _run(SameSexFamily, fam, runner=runner)
        self.assertTrue(broken)

    def test_same_sex_family_ok(self):
        fam, runner = self._couple()
        broken, _ = _run(SameSexFamily, fam, runner=runner)
        self.assertFalse(broken)

    def test_female_husband_broken(self):
        fam, runner = self._couple(father_gender=Person.FEMALE)
        broken, res = _run(FemaleHusband, fam, runner=runner)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "warning")

    def test_male_wife_broken(self):
        fam, runner = self._couple(mother_gender=Person.MALE)
        broken, _ = _run(MaleWife, fam, runner=runner)
        self.assertTrue(broken)

    def test_large_age_gap_broken(self):
        # father born year 1, mother born 50 years later → gap > 30 years
        fam, runner = self._couple(father_birth=1, mother_birth=50 * 365 + 1)
        broken, _ = _run(LargeAgeGapFamily, fam, runner=runner, hw_diff=30, est=True)
        self.assertTrue(broken)

    def test_large_age_gap_ok(self):
        fam, runner = self._couple(father_birth=1, mother_birth=5 * 365 + 1)
        broken, _ = _run(LargeAgeGapFamily, fam, runner=runner, hw_diff=30, est=True)
        self.assertFalse(broken)

    def test_marriage_before_birth_broken(self):
        # father born after marriage
        fam, runner = self._couple(father_birth=500)
        fam.marr_date = 100
        broken, res = _run(MarriageBeforeBirth, fam, runner=runner, est=True)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "error")

    def test_marriage_after_death_broken(self):
        # father dead before marriage
        fam, runner = self._couple(father_death=100)
        fam.marr_date = 500
        broken, _ = _run(MarriageAfterDeath, fam, runner=runner, est=True)
        self.assertTrue(broken)

    def test_early_marriage_broken(self):
        # father born 5 years before marriage (min is 17)
        fam, runner = self._couple(father_birth=1)
        fam.marr_date = 5 * 365 + 1
        broken, _ = _run(EarlyMarriage, fam, runner=runner, yng_mar=17, est=True)
        self.assertTrue(broken)

    def test_late_marriage_broken(self):
        # father born 60 years before marriage (max is 50)
        fam, runner = self._couple(father_birth=1)
        fam.marr_date = 60 * 365 + 1
        broken, _ = _run(LateMarriage, fam, runner=runner, old_mar=50, est=True)
        self.assertTrue(broken)

    def test_unborn_parent_broken(self):
        # father born after child
        child = _FakePerson(birth_date=[100, 100])
        father = _FakePerson(
            gender=Person.MALE, birth_date=[500, 500], death_date=[0, 0]
        )
        mother = _FakePerson(
            gender=Person.FEMALE, birth_date=[0, 0], death_date=[0, 0]
        )

        class _Ref:
            ref = "child"
            frel = 0
            mrel = 0

        fam = _FakeFamily(
            father_handle="dad", mother_handle="mom", child_ref_list=[_Ref()]
        )
        runner = _MockRunner(
            persons={"dad": father, "mom": mother, "child": child}
        )
        broken, res = _run(UnbornParent, fam, runner=runner, est=True)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "error")

    def test_large_children_span_broken(self):
        child1 = _FakePerson(birth_date=[100, 100])
        child2 = _FakePerson(birth_date=[100 + 30 * 365, 100 + 30 * 365])

        class _Ref:
            def __init__(self, h):
                self.ref = h

        fam = _FakeFamily(child_ref_list=[_Ref("c1"), _Ref("c2")])
        runner = _MockRunner(persons={"c1": child1, "c2": child2})
        broken, _ = _run(LargeChildrenSpan, fam, runner=runner, cb_span=25, est=True)
        self.assertTrue(broken)

    def test_large_children_age_diff_broken(self):
        child1 = _FakePerson(birth_date=[100, 100])
        child2 = _FakePerson(birth_date=[100 + 10 * 365, 100 + 10 * 365])

        class _Ref:
            def __init__(self, h):
                self.ref = h

        fam = _FakeFamily(child_ref_list=[_Ref("c1"), _Ref("c2")])
        runner = _MockRunner(persons={"c1": child1, "c2": child2})
        broken, _ = _run(LargeChildrenAgeDiff, fam, runner=runner, c_space=8, est=True)
        self.assertTrue(broken)

    def test_married_relation_broken(self):
        from gramps.gen.lib import FamilyRelType
        fam = _FakeFamily(marr_date=500, relationship=FamilyRelType.UNKNOWN)
        broken, _ = _run(MarriedRelation, fam)
        self.assertTrue(broken)

    def test_family_events_unknown_broken(self):
        fam = _FakeFamily(events_of_type_unknown=True)
        broken, res = _run(FamilyHasEventsOfTypeUnknown, fam)
        self.assertTrue(broken)
        self.assertEqual(res["severity"], "error")

    def test_family_events_wrong_order_broken(self):
        fam = _FakeFamily(events_in_wrong_order=True)
        broken, _ = _run(FamilyHasEventsInWrongOrder, fam)
        self.assertTrue(broken)


# ---------------------------------------------------------------------------
# Result dict shape
# ---------------------------------------------------------------------------


class TestResultShape(unittest.TestCase):

    def test_result_keys(self):
        p = _FakePerson(birth_date=[200, 200], bapt_date=[100, 100],
                        gramps_id="I0001", name="Doe, John")
        rule = BirthAfterBapt(_MockRunner(), p)
        self.assertTrue(rule.broken())
        res = rule.report_itself()
        expected_keys = {
            "message", "object_type", "object_id", "object_handle",
            "name", "rule_id", "rule_params", "severity",
        }
        self.assertEqual(set(res.keys()), expected_keys)

    def test_severity_values(self):
        p_err = _FakePerson(birth_date=[200, 200], bapt_date=[100, 100])
        rule_err = BirthAfterBapt(_MockRunner(), p_err)
        self.assertEqual(rule_err.report_itself()["severity"], "error")

        p_warn = _FakePerson(gender=Person.UNKNOWN)
        rule_warn = UnknownGender(_MockRunner(), p_warn)
        self.assertEqual(rule_warn.report_itself()["severity"], "warning")

    def test_rule_params_are_list(self):
        p = _FakePerson(birth_date=[0, 100], death_date=[0, 100 + 400 * 365])
        rule = OldAge(_MockRunner(), p, old_age=90, est=True)
        res = rule.report_itself()
        self.assertIsInstance(res["rule_params"], list)
        self.assertIn(90, res["rule_params"])


# ---------------------------------------------------------------------------
# run_verify smoke test against the real example DB
# ---------------------------------------------------------------------------


class TestRunVerify(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._example = ExampleDbInMemory()
        cls.db = cls._example.load()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._example.close()

    def test_returns_list(self):
        results = run_verify(self.db)
        self.assertIsInstance(results, list)

    def test_results_are_nonempty(self):
        results = run_verify(self.db)
        # The example DB is known to have data issues.
        self.assertGreater(len(results), 0)

    def test_result_shape(self):
        results = run_verify(self.db)
        required = {
            "message", "object_type", "object_id", "object_handle",
            "name", "rule_id", "rule_params", "severity",
        }
        for item in results:
            self.assertEqual(set(item.keys()), required)

    def test_severity_values(self):
        results = run_verify(self.db)
        for item in results:
            self.assertIn(item["severity"], ("error", "warning"))

    def test_object_type_values(self):
        results = run_verify(self.db)
        for item in results:
            self.assertIn(item["object_type"], ("Person", "Family"))

    def test_default_options_used(self):
        results_default = run_verify(self.db)
        results_explicit = run_verify(self.db, DEFAULT_OPTIONS)
        self.assertEqual(len(results_default), len(results_explicit))

    def test_options_change_results(self):
        # Raising the max-age threshold should reduce or maintain OldAge findings.
        results_strict = run_verify(self.db, {"oldage": 50})
        results_lenient = run_verify(self.db, {"oldage": 200})
        strict_old_age = [r for r in results_strict if r["rule_id"] == 7]
        lenient_old_age = [r for r in results_lenient if r["rule_id"] == 7]
        self.assertGreaterEqual(len(strict_old_age), len(lenient_old_age))

    def test_verify_options_instance_accepted(self):
        """VerifyOptions instance is accepted by run_verify."""
        opts = VerifyOptions(oldage=200)
        results = run_verify(self.db, opts)
        self.assertIsInstance(results, list)

    def test_verify_options_same_as_dict(self):
        """VerifyOptions and equivalent dict produce identical results."""
        opts = VerifyOptions(oldage=50)
        results_obj = run_verify(self.db, opts)
        results_dict = run_verify(self.db, {"oldage": 50})
        self.assertEqual(len(results_obj), len(results_dict))


if __name__ == "__main__":
    unittest.main()
