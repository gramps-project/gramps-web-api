#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024 David Straub
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Unit tests for `gramps_webapi.undodb.DbUndoSQL`."""

import pickle
import shutil
import tempfile
import time
import unittest

from gramps.gen.lib.json_utils import (
    object_to_dict,
    string_to_dict,
)
from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.db.utils import make_database
from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
    Tag,
)
from sqlalchemy import text

from gramps_webapi.undodb import DbUndoSQL


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class TestUndoHistory(unittest.TestCase):
    """Tests Undo History Addon."""

    @classmethod
    def setUpClass(cls) -> None:
        pass

    def setUp(self) -> None:
        self.dbdir = tempfile.mkdtemp()
        self.db: DbWriteBase = make_database("sqlite")

        def create_undo_manager():
            path = self.db.undolog
            return DbUndoSQL(grampsdb=self.db, dburl=f"sqlite:///{path}")

        self.db._create_undo_manager = create_undo_manager
        self.db.load(self.dbdir)

        with DbTxn("Add test objects", self.db) as trans:
            for i in range(10):
                self.__add_object(Person, self.db.add_person, trans)
                self.__add_object(Family, self.db.add_family, trans)
                self.__add_object(Event, self.db.add_event, trans)
                self.__add_object(Place, self.db.add_place, trans)
                self.__add_object(Repository, self.db.add_repository, trans)
                self.__add_object(Source, self.db.add_source, trans)
                self.__add_object(Citation, self.db.add_citation, trans)
                self.__add_object(Media, self.db.add_media, trans)
                self.__add_object(Note, self.db.add_note, trans)
                self.__add_object(Tag, self.db.add_tag, trans)

    @classmethod
    def tearDownClass(cls):
        pass

    def tearDown(self):
        shutil.rmtree(self.dbdir)

    def __add_object(self, obj_class, add_func, trans):
        """Add an object."""
        obj = obj_class()
        add_func(obj, trans)

    def _get_history_table(self, table_name):
        """Get a table from the history database."""
        dbundo = self.db.get_undodb()
        with dbundo.session_scope() as session:
            res = session.execute(text(f"SELECT * FROM {table_name}"))
            return res.mappings().all()

    def test_initial_sate(self):
        assert self.db.get_number_of_people() == 10
        connections = self._get_history_table("connections")
        assert len(connections) == 1
        assert connections[0]["id"] == 1
        assert connections[0]["tree_id"] is None
        assert time.time() - connections[0]["timestamp"] / 1e9 < 10
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 1
        assert transactions[0]["connection_id"] == 1
        assert transactions[0]["id"] == 1
        assert transactions[0]["description"] == "Add test objects"
        assert transactions[0]["timestamp"] - connections[0]["timestamp"] < 10e9
        assert transactions[0]["undo"] == 0
        changes = self._get_history_table("changes")
        assert len(changes) == 100
        for commit in changes:
            assert commit["connection_id"] == 1
            assert commit["trans_type"] == 0  # add
            assert commit["timestamp"] < transactions[0]["timestamp"]
        assert len([com for com in changes if com["obj_class"] == "Person"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Family"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Event"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Place"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Repository"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Source"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Citation"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Media"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Note"]) == 10
        assert len([com for com in changes if com["obj_class"] == "Tag"]) == 10

    def test_undo_redo_initial_state(self):
        assert self.db.get_number_of_people() == 10
        self.db.undo()
        connections = self._get_history_table("connections")
        assert len(connections) == 1
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 2
        assert transactions[1]["description"] == "_Undo Add test objects"
        changes = self._get_history_table("changes")
        assert len(changes) == 100
        assert self.db.get_number_of_people() == 0
        self.db.redo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 3
        assert transactions[1]["description"] == "_Undo Add test objects"
        assert transactions[2]["description"] == "_Redo Add test objects"
        changes = self._get_history_table("changes")
        assert len(changes) == 100
        assert self.db.get_number_of_people() == 10

    def test_undo_redo_delete(self):
        person: Person = next(self.db.iter_people())
        with DbTxn("Delete person", self.db) as trans:
            self.db.delete_person_from_database(person, trans)
        assert self.db.get_number_of_people() == 9
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 2
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        self.db.undo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 3
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        assert self.db.get_number_of_people() == 10
        self.db.redo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 4
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        assert self.db.get_number_of_people() == 9
        commit = changes[-1]
        assert commit["id"] == 101
        assert commit["obj_class"] == "Person"
        assert commit["trans_type"] == 2  # delete
        assert commit["obj_handle"] == person.handle
        assert commit["ref_handle"] is None
        assert commit["new_json"] is None
        assert string_to_dict(commit["old_json"]) == object_to_dict(person)

    def test_undo_redo_modify(self):
        person: Person = next(self.db.iter_people())
        old_person: Person = next(self.db.iter_people())
        alpha_em = "1/137.036"
        person.gramps_id = alpha_em
        with DbTxn("Modify person", self.db) as trans:
            self.db.commit_person(person, trans)
        assert self.db.get_number_of_people() == 10
        new_person = self.db.get_person_from_gramps_id(alpha_em)
        assert new_person.handle == person.handle
        assert new_person.change != old_person.handle
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 2
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        self.db.undo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 3
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        assert self.db.get_number_of_people() == 10
        self.db.redo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 4
        changes = self._get_history_table("changes")
        assert len(changes) == 101
        assert self.db.get_number_of_people() == 10
        commit = changes[-1]
        assert commit["id"] == 101
        assert commit["obj_class"] == "Person"
        assert commit["trans_type"] == 1  # modify
        assert commit["obj_handle"] == person.handle
        assert commit["ref_handle"] is None
        assert string_to_dict(commit["new_json"]) == object_to_dict(person)
        assert string_to_dict(commit["new_json"]) == object_to_dict(new_person)
        assert string_to_dict(commit["old_json"]) == object_to_dict(old_person)


class TestMigrate(unittest.TestCase):
    """Tests for the migrate() function (pre-v3.0 → v3.0 undo DB migration)."""

    def setUp(self):
        self.dbdir = tempfile.mkdtemp()
        self.db: DbWriteBase = make_database("sqlite")

        def create_undo_manager():
            path = self.db.undolog
            return DbUndoSQL(grampsdb=self.db, dburl=f"sqlite:///{path}")

        self.db._create_undo_manager = create_undo_manager
        self.db.load(self.dbdir)

        with DbTxn("Add test person", self.db) as trans:
            person = Person()
            self.db.add_person(person, trans)
            self.person_handle = person.handle

    def tearDown(self):
        self.db.close(update=False)
        shutil.rmtree(self.dbdir)

    def _get_undodb(self) -> DbUndoSQL:
        return self.db.get_undodb()

    def _drop_json_columns(self):
        """Simulate a pre-v3.0 database by dropping the JSON columns."""
        undodb = self._get_undodb()
        with undodb.session_scope() as session:
            session.execute(text("ALTER TABLE changes DROP COLUMN old_json"))
            session.execute(text("ALTER TABLE changes DROP COLUMN new_json"))

    def _null_json_set_blobs(self):
        """Simulate pre-v3.0 rows: clear JSON columns and write blob data instead."""
        person = self.db.get_person_from_handle(self.person_handle)
        blob = pickle.dumps(person.serialize(), protocol=1)
        undodb = self._get_undodb()
        with undodb.session_scope() as session:
            session.execute(
                text(
                    "UPDATE changes SET old_json = NULL, new_json = NULL,"
                    " new_data = :blob"
                ),
                {"blob": blob},
            )

    def test_migrate_adds_missing_columns(self):
        """migrate() adds old_json/new_json when they are absent (pre-v3.0 DB)."""
        from gramps_webapi.undodb import migrate
        from sqlalchemy import inspect as sa_inspect

        self._drop_json_columns()
        undodb = self._get_undodb()

        cols_before = {
            col["name"]
            for col in sa_inspect(undodb.engine).get_columns("changes")
        }
        self.assertNotIn("old_json", cols_before)
        self.assertNotIn("new_json", cols_before)

        migrate(undodb)

        cols_after = {
            col["name"]
            for col in sa_inspect(undodb.engine).get_columns("changes")
        }
        self.assertIn("old_json", cols_after)
        self.assertIn("new_json", cols_after)

    def test_migrate_backfills_blob_data(self):
        """migrate() fills old_json/new_json from blob columns for pre-v3.0 rows."""
        from gramps_webapi.undodb import migrate

        self._null_json_set_blobs()
        undodb = self._get_undodb()

        with undodb.session_scope() as session:
            nulls: int = session.execute(
                text("SELECT COUNT(*) FROM changes WHERE new_json IS NULL")
            ).scalar() or 0
        self.assertGreater(nulls, 0)

        migrate(undodb)

        with undodb.session_scope() as session:
            nulls_after = session.execute(
                text("SELECT COUNT(*) FROM changes WHERE new_json IS NULL")
            ).scalar()
        self.assertEqual(nulls_after, 0)

    def test_migrate_idempotent(self):
        """Calling migrate() twice does not raise and does not corrupt data."""
        from gramps_webapi.undodb import migrate

        migrate(self._get_undodb())
        migrate(self._get_undodb())  # second call must not crash

        undodb = self._get_undodb()
        with undodb.session_scope() as session:
            count: int = session.execute(
                text("SELECT COUNT(*) FROM changes")
            ).scalar() or 0
        self.assertGreater(count, 0)

    def test_migrate_noop_when_current(self):
        """migrate() on an already-current DB (all JSON populated) is a no-op."""
        from gramps_webapi.undodb import migrate

        undodb = self._get_undodb()

        with undodb.session_scope() as session:
            rows_before = session.execute(
                text("SELECT id, new_json FROM changes ORDER BY id")
            ).fetchall()

        migrate(undodb)

        with undodb.session_scope() as session:
            rows_after = session.execute(
                text("SELECT id, new_json FROM changes ORDER BY id")
            ).fetchall()

        self.assertEqual(rows_before, rows_after)
