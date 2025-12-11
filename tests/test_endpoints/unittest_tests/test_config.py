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

"""Tests for the `gramps_webapi.api.resources.user` module."""

import os
import re
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_MEMBER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL


class TestConfig(unittest.TestCase):
    """Test cases for the /api/config/ endpoints."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        dirpath, _name = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            add_user(
                name="user",
                password="123",
                email="test1@example.com",
                role=ROLE_MEMBER,
                tree=tree,
            )
            add_user(
                name="admin",
                password="123",
                email="test2@example.com",
                role=ROLE_ADMIN,
                tree=tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        self.header_member = {"Authorization": f"Bearer {rv.json['access_token']}"}
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        self.header_owner = {"Authorization": f"Bearer {rv.json['access_token']}"}

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_get_config(self):
        rv = self.client.get(
            f"{BASE_URL}/config/",
            headers=self.header_member,
        )
        assert rv.status_code == 403
        rv = self.client.get(
            f"{BASE_URL}/config/",
            headers=self.header_owner,
        )
        assert rv.status_code == 200
        assert rv.json == {}

    def test_set_config_unauth(self):
        rv = self.client.put(
            f"{BASE_URL}/config/EMAIL_HOST/",
            headers=self.header_member,
            json={"value": "myhost"},
        )
        assert rv.status_code == 403

    def test_set_config_put(self):
        rv = self.client.put(
            f"{BASE_URL}/config/EMAIL_HOST/",
            headers=self.header_owner,
            json={"value": "host1"},
        )
        assert rv.status_code == 200
        rv = self.client.get(
            f"{BASE_URL}/config/EMAIL_HOST/", headers=self.header_owner
        )
        assert rv.status_code == 200
        assert rv.json == "host1"

    def test_config_delete(self):
        rv = self.client.put(
            f"{BASE_URL}/config/EMAIL_HOST/",
            headers=self.header_owner,
            json={"value": "host2"},
        )
        rv = self.client.get(
            f"{BASE_URL}/config/EMAIL_HOST/", headers=self.header_owner
        )
        assert rv.status_code == 200
        assert rv.json == "host2"
        rv = self.client.delete(
            f"{BASE_URL}/config/EMAIL_HOST/",
            headers=self.header_owner,
        )
        rv = self.client.get(
            f"{BASE_URL}/config/EMAIL_HOST/", headers=self.header_owner
        )
        assert rv.status_code == 404

    def test_config_reset_password(self):
        """Check that the config options are picked up in the reset email."""

        def get_from_host():
            with patch("smtplib.SMTP_SSL") as mock_smtp:
                self.client.post(f"{BASE_URL}/users/user/password/reset/trigger/")
                context = mock_smtp.return_value
                context.send_message.assert_called()
                name, args, kwargs = context.method_calls.pop(0)
                msg = args[0]
                body = msg.get_body().get_payload().replace("=\n", "")
                matches = re.findall(r".*(https?://[^/]+)/api", body)
                host = matches[0]
                return msg["From"], host

        from_email, host = get_from_host()
        assert from_email == ""
        assert host == "http://localhost"
        self.client.put(
            f"{BASE_URL}/config/BASE_URL/",
            headers=self.header_owner,
            json={"value": "https://www.example.com"},
        )
        self.client.put(
            f"{BASE_URL}/config/DEFAULT_FROM_EMAIL/",
            headers=self.header_owner,
            json={"value": "from@example.com"},
        )
        from_email, host = get_from_host()
        assert from_email == "from@example.com"
        assert host == "https://www.example.com"
