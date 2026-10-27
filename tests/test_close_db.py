#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Closing a database releases its connection even if close() fails (#1108)."""

import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from flask import g
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Note

from gramps_webapi.api.access import AccessPolicy, RestrictedDb
from gramps_webapi.api.util import close_db
from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager


def _db(fails: bool) -> MagicMock:
    """A database whose close() fails like DbGeneric's metadata write can."""
    db = MagicMock()
    if fails:
        db.close.side_effect = sqlite3.OperationalError("database is locked")
    return db


def test_close_db_closes_connection_when_close_fails():
    db = _db(fails=True)
    with pytest.raises(sqlite3.OperationalError):
        close_db(db)
    db.dbapi.close.assert_called_once()
    db.undodb.close.assert_called_once()


def test_close_db_does_not_close_connection_twice():
    db = _db(fails=False)
    close_db(db)
    db.close.assert_called_once()
    db.dbapi.close.assert_not_called()
    db.undodb.close.assert_called_once()


def test_restricted_db_closes_connection_when_close_fails():
    db = _db(fails=True)
    restricted = RestrictedDb(db, AccessPolicy(view_private=False))
    with pytest.raises(sqlite3.OperationalError):
        close_db(restricted)
    db.dbapi.close.assert_called_once()
    db.undodb.close.assert_called_once()


def test_teardown_closes_write_db_when_closing_read_db_fails():
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        app = create_app(config={"TESTING": True, "RATELIMIT_ENABLED": False})
    db, db_write = _db(fails=True), _db(fails=False)
    ctx = app.app_context()
    ctx.push()
    g.db = db
    g.db_write = db_write
    with pytest.raises(sqlite3.OperationalError):
        ctx.pop()
    db.dbapi.close.assert_called_once()
    db_write.close.assert_called_once()
    db_write.undodb.close.assert_called_once()


@pytest.fixture
def tree():
    name = "Test close_db failure"
    dbman = CLIDbManager(DbState())
    dbman.create_new_db_cli(name, dbid="sqlite")
    yield WebDbManager(name)
    dbman.remove_database(name)


def test_real_tree_is_writable_after_close_fails(tree):
    """The metadata save in close() loses a write race to another connection (#1108)."""
    failed = tree.get_db(readonly=False).db
    failed.dbapi.execute("PRAGMA busy_timeout = 100")
    other = sqlite3.connect(os.path.join(tree.path, "sqlite.db"), isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        close_db(failed)
    other.rollback()
    other.close()
    # `failed` stays referenced, as it does in a worker. If its connection were still
    # open, its SHARED lock would make this commit fail with "database is locked".
    db = tree.get_db(readonly=False).db
    with DbTxn("Add a note", db) as trans:
        db.add_note(Note("written after a failed close"), trans)
    close_db(db)
    db = tree.get_db().db
    assert db.get_number_of_notes() == 1
    close_db(db)
