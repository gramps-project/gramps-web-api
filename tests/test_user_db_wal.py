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

"""Tests that a SQLite user database runs in WAL mode."""

import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from gramps_webapi.app import create_app
from gramps_webapi.auth import TaskTree, user_db
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.util.task_state import QUEUED, acquire


class UserDbWalTestCase(unittest.TestCase):
    """A file-backed SQLite user database."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "users.sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "USER_DB_URI": f"sqlite:///{self.path}",
                }
            )
        with self.app.app_context():
            user_db.create_all()

    def tearDown(self):
        with self.app.app_context():
            user_db.session.remove()
            user_db.engine.dispose()
        self.tmp.cleanup()

    def test_journal_mode_is_wal(self):
        with sqlite3.connect(self.path) as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")

    def test_reader_not_blocked_by_a_committing_writer(self):
        """A task status read succeeds while a worker holds the write lock.

        In rollback-journal mode an EXCLUSIVE lock blocks readers, and the
        read below fails with "database is locked" after the driver's timeout.
        """
        task_id = str(uuid.uuid4())
        with self.app.app_context():
            acquire(task_id, "test", "tree", None, None)
        writer = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        try:
            writer.execute("BEGIN EXCLUSIVE")
            writer.execute(
                "UPDATE task_tree SET status = 'running' WHERE task_id = ?",
                (task_id,),
            )
            start = time.monotonic()
            with self.app.app_context():
                row = user_db.session.get(TaskTree, task_id)
                status = row.status
            elapsed = time.monotonic() - start
        finally:
            writer.execute("ROLLBACK")
            writer.close()
        self.assertEqual(status, QUEUED)
        self.assertLess(elapsed, 1)

    def test_in_memory_database_is_left_alone(self):
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "USER_DB_URI": "sqlite://",
                }
            )
        with app.app_context():
            with user_db.engine.connect() as connection:
                mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        self.assertEqual(mode, "memory")


if __name__ == "__main__":
    unittest.main()
