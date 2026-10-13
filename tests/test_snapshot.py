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

"""Tests for consistent snapshots of SQLite databases."""

import gzip
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Family, Person, Researcher
from gramps.gen.user import User
from gramps.plugins.export.exportxml import export_data

from gramps_webapi.api.snapshot import consistent_read
from gramps_webapi.api.util import ModifiedPrivateProxyDb
from gramps_webapi.dbmanager import WebDbManager

XML_NAMESPACE = "{http://gramps-project.org/xml/1.7.2/}"


def _add_person(db, handle: str, private: bool = False) -> None:
    with DbTxn("add person", db) as trans:
        person = Person()
        person.set_handle(handle)
        person.set_gramps_id(handle)
        person.set_privacy(private)
        db.add_person(person, trans)


def _add_person_with_family(db, person_handle: str, family_handle: str) -> None:
    """Add a person and a family referencing them, as one transaction."""
    with DbTxn("add family", db) as trans:
        person = Person()
        person.set_handle(person_handle)
        person.set_gramps_id(person_handle)
        db.add_person(person, trans)
        family = Family()
        family.set_handle(family_handle)
        family.set_gramps_id(family_handle)
        family.set_father_handle(person_handle)
        db.add_family(family, trans)


def _write_after_call(db: DbReadBase, method: str, write) -> None:
    """Make `db.<method>` run `write` right after its first call returns."""
    original = getattr(db, method)
    done = []

    def wrapper(*args, **kwargs):
        result = original(*args, **kwargs)
        if not done:
            done.append(True)
            write()
        return result

    setattr(db, method, wrapper)


def _exported_references(path: str) -> tuple[set[str], set[str]]:
    """Return the person handles in an exported XML file and the persons its
    families reference."""
    with gzip.open(path) as f:
        root = ET.parse(f).getroot()
    # Gramps XML prefixes handles with an underscore
    people = {
        el.get("handle").lstrip("_") for el in root.iter(f"{XML_NAMESPACE}person")
    }
    fathers = {
        el.get("hlink").lstrip("_") for el in root.iter(f"{XML_NAMESPACE}father")
    }
    return people, fathers


class TestConsistentReadSQLite(unittest.TestCase):
    """A snapshot doesn't see writes that happen after it was taken."""

    def setUp(self):
        self.name = "Test Snapshot"
        self.dbman = CLIDbManager(DbState())
        self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.dbmgr = WebDbManager(self.name)
        self.writer = self.dbmgr.get_db(readonly=False).db
        _add_person(self.writer, "P0001")
        _add_person(self.writer, "P0002", private=True)
        self.reader = self.dbmgr.get_db().db

    def tearDown(self):
        self.reader.close()
        self.writer.close()
        self.dbman.remove_database(self.name)

    def test_snapshot_does_not_see_later_writes(self):
        with consistent_read(self.reader) as snapshot_db:
            self.assertIsNot(snapshot_db, self.reader)
            _add_person(self.writer, "P0003")
            self.assertEqual(set(snapshot_db.get_person_handles()), {"P0001", "P0002"})
        self.assertEqual(
            set(self.reader.get_person_handles()), {"P0001", "P0002", "P0003"}
        )

    def test_snapshot_keeps_metadata(self):
        researcher = Researcher()
        researcher.set_name("Jane Doe")
        self.writer.set_researcher(researcher)
        self.writer.close()
        self.writer = self.dbmgr.get_db(readonly=False).db
        self.reader.close()
        self.reader = self.dbmgr.get_db().db
        with consistent_read(self.reader) as snapshot_db:
            self.assertEqual(snapshot_db.get_researcher().get_name(), "Jane Doe")

    def test_snapshot_copy_is_deleted(self):
        with consistent_read(self.reader) as snapshot_db:
            directory = snapshot_db.get_save_path()
            self.assertTrue(os.path.isdir(directory))
        self.assertFalse(os.path.exists(directory))

    def test_private_proxy_is_preserved(self):
        proxy = ModifiedPrivateProxyDb(self.reader)
        with consistent_read(proxy) as snapshot_db:
            self.assertIsInstance(snapshot_db, ModifiedPrivateProxyDb)
            self.assertIsNot(snapshot_db.db, self.reader)
            _add_person(self.writer, "P0003")
            self.assertEqual(set(snapshot_db.get_person_handles()), {"P0001"})


class TestExportDuringWrite(unittest.TestCase):
    """An export must not contain references to objects it doesn't include."""

    def setUp(self):
        self.name = "Test Export During Write"
        self.dbman = CLIDbManager(DbState())
        self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.dbmgr = WebDbManager(self.name)
        self.writer = self.dbmgr.get_db(readonly=False).db
        # the exporter skips object types that are empty when it starts
        _add_person_with_family(self.writer, "P0001", "F0001")
        self.reader = self.dbmgr.get_db().db
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "export.gramps")

    def tearDown(self):
        self.reader.close()
        self.writer.close()
        self.dbman.remove_database(self.name)
        self.tmpdir.cleanup()

    def _write(self):
        # people are already listed, families are exported next
        _add_person_with_family(self.writer, "P0002", "F0002")

    def test_without_snapshot_reference_is_dangling(self):
        """Documents the problem the snapshot solves."""
        _write_after_call(self.reader, "get_person_handles", self._write)
        self.assertTrue(export_data(self.reader, self.path, User()))
        people, fathers = _exported_references(self.path)
        self.assertEqual(people, {"P0001"})
        self.assertEqual(fathers, {"P0001", "P0002"})

    def test_with_snapshot_references_are_complete(self):
        with consistent_read(self.reader) as snapshot_db:
            _write_after_call(snapshot_db, "get_person_handles", self._write)
            self.assertTrue(export_data(snapshot_db, self.path, User()))
        people, fathers = _exported_references(self.path)
        self.assertEqual(people, {"P0001"})
        self.assertEqual(fathers, {"P0001"})
