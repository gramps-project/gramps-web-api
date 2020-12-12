#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the `gramps_webapi.api.resources.user` module."""

import re
import unittest
from quopri import decodestring
from unittest.mock import patch

from flask_jwt_extended import get_jwt_claims, get_jwt_identity
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Person, Surname

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from tests.test_endpoints import get_test_client

from . import BASE_URL


class TestUser(unittest.TestCase):
    """Test cases for the /api/user endpoints."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        _, _name = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        sqlauth = self.app.config["AUTH_PROVIDER"]
        sqlauth.create_table()
        sqlauth.add_user(name="user", password="123", email="test@example.com")
        self.assertTrue(self.app.testing)
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_change_password_wrong_method(self):
        rv = self.client.get(BASE_URL + "/user/password/change")
        assert rv.status_code == 405

    def test_change_password_no_token(self):
        rv = self.client.post(
            BASE_URL + "/user/password/change",
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 401

    def test_change_password_wrong_old_pw(self):
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "012", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_change_password(self):
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "456"}
        )
        assert rv.status_code == 200

    def test_change_password_twice(self):
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_reset_password_trigger_invalid_user(self):
        rv = self.client.post(
            BASE_URL + "/user/password/reset/trigger/", json={"username": "doesn_exist"}
        )
        assert rv.status_code == 404

    def test_reset_password_trigger_status(self):
        with patch("smtplib.SMTP") as mock_smtp:
            rv = self.client.post(
                BASE_URL + "/user/password/reset/trigger/", json={"username": "user"}
            )
            assert rv.status_code == 201

    def test_reset_password(self):
        with patch("smtplib.SMTP") as mock_smtp:
            rv = self.client.post(
                BASE_URL + "/user/password/reset/trigger/", json={"username": "user"}
            )
            context = mock_smtp.return_value
            context.send_message.assert_called()
            name, args, kwargs = context.method_calls.pop(0)
            msg = args[0]
            # extract the token from the message body
            body = msg.get_body().get_payload().replace("=\n", "")
            matches = re.findall(r".*jwt=([^\s]+).*", body)
            self.assertEqual(len(matches), 1, msg=body)
            token = matches[0]
        # try without token!
        rv = self.client.post(
            BASE_URL + "/user/password/reset/",
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 401)
        # try empty PW!
        rv = self.client.post(
            BASE_URL + "/user/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": ""},
        )
        self.assertEqual(rv.status_code, 422)
        # now that should work
        rv = self.client.post(
            BASE_URL + "/user/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        # try again with the same token!
        rv = self.client.post(
            BASE_URL + "/user/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 409)
        # old password doesn't work anymore
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        # new password works!
        rv = self.client.post(
            BASE_URL + "/login/", json={"username": "user", "password": "789"}
        )
        assert rv.status_code == 200
