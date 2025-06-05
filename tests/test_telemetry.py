""" "Test the telemetry functionality."""

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

import time
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.api.cache import persistent_cache
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager


class TestTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API test_telemetry"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        cls.client = cls.app.test_client()
        # add a user to the database
        db_manager = WebDbManager(cls.name, create_if_missing=False)
        tree = db_manager.dirname
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
        persistent_cache.clear()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        persistent_cache.clear()

    def test_telemetry(self):
        with patch.dict("os.environ", {"MOCK_TELEMETRY": "1"}):
            with patch("requests.post") as mock_post:
                rv = self.client.post(
                    "/api/token/", json={"username": "user", "password": "123"}
                )
                access_token = rv.json["access_token"]
                header = {"Authorization": "Bearer {}".format(access_token)}
                rv = self.client.get("/api/people/")
                assert rv.status_code == 401
                # No JWT in request, so telemetry should not have been sent
                mock_post.assert_not_called()
                rv = self.client.get("/api/people/", headers=header)
                now = time.time()
                assert rv.status_code == 200
                # Telemetry should have been sent
                mock_post.assert_called_once()
                _, kwargs = mock_post.call_args
                assert "timestamp" in kwargs["json"]
                assert "server_uuid" in kwargs["json"]
                assert "tree_uuid" in kwargs["json"]
                last_sent = persistent_cache.get("telemetry_last_sent")
                assert last_sent is not None
                assert abs(now - last_sent) < 5.0
                assert kwargs["json"]["timestamp"] - last_sent < 5.0
                server_uuid = persistent_cache.get("telemetry_server_uuid")
                assert server_uuid == kwargs["json"]["server_uuid"]
                # call again
                rv = self.client.get("/api/people/", headers=header)
                # sent still just once
                mock_post.assert_called_once()
