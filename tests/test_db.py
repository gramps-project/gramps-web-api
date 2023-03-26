#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Tests for the `gramps_webapi.dbmanager` module."""

import unittest
import uuid

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState

from gramps_webapi.dbmanager import WebDbManager


class TestWebDbManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web Db Manager"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.db = make_database("sqlite")

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_lock(self):
        """Test if db is locked while open."""
        dbmgr = WebDbManager(self.name)
        self.assertFalse(dbmgr.is_locked())
        dbstate = dbmgr.get_db()
        self.assertFalse(dbmgr.is_locked())
        dbstate.db.close()
        self.assertFalse(dbmgr.is_locked())
        dbstate = dbmgr.get_db()
        self.assertFalse(dbmgr.is_locked())
        dbstate.db.close()
        self.assertFalse(dbmgr.is_locked())


class TestWebDbManagerCreate(unittest.TestCase):
    def test_create(self):
        name = "Test Web Db Manager 2"
        dbmgr = WebDbManager(name, create_if_missing=True)
        dbstate = DbState()
        assert dbmgr.path
        assert dbmgr.name == name
        assert dbmgr.dirname
        dbman = CLIDbManager(dbstate)
        # assert dirname is valid UUIDv4
        uuid.UUID(dbmgr.dirname, version=4)
        dbman.remove_database(name)

    def test_create_dirname(self):
        name = "Test Web Db Manager 3"
        dbmgr = WebDbManager(dirname="my_dirname", name=name, create_if_missing=True)
        dbstate = DbState()
        assert dbmgr.path
        assert dbmgr.name == name
        assert dbmgr.dirname == "my_dirname"
        dbman = CLIDbManager(dbstate)
        dbman.remove_database(name)

    def test_dont_create(self):
        name = "Test Web Db Manager 4"
        with self.assertRaises(ValueError):
            dbmgr = WebDbManager(name, create_if_missing=False)

    def test_dont_create_dirname(self):
        name = "Test Web Db Manager 5"
        with self.assertRaises(ValueError):
            dbmgr = WebDbManager(dirname="my_dirname_2", create_if_missing=False)
