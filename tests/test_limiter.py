#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2022      David Straub
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

"""Tests for rate limited endpoints."""

import os
import tempfile
import unittest
from pathlib import Path
from time import sleep
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


class TestRateLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dbpath)
        cls.tree = tree
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": True},
                config_from_env=False,
            )
            cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_token_endpoint(self):
        # other tests may have requested a token within the last second
        sleep(1)
        rv = self.client.post(
            "/api/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        rv = self.client.post(
            "/api/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 429
        sleep(1)
        rv = self.client.post(
            "/api/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200

    def _header(self, username: str) -> dict:
        # the token endpoint is rate limited to one request per second
        sleep(1)
        rv = self.client.post(
            "/api/token/", json={"username": username, "password": "123"}
        )
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def test_media_archive(self):
        """Only creating a new media archive counts towards the limit."""
        headers = self._header("admin")
        rv = self.client.post("/api/media/archive/", headers=headers)
        assert rv.status_code == 201
        file_name = rv.json["file_name"]
        # the existing archive is returned, which doesn't count
        rv = self.client.post("/api/media/archive/", headers=headers)
        assert rv.status_code == 201
        # creating the archive again does
        archive_dir = Path(self.app.config["EXPORT_DIR"], "media_archives", self.tree)
        (archive_dir / file_name).unlink()
        rv = self.client.post("/api/media/archive/", headers=headers)
        assert rv.status_code == 429
        # the limit is per user
        rv = self.client.post("/api/media/archive/", headers=self._header("user"))
        assert rv.status_code == 201


class TestBackupRateLimit(unittest.TestCase):
    """Creating backups is rate limited per tree."""

    @classmethod
    def setUpClass(cls):
        cls.name = "backups_rate_limit"
        cls.dbman = CLIDbManager(DbState())
        dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dbpath)
        cls.backup_dir = tempfile.TemporaryDirectory()
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.test_app = create_app(
                config_from_env=False,
                config={
                    "TREE": cls.name,
                    "BACKUP_DIR": cls.backup_dir.name,
                    "RATELIMIT_ENABLED": True,
                    "RATE_LIMIT_BACKUP": "2 per day",
                },
            )
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        with cls.test_app.app_context():
            user_db.create_all()
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=tree)
            add_user(name="owner2", password="123", role=ROLE_OWNER, tree=tree)
            add_user(name="editor", password="123", role=ROLE_EDITOR, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        cls.backup_dir.cleanup()

    def _header(self, name: str) -> dict:
        # the token endpoint is rate limited to one request per second
        sleep(1)
        rv = self.client.post("/api/token/", json={"username": name, "password": "123"})
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def test_rate_limit(self):
        editor = self._header("editor")
        owner = self._header("owner")
        # rejected requests don't count
        for _ in range(3):
            rv = self.client.post("/api/backups/", headers=editor)
            self.assertEqual(rv.status_code, 403)
        for _ in range(2):
            rv = self.client.post("/api/backups/", headers=owner)
            self.assertEqual(rv.status_code, 201)
        rv = self.client.post("/api/backups/", headers=owner)
        self.assertEqual(rv.status_code, 429)
        # the limit is per tree, not per user
        rv = self.client.post("/api/backups/", headers=self._header("owner2"))
        self.assertEqual(rv.status_code, 429)
