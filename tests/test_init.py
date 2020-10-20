"""Unit test package for gramps_webapi."""

import os
import unittest

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.config import get as getconfig
from gramps.gen.db.base import DbReadBase
from gramps.gen.dbstate import DbState

from . import ExampleDbInMemory, ExampleDbSQLite


class TestExampleDb(unittest.TestCase):
    """Test the example DB handlers."""

    def test_example_db_inmemory(self):
        """Test the in-memory example DB."""
        db = ExampleDbInMemory()
        self.assertIsInstance(db.load(), DbReadBase)
        db.close()

    def test_example_db_sqlite(self):
        """Test the SQLite example DB."""
        db = ExampleDbSQLite()
        db.write()
        self.assertEqual(getconfig("database.path"), db.tmp_dbdir)
        dbman = CLIDbManager(DbState())
        db_info = dbman.current_names
        # there is only one DB here
        self.assertEqual(len(db_info), 1)
        # DB name
        self.assertEqual(db_info[0][0], "example")
        # DB path
        self.assertEqual(os.path.dirname(db_info[0][1]), db.tmp_dbdir)
        db.delete()
        # just check that this is not at the tmp dir anymore
        self.assertNotEqual(getconfig("database.path"), db.tmp_dbdir)
        # ... and that the tmp dir is gone
        self.assertTrue(not os.path.exists(db.tmp_dbdir))
