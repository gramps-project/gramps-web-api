"""Tests for the `gramps_webapi.dbmanager` module."""

import os
import unittest

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
        self.assertTrue(dbmgr.is_locked())
        dbstate.db.close()
        self.assertFalse(dbmgr.is_locked())
