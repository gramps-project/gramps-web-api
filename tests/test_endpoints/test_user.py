#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

import re
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth.const import (
    ROLE_DISABLED,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_UNCONFIRMED,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

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
        sqlauth.add_user(
            name="user", password="123", email="test@example.com", role=ROLE_MEMBER
        )
        sqlauth.add_user(
            name="owner", password="123", email="owner@example.com", role=ROLE_OWNER
        )
        self.assertTrue(self.app.testing)
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_change_password_wrong_method(self):
        rv = self.client.get(BASE_URL + "/users/-/password/change")
        assert rv.status_code == 404

    def test_change_password_no_token(self):
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 401

    def test_change_password_wrong_old_pw(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "012", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_change_password(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "456"}
        )
        assert rv.status_code == 200

    def test_change_other_user_password(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user can't change owner's PW
        rv = self.client.post(
            BASE_URL + "/users/owner/password/change",
            headers={"Authorization": "Bearer {}".format(token_user)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403
        # owner can change user's PW
        rv = self.client.post(
            BASE_URL + "/users/user/password/change",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "456"}
        )
        assert rv.status_code == 200
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200

    def test_change_password_twice(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_reset_password_trigger_invalid_user(self):
        rv = self.client.post(BASE_URL + "/users/doesn_exist/password/reset/trigger/")
        assert rv.status_code == 404

    def test_reset_password_trigger_status(self):
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            rv = self.client.post(BASE_URL + "/users/user/password/reset/trigger/")
            assert rv.status_code == 201

    def test_reset_password(self):
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            rv = self.client.post(BASE_URL + "/users/user/password/reset/trigger/")
            context = mock_smtp.return_value
            context.send_message.assert_called()
            name, args, kwargs = context.method_calls.pop(0)
            msg = args[0]
            # extract the token from the message body
            body = msg.get_body().get_payload().replace("=\n", "")
            matches = re.findall(r".*jwt=([^\s]+).*", body)
            self.assertEqual(len(matches), 1, msg=body)
            token = matches[0]
            if token[:2] == "3D":
                token = token[2:]
        # try without token!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/", json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 401)
        # try empty PW!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": ""},
        )
        self.assertEqual(rv.status_code, 400)
        # now that should work
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        # try again with the same token!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 409)
        # old password doesn't work anymore
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        # new password works!
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "789"}
        )
        assert rv.status_code == 200

    def test_show_user(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user can view themselves
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": "Bearer {}".format(token_user)},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": None,
            },
        )
        # user cannot view others
        rv = self.client.get(
            BASE_URL + "/users/owner/",
            headers={"Authorization": "Bearer {}".format(token_user)},
        )
        assert rv.status_code == 403
        # owner can view others
        rv = self.client.get(
            BASE_URL + "/users/user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": None,
            },
        )

    def test_show_users(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user cannot view users
        rv = self.client.get(
            BASE_URL + "/users/",
            headers={"Authorization": "Bearer {}".format(token_user)},
        )
        assert rv.status_code == 403
        # owner can view users
        rv = self.client.get(
            BASE_URL + "/users/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        self.assertEqual(
            set([user["name"] for user in rv.json]), {"user", "owner"},
        )

    def test_edit_user(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user can edit themselves
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": "Bearer {}".format(token_user)},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 200
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": "Bearer {}".format(token_user)},
        )
        assert rv.status_code == 200
        # email is unchanged!
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": "My Name",
            },
        )
        # user cannot change others
        rv = self.client.put(
            BASE_URL + "/users/owner/",
            headers={"Authorization": "Bearer {}".format(token_user)},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 403
        # owner can edit others
        rv = self.client.put(
            BASE_URL + "/users/user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={"full_name": "His Name"},
        )
        assert rv.status_code == 200
        rv = self.client.get(
            BASE_URL + "/users/user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": "His Name",
            },
        )

    def test_add_user(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user cannot add user
        rv = self.client.post(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": "Bearer {}".format(token_user)},
            json={
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "My Name",
                "password": "abc",
            },
        )
        assert rv.status_code == 403
        # missing password
        rv = self.client.post(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "My Name",
            },
        )
        assert rv.status_code == 422
        # existing user
        rv = self.client.post(
            BASE_URL + "/users/user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "New Name",
                "password": "abc",
            },
        )
        assert rv.status_code == 409
        # OK
        rv = self.client.post(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "New Name",
                "password": "abc",
            },
        )
        assert rv.status_code == 201
        rv = self.client.get(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        # email is unchanged!
        self.assertEqual(
            rv.json,
            {
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "New Name",
                "name": "new_user",
            },
        )
        # check token for new user
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "new_user", "password": "abc"}
        )
        assert rv.status_code == 200

    def test_register_user(self):
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            # role is not allowed
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "role": ROLE_OWNER,
                    "full_name": "My Name",
                    "password": "abc",
                },
            )
            assert rv.status_code == 422
            # missing password
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={"email": "new_2@example.com", "full_name": "My Name",},
            )
            assert rv.status_code == 422
            # existing user
            rv = self.client.post(
                BASE_URL + "/users/user/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                },
            )
            assert rv.status_code == 409
            # OK
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                },
            )
            assert rv.status_code == 201
            # get owner token
            rv = self.client.post(
                BASE_URL + "/token/", json={"username": "owner", "password": "123"},
            )
            assert rv.status_code == 200
            token_owner = rv.json["access_token"]
            rv = self.client.get(
                BASE_URL + "/users/new_user_2/",
                headers={"Authorization": "Bearer {}".format(token_owner)},
            )
            assert rv.status_code == 200
            self.assertEqual(
                rv.json,
                {
                    "email": "new_2@example.com",
                    "role": ROLE_UNCONFIRMED,
                    "full_name": "New Name",
                    "name": "new_user_2",
                },
            )
            # new user cannot get token
            rv = self.client.post(
                BASE_URL + "/token/", json={"username": "new_user_2", "password": "abc"}
            )
            assert rv.status_code == 403

    def test_confirm_email(self):
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            rv = self.client.post(
                BASE_URL + "/users/new_user_3/register/",
                json={
                    "email": "new_3@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                },
            )
            assert rv.status_code == 201
            context = mock_smtp.return_value
            context.send_message.assert_called()
            name, args, kwargs = context.method_calls.pop(0)
            msg = args[0]
            # extract the token from the message body
            body = msg.get_body().get_payload().replace("=\n", "")
            matches = re.findall(r".*jwt=([^\s]+).*", body)
            self.assertEqual(len(matches), 1, msg=body)
            token = matches[0]
            if token[:2] == "3D":
                token = token[2:]
            # try without token
            rv = self.client.get(BASE_URL + "/users/-/email/confirm/")
            self.assertEqual(rv.status_code, 401)
            # now that should work
            rv = self.client.get(
                BASE_URL + "/users/-/email/confirm/",
                headers={"Authorization": "Bearer {}".format(token)},
            )
            self.assertEqual(rv.status_code, 200)
            # check return template
            self.assertIn(b"Thank you for confirming your e-mail address", rv.data)
            # get owner token
            rv = self.client.post(
                BASE_URL + "/token/", json={"username": "owner", "password": "123"},
            )
            assert rv.status_code == 200
            token_owner = rv.json["access_token"]
            # get user info
            rv = self.client.get(
                BASE_URL + "/users/new_user_3/",
                headers={"Authorization": "Bearer {}".format(token_owner)},
            )
            assert rv.status_code == 200
            # new role should be ROLE_DISABLED!
            self.assertEqual(
                rv.json,
                {
                    "email": "new_3@example.com",
                    "role": ROLE_DISABLED,
                    "full_name": "New Name",
                    "name": "new_user_3",
                },
            )
            # try getting list of people with email confirmation token
            # this should not be allowed!
            rv = self.client.get(
                BASE_URL + "/people/",
                headers={"Authorization": "Bearer {}".format(token)},
            )
            self.assertEqual(rv.status_code, 401)

    def test_delete_user(self):
        # get user token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        # get owner token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # add user
        rv = self.client.post(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={
                "email": "to_delete@example.com",
                "role": ROLE_MEMBER,
                "full_name": "To Delete",
                "password": "abc",
            },
        )
        assert rv.status_code == 201
        rv = self.client.get(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        # check token for new user
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user_to_delete", "password": "abc"}
        )
        assert rv.status_code == 200
        # user cannot delete user
        rv = self.client.delete(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": "Bearer {}".format(token_user)},
        )
        assert rv.status_code == 403
        # owner can user
        rv = self.client.delete(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 200
        # check user is gone
        rv = self.client.get(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
        )
        assert rv.status_code == 404
        # check user can't get token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user_to_delete", "password": "abc"}
        )
        assert rv.status_code == 403

    def test_change_user_role(self):
        # get user token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        # get owner token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # add user
        rv = self.client.post(
            BASE_URL + "/users/user_change_role/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={
                "email": "change_role@example.com",
                "role": ROLE_MEMBER,
                "full_name": "Change Role",
                "password": "abc",
            },
        )
        assert rv.status_code == 201
        # get token for new user
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "user_change_role", "password": "abc"},
        )
        assert rv.status_code == 200
        token_new_user = rv.json["access_token"]
        # user can change own details
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": "Bearer {}".format(token_new_user)},
            json={"full_name": "Change My Role"},
        )
        assert rv.status_code == 200
        # user cannot change own role
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": "Bearer {}".format(token_new_user)},
            json={"role": ROLE_OWNER},
        )
        assert rv.status_code == 403
        # owner can change user role
        rv = self.client.put(
            BASE_URL + "/users/user_change_role/",
            headers={"Authorization": "Bearer {}".format(token_owner)},
            json={"role": ROLE_OWNER},
        )
        assert rv.status_code == 200
