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
from gramps.gen.lib import Attribute, AttributeType, Event, EventType

from gramps_webapi.api.check import check_database, rebuild_custom_type_caches

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


if __name__ == "__main__":
    unittest.main()
