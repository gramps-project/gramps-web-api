#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Tests for the database repair endpoint."""

import os
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


class TestRepair(unittest.TestCase):
    """Test database repair."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API Repair"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=tree)
        rv = cls.client.post(
            "/api/token/", json={"username": "owner", "password": "123"}
        )
        access_token = rv.json["access_token"]
        cls.headers = {"Authorization": f"Bearer {access_token}"}

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_repair_empty_database(self):
        """Test Repairing the empty database."""
        rv = self.client.post("/api/trees/-/repair", headers=self.headers)
        assert rv.status_code == 201
        assert rv.json["num_errors"] == 0
        assert rv.json["message"] == ""

    def test_repair_empty_person(self):
        """Test Repairing an empty person."""
        rv = self.client.post("/api/people/", json={}, headers=self.headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/people/", headers=self.headers)
        assert rv.status_code == 200
        assert len(rv.json) == 1
        rv = self.client.post("/api/trees/-/repair", headers=self.headers)
        assert rv.status_code == 201
        assert rv.json["num_errors"] == 1
        rv = self.client.get("/api/people/", headers=self.headers)
        assert rv.status_code == 200
        assert len(rv.json) == 0

    def test_repair_empty_event(self):
        """Test Repairing an empty event."""
        rv = self.client.post("/api/events/", json={}, headers=self.headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/events/", headers=self.headers)
        assert rv.status_code == 200
        assert len(rv.json) == 1
        rv = self.client.post("/api/trees/-/repair", headers=self.headers)
        assert rv.status_code == 201
        assert rv.json["num_errors"] == 1
        rv = self.client.get("/api/events/", headers=self.headers)
        assert rv.status_code == 200
        assert len(rv.json) == 0
