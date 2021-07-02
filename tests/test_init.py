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

"""Unit test package for gramps_webapi."""

import os
import shutil
import tempfile
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
        test_grampshome = tempfile.mkdtemp()
        os.environ["GRAMPSHOME"] = test_grampshome
        db = ExampleDbSQLite()
        self.assertEqual(getconfig("database.path"), db.db_path)
        dbman = CLIDbManager(DbState())
        db_info = dbman.current_names
        # there is only one DB here
        self.assertEqual(len(db_info), 1)
        # DB name
        self.assertEqual(db_info[0][0], "example")
        # DB path
        self.assertEqual(os.path.dirname(db_info[0][1]), db.db_path)
        # DB cleanup
        shutil.rmtree(test_grampshome)
        self.assertTrue(not os.path.exists(test_grampshome))
