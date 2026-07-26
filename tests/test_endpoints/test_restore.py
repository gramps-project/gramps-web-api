#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
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

"""Tests for the /api/importers/{extension}/file/restore endpoint."""

import io
import os
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EMPTY_GRAMPS_AUTH_CONFIG

from .. import ExampleDbInMemory
from . import BASE_URL, TEST_USERS
from .checks import check_success
from .util import fetch_header

RESTORE_URL = BASE_URL + "/importers/gramps/file/restore"
IMPORT_URL = BASE_URL + "/importers/gramps/file"


class TestRestoreFile(unittest.TestCase):
    """Test cases for the /api/importers/{extension}/file/restore endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "restore_empty"
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(config_from_env=False, config={"TREE": cls.name})
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        cls.tree = os.path.basename(cls.dbpath)
        with cls.test_app.app_context():
            user_db.create_all()
            for role in TEST_USERS:
                add_user(
                    name=TEST_USERS[role]["name"],
                    password=TEST_USERS[role]["password"],
                    role=role,
                )
        cls.example_db = ExampleDbInMemory()
        with open(cls.example_db.path, "rb") as f:
            cls.backup_bytes = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def _empty_tree(self):
        """Empty the tree via the API so tests do not depend on each other.

        Deleting the SQLite file does not empty an already-populated tree,
        because the database connection persists across requests, so we clear
        the data through the delete-all endpoint instead. This makes each test
        self-contained regardless of execution order.
        """
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(f"{BASE_URL}/objects/delete/", headers=headers)
        self.assertIn(rv.status_code, (200, 202))
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), 0)

    def _post_backup(self, url, role=ROLE_OWNER):
        headers = fetch_header(self.client, role=role)
        return self.client.post(
            url, data=io.BytesIO(self.backup_bytes), headers=headers
        )

    def test_restore_wrong_role(self):
        """Editors may not restore from backup."""
        rv = self._post_backup(RESTORE_URL, role=ROLE_EDITOR)
        self.assertEqual(rv.status_code, 403)

    def test_restore_empty_file(self):
        """An empty upload is rejected."""
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(RESTORE_URL, data=None, headers=headers)
        self.assertEqual(rv.status_code, 400)
        self.assertIn("empty", rv.json["error"]["message"])

    def test_restore_missing_importer(self):
        """An unknown importer extension returns 404."""
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(
            BASE_URL + "/importers/missing/file/restore",
            data=io.BytesIO(self.backup_bytes),
            headers=headers,
        )
        self.assertEqual(rv.status_code, 404)

    def test_restore_dry_run_then_apply(self):
        """Dry run previews the changeset; apply resets the tree to the backup."""
        # Start from a clean tree and import the backup once (the "good" state).
        self._empty_tree()
        rv = self._post_backup(IMPORT_URL)
        self.assertEqual(rv.status_code, 201)
        people_good = len(check_success(self, f"{BASE_URL}/people/"))
        self.assertEqual(people_good, 2157)

        # Simulate the incident: import again, duplicating every object.
        rv = self._post_backup(IMPORT_URL)
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), 2 * 2157)

        # Dry run: preview the delta without touching the tree.
        rv = self._post_backup(RESTORE_URL + "?dry_run=true")
        self.assertEqual(rv.status_code, 200)
        summary = rv.json
        self.assertEqual(summary["to_add"]["people"], 0)
        self.assertEqual(summary["to_delete"]["people"], 2157)
        # The original import's handles match the backup's exactly, so those
        # 2157 count as unchanged; the duplicate copy has fresh handles absent
        # from the backup, so it's entirely in to_delete instead.
        self.assertEqual(summary["unchanged"]["people"], 2157)
        # Nothing was modified by the dry run.
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), 2 * 2157)

        # Apply the restore: the tree is reset to the backup state.
        rv = self._post_backup(RESTORE_URL)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["to_delete"]["people"], 2157)
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), people_good)
        # Search index reflects the restored state.
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(
            f"{BASE_URL}/search/?query=Andrew&pagesize=5", headers=headers
        )
        self.assertEqual(len(rv.json), 5)

    def test_restore_into_empty_tree_adds_everything(self):
        """Restoring a backup into an empty tree adds all objects."""
        self._empty_tree()
        rv = self._post_backup(RESTORE_URL + "?dry_run=true")
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["to_add"]["people"], 2157)
        self.assertEqual(rv.json["to_delete"]["people"], 0)
        self.assertEqual(rv.json["unchanged"]["people"], 0)
        rv = self._post_backup(RESTORE_URL)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), 2157)
