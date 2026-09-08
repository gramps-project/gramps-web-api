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
from unittest.mock import patch

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

from gramps_webapi.undodb import DbUndoSQL, DbUndoSQLWeb


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


class TestGetTransactions(unittest.TestCase):
    """Tests for the transaction history queries of `DbUndoSQLWeb`."""

    def setUp(self):
        self.dbdir = tempfile.mkdtemp()
        self.db: DbWriteBase = make_database("sqlite")

        def create_undo_manager():
            path = self.db.undolog
            return DbUndoSQLWeb(grampsdb=self.db, dburl=f"sqlite:///{path}", tree_id=1)

        self.db._create_undo_manager = create_undo_manager
        self.db.load(self.dbdir)

        # separate transactions, all within the same connection
        for description, obj_class, add_func in [
            ("Add person", Person, self.db.add_person),
            ("Add note", Note, self.db.add_note),
            ("Add place", Place, self.db.add_place),
        ]:
            with DbTxn(description, self.db) as trans:
                add_func(obj_class(), trans)

    def tearDown(self):
        self.db.close(update=False)
        shutil.rmtree(self.dbdir)

    def test_changes_of_shared_connection(self):
        undodb = self.db.get_undodb()
        transactions, count = undodb.get_transactions()
        assert count == 3
        assert {transaction["connection"]["id"] for transaction in transactions} == {1}
        assert [transaction["description"] for transaction in transactions] == [
            "Add person",
            "Add note",
            "Add place",
        ]
        for transaction, obj_class in zip(transactions, ["Person", "Note", "Place"]):
            assert [change["obj_class"] for change in transaction["changes"]] == [
                obj_class
            ]

    def test_get_transaction(self):
        undodb = self.db.get_undodb()
        transaction = undodb.get_transaction(2)
        assert transaction["description"] == "Add note"
        assert [change["obj_class"] for change in transaction["changes"]] == ["Note"]
        assert undodb.get_transaction(99) is None

    def test_changes_of_chunked_transactions(self):
        undodb = self.db.get_undodb()
        with patch("gramps_webapi.undodb.CHANGES_QUERY_CHUNK_SIZE", 2):
            transactions, _ = undodb.get_transactions()
        assert [
            change["obj_class"]
            for transaction in transactions
            for change in transaction["changes"]
        ] == ["Person", "Note", "Place"]

    def test_transactions_state(self):
        undodb = self.db.get_undodb()
        assert undodb.get_transactions_state() == (3, 3)
        with DbTxn("Add another person", self.db) as trans:
            self.db.add_person(Person(), trans)
        assert undodb.get_transactions_state() == (4, 4)

    def test_data_only_included_on_demand(self):
        undodb = self.db.get_undodb()
        transactions, _ = undodb.get_transactions(old_data=False, new_data=False)
        change = transactions[0]["changes"][0]
        assert "old_data" not in change
        assert "new_data" not in change
        transactions, _ = undodb.get_transactions(old_data=True, new_data=True)
        change = transactions[0]["changes"][0]
        assert change["old_data"] == {}
        assert change["new_data"]["_class"] == "Person"


class TestGetObjectChanges(unittest.TestCase):
    """Tests for the object-scoped change history queries of `DbUndoSQLWeb`."""

    def setUp(self):
        self.dbdir = tempfile.mkdtemp()
        self.db: DbWriteBase = make_database("sqlite")

        def create_undo_manager():
            path = self.db.undolog
            return DbUndoSQLWeb(grampsdb=self.db, dburl=f"sqlite:///{path}", tree_id=1)

        self.db._create_undo_manager = create_undo_manager
        self.db.load(self.dbdir)

        with DbTxn("Add person and note", self.db) as trans:
            person = Person()
            self.db.add_person(person, trans)
            note = Note()
            self.db.add_note(note, trans)
        self.person_handle = person.handle
        self.note_handle = note.handle

        person.gramps_id = "modified"
        with DbTxn("Modify person", self.db) as trans:
            self.db.commit_person(person, trans)

    def tearDown(self):
        self.db.close(update=False)
        shutil.rmtree(self.dbdir)

    def test_returns_only_this_object_changes(self):
        undodb = self.db.get_undodb()
        changes, count = undodb.get_object_changes("Person", self.person_handle)
        assert count == 2
        assert [change["trans_type"] for change in changes] == [0, 1]  # add, modify
        assert all(change["obj_handle"] == self.person_handle for change in changes)
        assert all(change["obj_class"] == "Person" for change in changes)

    def test_excludes_sibling_changes_from_same_transaction(self):
        undodb = self.db.get_undodb()
        changes, count = undodb.get_object_changes("Note", self.note_handle)
        assert count == 1
        assert changes[0]["obj_handle"] == self.note_handle

    def test_unknown_handle_returns_empty(self):
        undodb = self.db.get_undodb()
        changes, count = undodb.get_object_changes("Person", "nonexistent")
        assert changes == []
        assert count == 0

    def test_transaction_id_matches_covering_transaction(self):
        undodb = self.db.get_undodb()
        changes, _ = undodb.get_object_changes("Person", self.person_handle)
        transactions, _ = undodb.get_transactions()
        transactions_by_id = {
            transaction["id"]: transaction for transaction in transactions
        }
        for change in changes:
            assert change["transaction_id"] is not None
            transaction = transactions_by_id[change["transaction_id"]]
            transaction_change_handles = {
                c["obj_handle"] for c in transaction["changes"]
            }
            assert change["obj_handle"] in transaction_change_handles

    def test_transaction_id_stable_when_ranges_absent(self):
        """Range-less transactions all cover the connection; the lowest id wins.

        Without a deterministic order the resolved id would depend on the
        query plan, and the endpoint's ETag would not notice it changing.
        """
        undodb = self.db.get_undodb()
        with undodb.session_scope() as session:
            session.execute(text("UPDATE transactions SET first = NULL, last = NULL"))
            session.execute(
                text(
                    "INSERT INTO transactions"
                    " (id, connection_id, description, first, last, undo, timestamp)"
                    " SELECT 900 + id, connection_id, 'empty', NULL, NULL, 0, timestamp"
                    " FROM transactions"
                )
            )
            session.commit()
            lowest_id = session.execute(
                text("SELECT MIN(id) FROM transactions")
            ).scalar()

        changes, _ = undodb.get_object_changes("Person", self.person_handle)
        assert changes
        assert [change["transaction_id"] for change in changes] == [lowest_id] * len(
            changes
        )

    def test_state(self):
        undodb = self.db.get_undodb()
        max_ts, count = undodb.get_object_changes_state("Person", self.person_handle)
        assert count == 2
        assert isinstance(max_ts, int)
        with DbTxn("Modify person again", self.db) as trans:
            person = self.db.get_person_from_handle(self.person_handle)
            person.gramps_id = "modified again"
            self.db.commit_person(person, trans)
        new_max_ts, new_count = undodb.get_object_changes_state(
            "Person", self.person_handle
        )
        assert new_count == 3
        assert new_max_ts >= max_ts

    def test_data_only_included_on_demand(self):
        undodb = self.db.get_undodb()
        changes, _ = undodb.get_object_changes(
            "Person", self.person_handle, old_data=False, new_data=False
        )
        assert "old_data" not in changes[0]
        assert "new_data" not in changes[0]
        changes, _ = undodb.get_object_changes(
            "Person", self.person_handle, old_data=True, new_data=True
        )
        assert changes[1]["old_data"]["gramps_id"] != "modified"
        assert changes[1]["new_data"]["gramps_id"] == "modified"

    def test_pagination_and_descending(self):
        undodb = self.db.get_undodb()
        changes, count = undodb.get_object_changes(
            "Person", self.person_handle, page=1, pagesize=1
        )
        assert count == 2
        assert len(changes) == 1
        assert changes[0]["trans_type"] == 0  # add, ascending default
        changes, _ = undodb.get_object_changes(
            "Person", self.person_handle, ascending=False
        )
        assert [change["trans_type"] for change in changes] == [1, 0]

    def test_connection_included(self):
        undodb = self.db.get_undodb()
        changes, _ = undodb.get_object_changes("Person", self.person_handle)
        assert changes[0]["connection"]["id"] == 1

    def test_before_after_zero_is_a_real_cursor_not_unset(self):
        """`before=0`/`after=0` must filter, not be treated as 'no filter'."""
        undodb = self.db.get_undodb()
        changes, count = undodb.get_object_changes(
            "Person", self.person_handle, before=0
        )
        assert changes == []
        assert count == 0

        changes, count = undodb.get_object_changes(
            "Person", self.person_handle, after=0
        )
        assert count == 2


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
            col["name"] for col in sa_inspect(undodb.engine).get_columns("changes")
        }
        self.assertNotIn("old_json", cols_before)
        self.assertNotIn("new_json", cols_before)

        migrate(undodb)

        cols_after = {
            col["name"] for col in sa_inspect(undodb.engine).get_columns("changes")
        }
        self.assertIn("old_json", cols_after)
        self.assertIn("new_json", cols_after)

    def test_migrate_backfills_blob_data(self):
        """migrate() fills old_json/new_json from blob columns for pre-v3.0 rows."""
        from gramps_webapi.undodb import migrate

        self._null_json_set_blobs()
        undodb = self._get_undodb()

        with undodb.session_scope() as session:
            nulls: int = (
                session.execute(
                    text("SELECT COUNT(*) FROM changes WHERE new_json IS NULL")
                ).scalar()
                or 0
            )
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
            count: int = (
                session.execute(text("SELECT COUNT(*) FROM changes")).scalar() or 0
            )
        self.assertGreater(count, 0)

    def test_migrate_adds_missing_object_index(self):
        """migrate() adds the (obj_class, obj_handle) index when absent."""
        from gramps_webapi.undodb import migrate
        from sqlalchemy import inspect as sa_inspect

        undodb = self._get_undodb()
        with undodb.engine.begin() as conn:
            conn.execute(text("DROP INDEX ix_changes_obj_class_obj_handle"))

        index_names_before = {
            idx["name"] for idx in sa_inspect(undodb.engine).get_indexes("changes")
        }
        self.assertNotIn("ix_changes_obj_class_obj_handle", index_names_before)

        migrate(undodb)

        index_names_after = {
            idx["name"] for idx in sa_inspect(undodb.engine).get_indexes("changes")
        }
        self.assertIn("ix_changes_obj_class_obj_handle", index_names_after)

    def test_migrate_object_index_idempotent(self):
        """Calling migrate() when the index already exists does not raise."""
        from gramps_webapi.undodb import migrate

        undodb = self._get_undodb()
        migrate(undodb)
        migrate(undodb)  # second call must not crash

        from sqlalchemy import inspect as sa_inspect

        index_names = {
            idx["name"] for idx in sa_inspect(undodb.engine).get_indexes("changes")
        }
        self.assertIn("ix_changes_obj_class_obj_handle", index_names)

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
