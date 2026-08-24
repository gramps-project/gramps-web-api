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

"""Unit tests for `gramps_webapi.api.check`."""

import unittest

from gramps.gen.db import DbTxn
from gramps.gen.lib import (
    Attribute,
    AttributeType,
    Event,
    EventRef,
    EventType,
    MediaRef,
    Person,
)

from gramps_webapi.api.check import (
    check_database,
    rebuild_custom_type_caches,
    strip_empty_refs,
)

from . import ExampleDbInMemory


class TestRebuildCustomTypeCaches(unittest.TestCase):
    """Tests for custom type cache rebuilding."""

    @classmethod
    def setUpClass(cls):
        cls.exampledb = ExampleDbInMemory()
        cls.db = cls.exampledb.load()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.exampledb.close()

    def test_stale_custom_event_type_removed(self):
        with DbTxn("add event", self.db) as trans:
            event = Event()
            event_type = EventType()
            event_type.set((EventType.CUSTOM, "StaleCustomEventXYZ"))
            event.set_type(event_type)
            self.db.add_event(event, trans)
            handle = event.handle

        self.assertIn("StaleCustomEventXYZ", self.db.get_event_types())

        with DbTxn("remove event", self.db) as trans:
            self.db.remove_event(handle, trans)

        # cache is append-only: still stale right after the record is gone
        self.assertIn("StaleCustomEventXYZ", self.db.get_event_types())

        removed = rebuild_custom_type_caches(self.db)

        self.assertIn(("event_names", "StaleCustomEventXYZ"), removed)
        self.assertNotIn("StaleCustomEventXYZ", self.db.get_event_types())

    def test_in_use_custom_type_not_removed(self):
        with DbTxn("add event", self.db) as trans:
            event = Event()
            event_type = EventType()
            event_type.set((EventType.CUSTOM, "ActiveCustomEventXYZ"))
            event.set_type(event_type)
            self.db.add_event(event, trans)

        rebuild_custom_type_caches(self.db)

        self.assertIn("ActiveCustomEventXYZ", self.db.get_event_types())

    def test_stale_custom_attribute_type_removed(self):
        with DbTxn("add event", self.db) as trans:
            event = Event()
            attribute = Attribute()
            attribute_type = AttributeType()
            attribute_type.set((AttributeType.CUSTOM, "StaleCustomAttrXYZ"))
            attribute.set_type(attribute_type)
            event.add_attribute(attribute)
            self.db.add_event(event, trans)
            handle = event.handle

        self.assertIn("StaleCustomAttrXYZ", self.db.get_event_attribute_types())

        with DbTxn("remove event", self.db) as trans:
            self.db.remove_event(handle, trans)

        removed = rebuild_custom_type_caches(self.db)

        self.assertIn(("event_attributes", "StaleCustomAttrXYZ"), removed)
        self.assertNotIn("StaleCustomAttrXYZ", self.db.get_event_attribute_types())


class TestCheckDatabase(unittest.TestCase):
    """Tests for check_database, including type cache cleanup."""

    @classmethod
    def setUpClass(cls):
        cls.exampledb = ExampleDbInMemory()
        cls.db = cls.exampledb.load()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.exampledb.close()

    def test_reports_removed_custom_types(self):
        with DbTxn("add event", self.db) as trans:
            event = Event()
            event_type = EventType()
            event_type.set((EventType.CUSTOM, "StaleViaCheckXYZ"))
            event.set_type(event_type)
            self.db.add_event(event, trans)
            handle = event.handle

        with DbTxn("remove event", self.db) as trans:
            self.db.remove_event(handle, trans)

        result = check_database(self.db)

        self.assertGreaterEqual(result["num_errors"], 1)
        self.assertIn("unused custom type value", result["message"])
        self.assertNotIn("StaleViaCheckXYZ", self.db.get_event_types())


class TestStripEmptyRefs(unittest.TestCase):
    """Tests for removing references without a target.

    See https://github.com/gramps-project/gramps-web-api/issues/479 - such
    references are invisible to Gramps' own check tool and break the XML export.
    """

    def setUp(self):
        self.exampledb = ExampleDbInMemory()
        self.db = self.exampledb.load()

    def tearDown(self):
        self.db.close()
        self.exampledb.close()

    def _add_person(self, person):
        with DbTxn("add person", self.db) as trans:
            self.db.add_person(person, trans)
        return person.handle

    def test_empty_media_ref_removed(self):
        person = Person()
        person.add_media_reference(MediaRef())  # ref defaults to None
        handle = self._add_person(person)

        with DbTxn("strip", self.db) as trans:
            repaired = strip_empty_refs(self.db, trans)

        self.assertIn(("person", person.gramps_id), repaired)
        self.assertEqual(self.db.get_person_from_handle(handle).media_list, [])

    def test_valid_media_ref_kept(self):
        media_handle = next(self.db.iter_media_handles())
        person = Person()
        media_ref = MediaRef()
        media_ref.set_reference_handle(media_handle)
        person.add_media_reference(media_ref)
        handle = self._add_person(person)

        with DbTxn("strip", self.db) as trans:
            repaired = strip_empty_refs(self.db, trans)

        self.assertEqual(repaired, [])
        kept = self.db.get_person_from_handle(handle).media_list
        self.assertEqual([ref.ref for ref in kept], [media_handle])

    def test_birth_ref_index_survives_stripping(self):
        event_handle = next(self.db.iter_event_handles())
        person = Person()
        person.add_event_ref(EventRef())  # empty ref, sits before the birth ref
        birth_ref = EventRef()
        birth_ref.set_reference_handle(event_handle)
        person.add_event_ref(birth_ref)
        person.set_birth_ref(birth_ref)
        self.assertEqual(person.birth_ref_index, 1)
        handle = self._add_person(person)

        with DbTxn("strip", self.db) as trans:
            strip_empty_refs(self.db, trans)

        person = self.db.get_person_from_handle(handle)
        self.assertEqual([ref.ref for ref in person.event_ref_list], [event_handle])
        self.assertEqual(person.birth_ref_index, 0)
        self.assertEqual(person.get_birth_ref().ref, event_handle)

    def test_empty_birth_ref_is_unset(self):
        person = Person()
        birth_ref = EventRef()  # empty ref that is also the birth reference
        person.add_event_ref(birth_ref)
        person.set_birth_ref(birth_ref)
        handle = self._add_person(person)

        with DbTxn("strip", self.db) as trans:
            strip_empty_refs(self.db, trans)

        person = self.db.get_person_from_handle(handle)
        self.assertEqual(person.event_ref_list, [])
        self.assertEqual(person.birth_ref_index, -1)
        self.assertIsNone(person.get_birth_ref())

    def test_check_database_reports_and_repairs(self):
        person = Person()
        person.add_media_reference(MediaRef())
        handle = self._add_person(person)

        result = check_database(self.db)

        self.assertGreaterEqual(result["num_errors"], 1)
        self.assertIn("references without a target", result["message"])
        self.assertEqual(self.db.get_person_from_handle(handle).media_list, [])


if __name__ == "__main__":
    unittest.main()
