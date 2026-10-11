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

"""Tests for the ETags of cached endpoints."""

import hashlib
import os
import unittest
import uuid
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


class TestRequestCacheETag(unittest.TestCase):
    """Test that cached endpoints use the cache key as ETag."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API ETag"
        cls.dbman = CLIDbManager(DbState())
        dbpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
        cls.headers_admin = get_headers(cls.client, "admin", "123")
        cls.headers_user = get_headers(cls.client, "user", "123")
        cls.handle = cls._add_note("A note.")

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    @classmethod
    def _add_note(cls, text: str) -> str:
        handle = str(uuid.uuid4())
        rv = cls.client.post(
            "/api/notes/",
            json={
                "handle": handle,
                "_class": "Note",
                "text": {"_class": "StyledText", "string": text},
            },
            headers=cls.headers_admin,
        )
        assert rv.status_code == 201
        return handle

    def _get_etag(self, path: str, headers: dict[str, str]) -> str:
        rv = self.client.get(path, headers=headers)
        self.assertEqual(rv.status_code, 200)
        return rv.headers["ETag"]

    def test_etag_stable(self):
        """Repeated requests get the same ETag."""
        path = f"/api/notes/{self.handle}"
        etag = self._get_etag(path, self.headers_admin)
        self.assertEqual(etag, self._get_etag(path, self.headers_admin))

    def test_etag_changes_after_write(self):
        """Any change to the tree changes the ETag."""
        path = f"/api/notes/{self.handle}"
        etag = self._get_etag(path, self.headers_admin)
        self._add_note("Another note.")
        self.assertNotEqual(etag, self._get_etag(path, self.headers_admin))

    def test_etag_depends_on_args(self):
        """Different query arguments get different ETags."""
        path = f"/api/notes/{self.handle}"
        etag = self._get_etag(path, self.headers_admin)
        self.assertNotEqual(
            etag, self._get_etag(f"{path}?keys=handle", self.headers_admin)
        )

    def test_etag_depends_on_permission(self):
        """Users with and without permission to view private records get
        different ETags."""
        path = f"/api/notes/{self.handle}"
        self.assertNotEqual(
            self._get_etag(path, self.headers_admin),
            self._get_etag(path, self.headers_user),
        )

    def test_etag_without_timestamp(self):
        """Without a last change timestamp, the ETag is the hash of the body."""
        path = f"/api/notes/{self.handle}"
        with patch(
            "gramps_webapi.api.cache.get_db_last_change_timestamp", return_value=None
        ):
            rv = self.client.get(path, headers=self.headers_admin)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers["ETag"], f'"{hashlib.sha256(rv.data).hexdigest()}"')
