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

"""Consistent snapshots of a Gramps database for long reads such as exports.

Gramps reads every object with its own query, outside of any transaction. A
long read like an export can therefore see a write half-way through, and the
resulting file can reference objects it doesn't contain. On import, Gramps
turns such references into empty placeholder objects without any warning.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import DBMODE_R
from gramps.gen.db.utils import make_database

from .resources.db_backend import SHARED_POSTGRES_CLASS_NAME, is_sqlite
from .util import ModifiedPrivateProxyDb


@contextmanager
def consistent_read(db_handle: DbReadBase) -> Generator[DbReadBase, None, None]:
    """Yield a database handle on which all reads see a single snapshot.

    SQLite: the database file is copied with SQLite's online backup API and
    the copy is opened read-only. SharedPostgreSQL: the reads run in a
    read-only `REPEATABLE READ` transaction. Other backends are yielded
    unchanged, without a snapshot.

    A private proxy database is preserved: the snapshot is taken of the
    underlying database and wrapped in a new proxy if needed.
    """
    if isinstance(db_handle, ModifiedPrivateProxyDb):
        with consistent_read(db_handle.db) as snapshot_db:
            if snapshot_db is db_handle.db:
                yield db_handle
            else:
                yield ModifiedPrivateProxyDb(snapshot_db)
        return
    if is_sqlite(db_handle):
        with _sqlite_snapshot(db_handle) as snapshot_db:
            yield snapshot_db
    elif type(db_handle).__name__ == SHARED_POSTGRES_CLASS_NAME:
        with _repeatable_read_transaction(db_handle):
            yield db_handle
    else:
        yield db_handle


@contextmanager
def _sqlite_snapshot(db_handle: Any) -> Generator[DbReadBase, None, None]:
    """Yield a read-only copy of a SQLite database, deleted afterwards.

    The copy is made in a single step of the online backup API, which holds a
    read lock only while copying, so writers are blocked for that time only.
    """
    source_path = os.path.abspath(os.path.join(db_handle.get_save_path(), "sqlite.db"))
    with tempfile.TemporaryDirectory(prefix="gramps-snapshot-") as directory:
        source = sqlite3.connect(f"{Path(source_path).as_uri()}?mode=ro", uri=True)
        try:
            target = sqlite3.connect(os.path.join(directory, "sqlite.db"))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        snapshot_db = make_database("sqlite")
        snapshot_db.load(directory, mode=DBMODE_R)
        try:
            yield snapshot_db
        finally:
            snapshot_db.close()


@contextmanager
def _repeatable_read_transaction(db_handle: Any) -> Generator[None, None, None]:
    """Run the reads inside the context in one read-only snapshot transaction.

    All cursors of a SharedPostgreSQL handle share its single connection, so
    every read sees the snapshot. The transaction is ended with an explicit
    `ROLLBACK` statement: the connection is in autocommit mode, where the
    driver's `rollback()` does nothing. The addon rolls back by itself on any
    SQL error, which ends the snapshot early, so errors must not be swallowed
    inside the context.
    """
    db_handle.dbapi.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    try:
        # the snapshot is taken at the first query, not at BEGIN
        db_handle.dbapi.execute("SELECT 1")
        yield
    finally:
        db_handle.dbapi.execute("ROLLBACK")
