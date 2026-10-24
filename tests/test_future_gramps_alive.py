#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Tests for gramps_webapi.future_gramps.alive."""

import unittest

from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules.person import ProbablyAlive
from gramps.gen.lib import (
    Attribute,
    AttributeType,
    ChildRef,
    Date,
    Event,
    EventRef,
    EventType,
    Family,
    Person,
)
from gramps.gen.proxy import LivingProxyDb, PrivateProxyDb
from gramps.gen.utils import alive
from gramps.gen.utils.alive import probably_alive

from gramps_webapi.future_gramps.alive import apply_patch


def setUpModule():
    apply_patch()


def _event(db, trans, event_type, year, private=False):
    event = Event()
    event.set_type(event_type)
    date = Date()
    date.set_yr_mon_day(year, 5, 4)
    event.set_date_object(date)
    event.set_privacy(private)
    db.add_event(event, trans)
    event_ref = EventRef()
    event_ref.set_reference_handle(event.handle)
    return event_ref


class ProbablyAlivePrivacyTest(unittest.TestCase):
    """Private records must not be used through a private proxy."""

    def setUp(self):
        db = make_database("sqlite")
        db.load(":memory:")
        with DbTxn("add people", db) as trans:
            mother = Person()
            mother.set_gender(Person.FEMALE)
            mother.add_event_ref(_event(db, trans, EventType.BIRTH, 1990, True))
            mother.set_birth_ref(mother.get_event_ref_list()[0])
            attribute = Attribute()
            attribute.set_type(AttributeType.DESCRIPTION)
            attribute.set_value("private value")
            attribute.set_privacy(True)
            mother.add_attribute(attribute)
            father = Person()
            father.set_gender(Person.MALE)
            child = Person()
            dead = Person()
            dead.add_event_ref(_event(db, trans, EventType.DEATH, 1900, True))
            dead.set_death_ref(dead.get_event_ref_list()[0])
            for person in (mother, father, child, dead):
                db.add_person(person, trans)
            family = Family()
            family.set_father_handle(father.handle)
            family.set_mother_handle(mother.handle)
            child_ref = ChildRef()
            child_ref.set_reference_handle(child.handle)
            family.add_child_ref(child_ref)
            db.add_family(family, trans)
            for person in (mother, father):
                person.add_family_handle(family.handle)
            child.add_parent_family_handle(family.handle)
            for person in (mother, father, child):
                db.commit_person(person, trans)
        self.db = db
        self.mother, self.father, self.child, self.dead = mother, father, child, dead

    def tearDown(self):
        self.db.close()

    def test_base_db_uses_private_records(self):
        birth, _, _, other = alive.probably_alive_range(self.father, self.db)
        self.assertTrue(birth.is_valid())
        self.assertEqual(other.handle, self.mother.handle)
        birth, _, _, _ = alive.probably_alive_range(self.child, self.db)
        self.assertTrue(birth.is_valid())
        self.assertFalse(probably_alive(self.dead, self.db))

    def test_private_proxy_hides_private_events(self):
        proxy = PrivateProxyDb(self.db)
        for person in (self.father, self.child):
            birth, death, explain, other = alive.probably_alive_range(person, proxy)
            self.assertIsNone(birth)
            self.assertIsNone(death)
            self.assertIsNone(other)
        # imported by name, like the callers in Gramps
        self.assertTrue(probably_alive(self.dead, proxy))

    def test_private_proxy_returns_sanitized_relative(self):
        with DbTxn("add public birth", self.db) as trans:
            self.mother.add_event_ref(_event(self.db, trans, EventType.BAPTISM, 1990))
            self.db.commit_person(self.mother, trans)
        _, _, _, other = alive.probably_alive_range(self.father, self.db)
        self.assertEqual(len(other.get_attribute_list()), 1)
        proxy = PrivateProxyDb(self.db)
        _, _, _, other = alive.probably_alive_range(self.father, proxy)
        self.assertEqual(other.handle, self.mother.handle)
        self.assertEqual(other.get_attribute_list(), [])

    def test_person_from_base_db_is_sanitized(self):
        # the dead person as stored, with the reference to the private death
        dead = self.db.get_person_from_handle(self.dead.handle)
        self.assertTrue(probably_alive(dead, PrivateProxyDb(self.db)))

    def test_private_person_is_ignored(self):
        with DbTxn("make private", self.db) as trans:
            self.father.set_privacy(True)
            self.db.commit_person(self.father, trans)
        self.assertEqual(
            alive.probably_alive_range(self.father, PrivateProxyDb(self.db)),
            (None, None, "", None),
        )

    def test_living_proxy_over_private_proxy(self):
        proxy = LivingProxyDb(PrivateProxyDb(self.db), LivingProxyDb.MODE_EXCLUDE_ALL)
        self.assertTrue(probably_alive(self.dead, proxy))
        proxy = LivingProxyDb(self.db, LivingProxyDb.MODE_EXCLUDE_ALL)
        self.assertFalse(probably_alive(self.dead, proxy))

    def test_filter_rule(self):
        # born after 2003 according to the mother's private birth
        person_filter = GenericFilter()
        person_filter.add_rule(ProbablyAlive(["2000-01-01"]))
        proxy = PrivateProxyDb(self.db)
        handles = person_filter.apply(proxy, list(proxy.iter_person_handles()))
        self.assertIn(self.child.handle, handles)
        handles = person_filter.apply(self.db, list(self.db.iter_person_handles()))
        self.assertNotIn(self.child.handle, handles)

    def test_apply_patch_twice(self):
        patched = alive.probably_alive_range
        apply_patch()
        self.assertIs(alive.probably_alive_range, patched)
