#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026  Gramps Development Team
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

"""Tests for user database migrations running in several processes at once."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing

from alembic.config import Config
from alembic.script import ScriptDirectory

from gramps_webapi.const import ENV_CONFIG_FILE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# each run starts two migrations at the same moment; without a lock, most
# runs end with one of them failing or with two rows in alembic_version
RUNS = 5


def get_script() -> ScriptDirectory:
    """Return the migration scripts of the user database."""
    config = Config(os.path.join(ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(ROOT, "alembic_users"))
    return ScriptDirectory.from_config(config)


def start_upgrade(db_uri: str, revision: str = "head") -> subprocess.Popen:
    """Start `alembic upgrade` in a new process, like the Docker entrypoint."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {ENV_CONFIG_FILE, "USER_DB_URI"}
    }
    env["GRAMPSWEB_USER_DB_URI"] = db_uri
    return subprocess.Popen(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


class TestConcurrentMigration(unittest.TestCase):
    """Two processes upgrade the same SQLite user database at the same time."""

    def run_pairs(self, start_revision: str | None = None) -> None:
        head = get_script().get_current_head()
        for _ in range(RUNS):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "users.sqlite")
                db_uri = f"sqlite:///{path}"
                if start_revision:
                    proc = start_upgrade(db_uri, start_revision)
                    output = proc.communicate()[0].decode()
                    self.assertEqual(proc.returncode, 0, output)
                procs = [start_upgrade(db_uri), start_upgrade(db_uri)]
                for proc in procs:
                    output = proc.communicate()[0].decode()
                    self.assertEqual(proc.returncode, 0, output)
                with closing(sqlite3.connect(path)) as conn:
                    versions = [
                        row[0]
                        for row in conn.execute(
                            "SELECT version_num FROM alembic_version"
                        )
                    ]
                self.assertEqual(versions, [head])

    def test_empty_database(self):
        """A new install, where the web and the Celery container start together."""
        self.run_pairs()

    def test_upgrade(self):
        """An upgrade by the newest migration."""
        script = get_script()
        previous = script.get_revision(script.get_current_head()).down_revision
        self.assertIsInstance(previous, str)
        self.run_pairs(start_revision=previous)
