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

import os
import unittest
import uuid
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db.dbconst import DBBACKEND
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState

from gramps_webapi.dbmanager import WebDbManager, _backend_cache, _name_cache


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


class TestWebDbManagerCache(unittest.TestCase):
    """Tests for module-level metadata caches."""

    def setUp(self):
        self.name = "Test Cache Db"
        self.dbmgr = WebDbManager(self.name, create_if_missing=True)
        self.dbman = CLIDbManager(DbState())

    def tearDown(self):
        _name_cache.pop(self.dbmgr.path, None)
        _backend_cache.pop(self.dbmgr.path, None)
        self.dbman.remove_database(self.name)

    def test_name_cache_populated_after_init(self):
        """name.txt is cached after the first WebDbManager instantiation."""
        self.assertIn(self.dbmgr.path, _name_cache)
        self.assertEqual(_name_cache[self.dbmgr.path], self.name)

    def test_backend_cache_populated_after_init(self):
        """DBBACKEND is cached after the first WebDbManager instantiation."""
        self.assertIn(self.dbmgr.path, _backend_cache)
        self.assertEqual(_backend_cache[self.dbmgr.path][1], "sqlite")

    def test_name_cache_hit_skips_disk_read(self):
        """_get_name() returns the cached value without touching the filesystem."""
        # After the first init the cache is warm; subsequent opens must not
        # call open() on name.txt.
        with patch("builtins.open", side_effect=AssertionError("disk read")):
            # Re-construct using dirname so _get_name() is called
            dbmgr2 = WebDbManager(dirname=self.dbmgr.dirname, create_if_missing=False)
        self.assertEqual(dbmgr2.name, self.name)

    def test_backend_cache_hit_skips_disk_read(self):
        """_check_backend() uses the cached dbid without calling get_dbid_from_path."""
        target = "gramps_webapi.dbmanager.get_dbid_from_path"
        with patch(target, side_effect=AssertionError("disk read")):
            WebDbManager(dirname=self.dbmgr.dirname, create_if_missing=False)

    def test_rename_updates_name_cache(self):
        """rename_database() keeps _name_cache consistent."""
        new_name = "Test Cache Db Renamed"
        try:
            self.dbmgr.rename_database(new_name)
            self.assertEqual(_name_cache[self.dbmgr.path], new_name)
            # A fresh WebDbManager for the same dirname must not hit disk
            with patch("builtins.open", side_effect=AssertionError("disk read")):
                dbmgr2 = WebDbManager(
                    dirname=self.dbmgr.dirname, create_if_missing=False
                )
            self.assertEqual(dbmgr2.name, new_name)
        finally:
            # rename back so tearDown can clean up by original name list
            self.dbmgr.rename_database(self.name)

    def test_dbid_forwarded_to_read_file(self):
        """get_db() passes the cached dbid so DBBACKEND is not re-read."""
        open_calls = []
        real_open = open

        def tracking_open(path, *args, **kwargs):
            open_calls.append(path)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=tracking_open):
            dbstate = self.dbmgr.get_db()
            dbstate.db.close()

        dbbackend_reads = [p for p in open_calls if str(p).endswith(DBBACKEND)]
        self.assertEqual(
            len(dbbackend_reads),
            0,
            "DBBACKEND should not be read from disk when dbid is already cached",
        )

    def test_name_cache_no_entry_for_missing_or_empty(self):
        """_get_name() must not cache anything when name.txt is missing or empty."""
        import gramps_webapi.dbmanager as dbmanager_module

        fake_dirname = "nonexistent_" + uuid.uuid4().hex
        fake_dirpath = os.path.join(self.dbmgr.dbdir, fake_dirname)

        # Non-existent directory: should raise and leave no cache entry.
        self.assertFalse(os.path.isdir(fake_dirpath))
        with self.assertRaises(ValueError):
            WebDbManager(dirname=fake_dirname, create_if_missing=False)
        self.assertNotIn(fake_dirpath, dbmanager_module._name_cache)

        # Empty name.txt: should also leave no cache entry so a later write
        # is picked up on the next call.
        os.makedirs(fake_dirpath)
        try:
            open(os.path.join(fake_dirpath, "name.txt"), "w").close()
            result = self.dbmgr._get_name(fake_dirname)
            self.assertIsNone(result)
            self.assertNotIn(fake_dirpath, dbmanager_module._name_cache)
        finally:
            import shutil

            shutil.rmtree(fake_dirpath, ignore_errors=True)
