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

import requests
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.api import telemetry
from gramps_webapi.api.cache import persistent_cache
from gramps_webapi.api.tasks import send_telemetry_task
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST
from gramps_webapi.const import (
    ENV_CONFIG_FILE,
    TELEMETRY_SERVER_ID_KEY,
    TELEMETRY_TIMESTAMP_KEY,
    TEST_AUTH_CONFIG,
)
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

    def setUp(self):
        persistent_cache.clear()
        telemetry._last_sent = 0.0
        telemetry._fallback_server_uuid = None

    def _auth_header(self):
        rv = self.client.post("/api/token/", json={"username": "user", "password": "123"})
        return {"Authorization": "Bearer {}".format(rv.json["access_token"])}

    def test_broken_cache_sends_once(self):
        """A cache that silently fails to write (as FileSystemCache does on a
        read-only directory) must not cause a ping on every request."""
        with patch.dict("os.environ", {"MOCK_TELEMETRY": "1"}):
            with patch("requests.post") as mock_post:
                header = self._auth_header()
                with (
                    patch.object(persistent_cache, "get", return_value=None),
                    patch.object(persistent_cache, "set", return_value=False),
                ):
                    for _ in range(10):
                        rv = self.client.get("/api/people/", headers=header)
                        assert rv.status_code == 200
                    mock_post.assert_called_once()
                    server_uuid = mock_post.call_args.kwargs["json"]["server_uuid"]
                    with self.app.app_context():
                        assert telemetry.get_server_uuid() == server_uuid
                        assert telemetry.get_server_uuid() == server_uuid

    def test_task_receives_payload_from_web_process(self):
        """The payload, including the server UUID, is built before queueing."""
        with patch.dict("os.environ", {"MOCK_TELEMETRY": "1"}):
            with patch("gramps_webapi.app.run_task") as mock_run_task:
                header = self._auth_header()
                rv = self.client.get("/api/people/", headers=header)
                assert rv.status_code == 200
                mock_run_task.assert_called_once()
                kwargs = mock_run_task.call_args.kwargs
                assert kwargs["tree"]
                assert kwargs["payload"]["server_uuid"] == persistent_cache.get(
                    TELEMETRY_SERVER_ID_KEY
                )
                assert "tree_uuid" in kwargs["payload"]
                # the timestamp is set before queueing, so no second task
                rv = self.client.get("/api/people/", headers=header)
                mock_run_task.assert_called_once()

    def test_task_ignores_missing_payload(self):
        """A task queued by an older version (tree only) is dropped."""
        with patch("requests.post") as mock_post:
            send_telemetry_task(tree="some_tree")
            mock_post.assert_not_called()

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
                last_sent = persistent_cache.get(TELEMETRY_TIMESTAMP_KEY)
                assert last_sent is not None
                assert abs(now - last_sent) < 5.0
                assert kwargs["json"]["timestamp"] - last_sent < 5.0
                server_uuid = persistent_cache.get(TELEMETRY_SERVER_ID_KEY)
                assert server_uuid == kwargs["json"]["server_uuid"]
                # call again
                rv = self.client.get("/api/people/", headers=header)
                # sent still just once
                mock_post.assert_called_once()

    def test_telemetry_send_failure_does_not_affect_response(self):
        """A network error sending telemetry must not return HTTP 500 to the caller."""
        with patch.dict("os.environ", {"MOCK_TELEMETRY": "1"}):
            with patch(
                "requests.post",
                side_effect=requests.exceptions.ConnectionError("unreachable"),
            ):
                rv = self.client.post(
                    "/api/token/", json={"username": "user", "password": "123"}
                )
                access_token = rv.json["access_token"]
                header = {"Authorization": "Bearer {}".format(access_token)}
                rv = self.client.get("/api/people/", headers=header)
                assert rv.status_code == 200

    def test_telemetry_timestamp_set_even_on_send_failure(self):
        """Timestamp is written before the HTTP call, so a failed send still
        updates the 24 h window and prevents immediate retry."""
        with patch.dict("os.environ", {"MOCK_TELEMETRY": "1"}):
            with patch(
                "requests.post",
                side_effect=requests.exceptions.ConnectionError("unreachable"),
            ):
                rv = self.client.post(
                    "/api/token/", json={"username": "user", "password": "123"}
                )
                access_token = rv.json["access_token"]
                header = {"Authorization": "Bearer {}".format(access_token)}
                self.client.get("/api/people/", headers=header)
                last_sent = persistent_cache.get(TELEMETRY_TIMESTAMP_KEY)
                assert last_sent is not None
                assert abs(time.time() - last_sent) < 5.0
