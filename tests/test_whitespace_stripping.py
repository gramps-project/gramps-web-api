#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025   David Straub
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

"""Tests for whitespace stripping functionality."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Person, Note, StyledText

from gramps_webapi.api.check import strip_trailing_whitespace
from gramps_webapi.api.resources.util import fix_object_dict
from gramps_webapi.api.util import strip_whitespace_recursive


class TestStripWhitespaceRecursive(unittest.TestCase):
    """Test the strip_whitespace_recursive utility function."""

    def test_strip_simple_string(self):
        """Test stripping a simple string."""
        result = strip_whitespace_recursive("  test  ")
        self.assertEqual(result, "test")

    def test_strip_string_in_dict(self):
        """Test stripping strings in a dictionary."""
        test_dict = {"name": "John  ", "surname": "  Doe  ", "middle": "Q"}
        result = strip_whitespace_recursive(test_dict)
        self.assertEqual(result["name"], "John")
        self.assertEqual(result["surname"], "Doe")
        self.assertEqual(result["middle"], "Q")

    def test_strip_nested_dict(self):
        """Test stripping strings in nested dictionaries."""
        test_dict = {
            "person": {
                "name": "  Jane  ",
                "address": {"street": "Main St  ", "city": "  Boston"},
            }
        }
        result = strip_whitespace_recursive(test_dict)
        self.assertEqual(result["person"]["name"], "Jane")
        self.assertEqual(result["person"]["address"]["street"], "Main St")
        self.assertEqual(result["person"]["address"]["city"], "Boston")

    def test_strip_list_of_strings(self):
        """Test stripping strings in lists."""
        test_list = ["  item1  ", "item2  ", "  item3"]
        result = strip_whitespace_recursive(test_list)
        self.assertEqual(result, ["item1", "item2", "item3"])

    def test_strip_list_in_dict(self):
        """Test stripping strings in lists within dictionaries."""
        test_dict = {"names": ["  John  ", "  Jane  "], "ages": [25, 30]}
        result = strip_whitespace_recursive(test_dict)
        self.assertEqual(result["names"], ["John", "Jane"])
        self.assertEqual(result["ages"], [25, 30])

    def test_preserve_non_string_types(self):
        """Test that non-string types are preserved."""
        test_dict = {
            "string": "  test  ",
            "integer": 123,
            "float": 45.67,
            "boolean": True,
            "none": None,
            "list": [1, 2, 3],
        }
        result = strip_whitespace_recursive(test_dict)
        self.assertEqual(result["string"], "test")
        self.assertEqual(result["integer"], 123)
        self.assertEqual(result["float"], 45.67)
        self.assertEqual(result["boolean"], True)
        self.assertIsNone(result["none"])
        self.assertEqual(result["list"], [1, 2, 3])

    def test_empty_string(self):
        """Test that empty strings become empty strings."""
        result = strip_whitespace_recursive("   ")
        self.assertEqual(result, "")

    def test_empty_dict(self):
        """Test empty dictionary."""
        result = strip_whitespace_recursive({})
        self.assertEqual(result, {})

    def test_empty_list(self):
        """Test empty list."""
        result = strip_whitespace_recursive([])
        self.assertEqual(result, [])

    def test_strip_tuple(self):
        """Test that tuples are handled correctly."""
        test_tuple = ("  test  ", "  value  ", 123)
        result = strip_whitespace_recursive(test_tuple)
        self.assertEqual(result, ("test", "value", 123))
        self.assertIsInstance(result, tuple)

    def test_nested_tuple(self):
        """Test nested tuples."""
        test_data = {
            "coords": ("  10.5  ", "  20.3  "),
            "values": [("  a  ", "  b  "), ("  c  ", "  d  ")],
        }
        result = strip_whitespace_recursive(test_data)
        self.assertEqual(result["coords"], ("10.5", "20.3"))
        self.assertEqual(result["values"], [("a", "b"), ("c", "d")])


class TestFixObjectDict(unittest.TestCase):
    """Test that fix_object_dict properly strips whitespace."""

    def test_fix_object_dict_strips_whitespace(self):
        """Test that fix_object_dict strips whitespace from string values."""
        obj_dict = {
            "_class": "Note",
            "text": {"_class": "StyledText", "string": "  This is a note.  "},
            "handle": "abc123  ",
            "gramps_id": "  N0001  ",
        }
        result = fix_object_dict(obj_dict)
        self.assertEqual(result["text"]["string"], "This is a note.")
        self.assertEqual(result["handle"], "abc123")
        self.assertEqual(result["gramps_id"], "N0001")

    def test_fix_object_dict_preserves_class(self):
        """Test that _class is preserved."""
        obj_dict = {"_class": "Person", "handle": "  h123  "}
        result = fix_object_dict(obj_dict)
        self.assertEqual(result["_class"], "Person")


class TestStripTrailingWhitespaceDatabase(unittest.TestCase):
    """Test the strip_trailing_whitespace function with actual database."""

    @classmethod
    def setUpClass(cls):
        """Set up a test database."""
        cls.name = "Test Whitespace DB"
        cls.dbstate = DbState()
        cls.dbman = CLIDbManager(cls.dbstate)
        cls.dbpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.db = make_database("sqlite")
        cls.db.load(cls.dbpath)

    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        cls.db.close()
        cls.dbman.remove_database(cls.name)

    def test_strip_whitespace_from_person(self):
        """Test stripping whitespace from person objects."""
        # Create a person with trailing whitespace
        person = Person()
        person.set_gramps_id("I0001")
        name = person.get_primary_name()
        name.set_first_name("John  ")  # trailing spaces
        name.get_primary_surname().set_surname("  Doe  ")  # leading and trailing

        with DbTxn("Add person", self.db) as trans:
            self.db.add_person(person, trans)

        # Run the whitespace stripping
        progress_callback = MagicMock()
        fixes = strip_trailing_whitespace(self.db, progress_callback)

        # Verify the person was fixed
        self.assertGreaterEqual(fixes, 1)

        # Retrieve and check the person
        person_check = self.db.get_person_from_gramps_id("I0001")
        name_check = person_check.get_primary_name()
        self.assertEqual(name_check.get_first_name(), "John")
        self.assertEqual(name_check.get_surname(), "Doe")

        # Progress callback should have been called
        progress_callback.assert_called()

    def test_strip_whitespace_from_note(self):
        """Test stripping whitespace from note objects."""
        # Create a note with trailing whitespace
        note = Note()
        note.set_gramps_id("N0001")
        styled_text = StyledText()
        styled_text.string = "This is a test note.  "  # trailing spaces
        note.set_styledtext(styled_text)

        with DbTxn("Add note", self.db) as trans:
            self.db.add_note(note, trans)

        # Run the whitespace stripping
        fixes = strip_trailing_whitespace(self.db, None)

        # Verify the note was fixed
        self.assertGreaterEqual(fixes, 1)

        # Retrieve and check the note
        note_check = self.db.get_note_from_gramps_id("N0001")
        self.assertEqual(note_check.get_styledtext().string, "This is a test note.")

    def test_no_changes_needed(self):
        """Test that objects without trailing whitespace are not modified."""
        # Create a person without trailing whitespace
        person = Person()
        person.set_gramps_id("I0002")
        name = person.get_primary_name()
        name.set_first_name("Jane")
        name.get_primary_surname().set_surname("Smith")

        with DbTxn("Add person", self.db) as trans:
            self.db.add_person(person, trans)

        # Get initial change time
        person_before = self.db.get_person_from_gramps_id("I0002")
        change_time_before = person_before.get_change_time()

        # Run the whitespace stripping
        fixes = strip_trailing_whitespace(self.db, None)

        # This person should not be counted in fixes since it had no trailing whitespace
        person_after = self.db.get_person_from_gramps_id("I0002")

        # Name should remain unchanged
        name_after = person_after.get_primary_name()
        self.assertEqual(name_after.get_first_name(), "Jane")
        self.assertEqual(name_after.get_surname(), "Smith")

    def test_empty_database(self):
        """Test running on an empty database doesn't crash."""
        # Create a new empty database
        empty_name = "Empty Test DB"
        empty_dbpath, _ = self.dbman.create_new_db_cli(empty_name, dbid="sqlite")
        empty_db = make_database("sqlite")
        empty_db.load(empty_dbpath)

        try:
            # Should not crash and return 0 fixes
            fixes = strip_trailing_whitespace(empty_db, None)
            self.assertEqual(fixes, 0)
        finally:
            empty_db.close()
            self.dbman.remove_database(empty_name)


if __name__ == "__main__":
    unittest.main()
