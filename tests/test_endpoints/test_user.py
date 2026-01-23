#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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
from unittest.mock import MagicMock

import pytest
from celery.result import AsyncResult
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import (
    add_user,
    create_oidc_account,
    delete_user,
    get_all_user_details,
    get_guid,
    get_number_users,
    get_user_details,
    get_user_oidc_accounts,
    user_db,
)
from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_DISABLED,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_UNCONFIRMED,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

from . import BASE_URL
from .util import fetch_header


class TestUser(unittest.TestCase):
    """Test cases for the /api/user endpoints."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        dbpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)
        dbpath2, _ = self.dbman.create_new_db_cli("Test Web API 2", dbid="sqlite")
        self.tree = os.path.basename(dbpath)
        self.tree2 = os.path.basename(dbpath2)
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
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            add_user(
                name="user2",
                password="123",
                email="test2@example.com",
                role=ROLE_MEMBER,
                tree=self.tree2,
            )
            add_user(
                name="owner",
                password="123",
                email="owner@example.com",
                role=ROLE_OWNER,
                tree=self.tree,
            )
            add_user(
                name="owner2",
                password="123",
                email="owner2@example.com",
                role=ROLE_OWNER,
                tree=self.tree2,
            )
            add_user(
                name="admin",
                password="123",
                email="admin@example.com",
                role=ROLE_ADMIN,
                tree=self.tree,
            )
        self.assertTrue(self.app.testing)
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_change_password_wrong_method(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.get(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 405

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
            headers={"Authorization": f"Bearer {token}"},
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
            headers={"Authorization": f"Bearer {token}"},
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
            headers={"Authorization": f"Bearer {token_user}"},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403
        # owner can change user's PW
        rv = self.client.post(
            BASE_URL + "/users/user/password/change",
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_reset_password_trigger_invalid_user(self):
        rv = self.client.post(BASE_URL + "/users/doesn_exist/password/reset/trigger/")
        assert rv.status_code == 404

    def test_reset_password_trigger_status(self):
        with patch("gramps_webapi.api.util.smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value = mock_smtp_instance
            rv = self.client.post(BASE_URL + "/users/user/password/reset/trigger/")
            assert rv.status_code == 201
            mock_smtp_instance.send_message.assert_called_once()

    def test_reset_password(self):
        with patch("gramps_webapi.api.util.smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value = mock_smtp_instance
            rv = self.client.post(BASE_URL + "/users/user/password/reset/trigger/")
            assert rv.status_code == 201
            mock_smtp_instance.send_message.assert_called_once()
            msg = mock_smtp_instance.send_message.call_args[0][0]
            # extract the token from the message body
            body = msg.get_body().get_payload().replace("=\n", "")
            matches = re.findall(
                r"jwt=3D([a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)", body
            )
            self.assertEqual(len(matches), 1, msg=body)
            token = matches[0]
            if token[:2] == "3D":
                token = token[2:]
        # try without token!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 401)
        # try empty PW!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": ""},
        )
        self.assertEqual(rv.status_code, 400, rv.data)
        # now that should work
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": f"Bearer {token}"},
            json={"new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        # try again with the same token!
        rv = self.client.post(
            BASE_URL + "/users/-/password/reset/",
            headers={"Authorization": f"Bearer {token}"},
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
            headers={"Authorization": f"Bearer {token_user}"},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": None,
                "tree": self.tree,
            },
        )
        # user cannot view others
        rv = self.client.get(
            BASE_URL + "/users/owner/",
            headers={"Authorization": f"Bearer {token_user}"},
        )
        assert rv.status_code == 403
        # owner can view others
        rv = self.client.get(
            BASE_URL + "/users/user/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": None,
                "tree": self.tree,
            },
        )
        # owner cannot view other tree
        rv = self.client.get(
            BASE_URL + "/users/user2/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 403
        # admin can view other tree
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "admin", "password": "123"},
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        rv = self.client.get(
            BASE_URL + "/users/user2/",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user2",
                "email": "test2@example.com",
                "role": ROLE_MEMBER,
                "full_name": None,
                "tree": self.tree2,
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
            headers={"Authorization": f"Bearer {token_user}"},
        )
        assert rv.status_code == 403
        # owner can view users
        rv = self.client.get(
            BASE_URL + "/users/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 200
        self.assertEqual(
            set(user["name"] for user in rv.json),
            {"admin", "user", "owner"},
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
            headers={"Authorization": f"Bearer {token_user}"},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 200
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {token_user}"},
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
                "tree": self.tree,
            },
        )
        # user cannot change others
        rv = self.client.put(
            BASE_URL + "/users/owner/",
            headers={"Authorization": f"Bearer {token_user}"},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 403
        # owner can edit others
        rv = self.client.put(
            BASE_URL + "/users/user/",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"full_name": "His Name"},
        )
        assert rv.status_code == 200
        rv = self.client.get(
            BASE_URL + "/users/user/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 200
        self.assertEqual(
            rv.json,
            {
                "name": "user",
                "email": "test@example.com",
                "role": ROLE_MEMBER,
                "full_name": "His Name",
                "tree": self.tree,
            },
        )

    def test_edit_user_duplicate_email(self):
        """Test that duplicate email returns 409 Conflict."""
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # Owner tries to change user's email to owner's existing email (duplicate)
        rv = self.client.put(
            BASE_URL + "/users/user/",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"email": "owner@example.com"},
        )
        assert rv.status_code == 409
        assert "E-mail already exists" in rv.json["error"]["message"]

    def test_edit_own_user_duplicate_email(self):
        """Test that duplicate email returns 409 Conflict when modifying own user."""
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        # User tries to change their own email to owner's existing email (duplicate)
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {token_user}"},
            json={"email": "owner@example.com"},
        )
        assert rv.status_code == 409
        assert "E-mail already exists" in rv.json["error"]["message"]

    def test_add_user(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token_user = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # user cannot add user
        rv = self.client.post(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": f"Bearer {token_user}"},
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
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token_owner}"},
            json={
                "email": "new@example.com",
                "role": ROLE_MEMBER,
                "full_name": "New Name",
                "password": "abc",
            },
        )
        assert rv.status_code == 409
        assert rv.json["error"]["message"] == "User already exists"
        # OK
        rv = self.client.post(
            BASE_URL + "/users/new_user/",
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token_owner}"},
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
                "tree": self.tree,
            },
        )
        # check token for new user
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "new_user", "password": "abc"}
        )
        assert rv.status_code == 200

    def test_register_user(self):
        with patch("gramps_webapi.api.util.smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value = mock_smtp_instance
            # role is not allowed
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "role": ROLE_OWNER,
                    "full_name": "My Name",
                    "password": "abc",
                    "tree": self.tree,
                },
            )
            assert rv.status_code == 422
            # missing tree
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "My Name",
                    "password": "abc",
                },
            )
            # missing password
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "My Name",
                    "tree": self.tree,
                },
            )
            assert rv.status_code == 422
            # existing user
            rv = self.client.post(
                BASE_URL + "/users/user/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                    "tree": self.tree,
                },
            )
            assert rv.status_code == 409
            assert rv.json["error"]["message"] == "User already exists"
            # OK
            rv = self.client.post(
                BASE_URL + "/users/new_user_2/register/",
                json={
                    "email": "new_2@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                    "tree": self.tree,
                },
            )
            assert rv.status_code == 201
            # get owner token
            rv = self.client.post(
                BASE_URL + "/token/",
                json={"username": "owner", "password": "123"},
            )
            assert rv.status_code == 200
            token_owner = rv.json["access_token"]
            rv = self.client.get(
                BASE_URL + "/users/new_user_2/",
                headers={"Authorization": f"Bearer {token_owner}"},
            )
            assert rv.status_code == 200
            self.assertEqual(
                rv.json,
                {
                    "email": "new_2@example.com",
                    "role": ROLE_UNCONFIRMED,
                    "full_name": "New Name",
                    "name": "new_user_2",
                    "tree": self.tree,
                },
            )
            # new user cannot get token
            rv = self.client.post(
                BASE_URL + "/token/", json={"username": "new_user_2", "password": "abc"}
            )
            assert rv.status_code == 403

    def test_confirm_email(self):
        with patch("gramps_webapi.api.util.smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value = mock_smtp_instance
            rv = self.client.post(
                BASE_URL + "/users/new_user_3/register/",
                json={
                    "email": "new_3@example.com",
                    "full_name": "New Name",
                    "password": "abc",
                    "tree": self.tree,
                },
            )
            assert rv.status_code == 201
            mock_smtp_instance.send_message.assert_called_once()
            msg = mock_smtp_instance.send_message.call_args[0][0]
            # extract the token from the message body
            body = msg.get_body().get_payload().replace("=\n", "")
            matches = re.findall(
                r"jwt=3D([a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+)", body
            )
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
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(rv.status_code, 200, rv.data)
            # check return template
            self.assertIn(b"Thank you for confirming your e-mail address", rv.data)
            # get owner token
            rv = self.client.post(
                BASE_URL + "/token/",
                json={"username": "owner", "password": "123"},
            )
            assert rv.status_code == 200
            token_owner = rv.json["access_token"]
            # get user info
            rv = self.client.get(
                BASE_URL + "/users/new_user_3/",
                headers={"Authorization": f"Bearer {token_owner}"},
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
                    "tree": self.tree,
                },
            )
            # try getting list of people with email confirmation token
            # this should not be allowed!
            rv = self.client.get(
                BASE_URL + "/people/",
                headers={"Authorization": f"Bearer {token}"},
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
            BASE_URL + "/token/",
            json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # add user
        rv = self.client.post(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token_user}"},
        )
        assert rv.status_code == 403
        # owner can user
        rv = self.client.delete(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 200
        # check user is gone
        rv = self.client.get(
            BASE_URL + "/users/user_to_delete/",
            headers={"Authorization": f"Bearer {token_owner}"},
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
            BASE_URL + "/token/",
            json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        # get admin token
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "admin", "password": "123"},
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        # add user
        rv = self.client.post(
            BASE_URL + "/users/user_change_role/",
            headers={"Authorization": f"Bearer {token_owner}"},
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
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"role": ROLE_OWNER},
        )
        assert rv.status_code == 200
        # owner cannot change user role to admin
        rv = self.client.put(
            BASE_URL + "/users/user_change_role/",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"role": ROLE_ADMIN},
        )
        assert rv.status_code == 403
        # admin can
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "admin", "password": "123"},
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        rv = self.client.put(
            BASE_URL + "/users/user_change_role/",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"role": ROLE_ADMIN},
        )
        assert rv.status_code == 200

    def test_add_users(self):
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "owner", "password": "123"},
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "admin", "password": "123"},
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        # other tree - not allowed
        users = [{"name": "new_user_1", "tree": self.tree2}]
        rv = self.client.post(
            BASE_URL + "/users/",
            json=users,
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 403
        users = [{"name": "new_user_1", "tree": "not_exists"}]
        rv = self.client.post(
            BASE_URL + "/users/",
            json=users,
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 422
        # OK - same tree
        users = [{"name": "new_user_1"}]
        rv = self.client.post(
            BASE_URL + "/users/",
            json=users,
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 201
        rv = self.client.get(
            BASE_URL + "/users/new_user_1/",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 200
        assert rv.json["tree"] == self.tree


class TestUserCreateOwner(unittest.TestCase):
    """Test cases for the /api/user/create_owner endpoint."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        _, _name = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            db_manager = WebDbManager(name=self.name, create_if_missing=False)
            self.tree = db_manager.dirname
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def _delete_users(self):
        """Delete existing users."""
        users = get_all_user_details(tree=None)
        for user in users:
            delete_user(name=user["name"])

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_create_admin(self):
        self._delete_users()
        rv = self.client.get(f"{BASE_URL}/token/create_owner/")
        assert rv.status_code == 200
        token = rv.json["access_token"]
        with self.app.app_context():
            assert get_number_users() == 0
        # data missing
        rv = self.client.post(
            f"{BASE_URL}/users/site_admin/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 422
        with self.app.app_context():
            assert get_number_users() == 0
        # non-existing tree
        rv = self.client.post(
            f"{BASE_URL}/users/site_admin/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
                "tree": "some_tree",
            },
        )
        assert rv.status_code == 422
        with self.app.app_context():
            assert get_number_users() == 0
        rv = self.client.post(
            f"{BASE_URL}/users/site_admin/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
            },
        )
        assert rv.status_code == 201
        with self.app.app_context():
            assert get_number_users() == 1
            assert get_user_details("site_admin")["role"] == ROLE_ADMIN
        # try posting again
        rv = self.client.post(
            f"{BASE_URL}/users/site_admin_2/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
            },
        )
        assert rv.status_code == 405
        with self.app.app_context():
            assert get_number_users() == 1
        rv = self.client.get(f"{BASE_URL}/token/create_owner/")
        assert rv.status_code == 405

    def test_create_owner(self):
        self._delete_users()
        rv = self.client.post(
            f"{BASE_URL}/token/create_owner/", json={"tree": self.tree}
        )
        assert rv.status_code == 201
        token = rv.json["access_token"]
        with self.app.app_context():
            assert get_number_users() == 0
        # data missing
        rv = self.client.post(
            f"{BASE_URL}/users/tree_owner/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "My Name"},
        )
        assert rv.status_code == 422
        with self.app.app_context():
            assert get_number_users() == 0
        # non-existing tree
        rv = self.client.post(
            f"{BASE_URL}/users/tree_owner/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
                "tree": "some_tree",
            },
        )
        assert rv.status_code == 422
        with self.app.app_context():
            assert get_number_users() == 0
        rv = self.client.post(
            f"{BASE_URL}/users/tree_owner/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
            },
        )
        assert rv.status_code == 201
        with self.app.app_context():
            assert get_number_users() == 1
            assert get_user_details("tree_owner")["role"] == ROLE_OWNER
            assert get_user_details("tree_owner")["tree"] == self.tree
        # try posting again
        rv = self.client.post(
            f"{BASE_URL}/users/tree_owner_2/create_owner/",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "password": "123",
                "email": "test@example.com",
                "full_name": "My Name",
            },
        )
        assert rv.status_code == 405
        with self.app.app_context():
            assert get_number_users() == 1
        rv = self.client.get(f"{BASE_URL}/token/create_owner/")
        assert rv.status_code == 405


class TestUserNameChange(unittest.TestCase):
    """Test cases for changing user names."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        dbpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            add_user(
                name="admin",
                password="123",
                email="admin@example.com",
                role=ROLE_ADMIN,
                tree=self.tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()
        # Get admin token
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        self.token = rv.json["access_token"]

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_change_own_username(self):
        """Test changing own username."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Login as the user
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "testuser", "password": "testpass"},
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Change own username using "-"
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name_new": "renameduser"},
        )
        assert rv.status_code == 200

        # Verify old username doesn't work
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "testuser", "password": "testpass"},
        )
        assert rv.status_code == 403

        # Verify new username works
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "renameduser", "password": "testpass"},
        )
        assert rv.status_code == 200

        # Verify user details reflect new name using - (self-reference)
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "renameduser"

    def test_admin_change_other_username(self):
        """Test admin changing another user's username."""
        # Create a regular user
        with self.app.app_context():
            add_user(
                name="regularuser",
                password="pass123",
                email="regular@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Admin changes the username
        rv = self.client.put(
            BASE_URL + "/users/regularuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "renamedregular"},
        )
        assert rv.status_code == 200

        # Verify old username doesn't exist
        rv = self.client.get(
            BASE_URL + "/users/regularuser/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert rv.status_code == 404

        # Verify new username exists
        rv = self.client.get(
            BASE_URL + "/users/renamedregular/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "renamedregular"

    def test_change_username_duplicate(self):
        """Test that changing to an existing username fails."""
        # Create two users
        with self.app.app_context():
            add_user(
                name="user1",
                password="pass1",
                email="user1@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            add_user(
                name="user2",
                password="pass2",
                email="user2@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Try to rename user1 to user2
        rv = self.client.put(
            BASE_URL + "/users/user1/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "user2"},
        )
        assert rv.status_code == 409
        assert "already exists" in rv.json["error"]["message"].lower()

    def test_change_username_empty(self):
        """Test that changing to empty username fails."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Try to rename to empty string
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": ""},
        )
        assert rv.status_code == 400
        assert "empty" in rv.json["error"]["message"].lower()

        # Try to rename to whitespace
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "   "},
        )
        assert rv.status_code == 400
        assert "empty" in rv.json["error"]["message"].lower()

    def test_change_username_reserved(self):
        """Test that changing to reserved usernames fails."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Try to rename to "-"
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "-"},
        )
        assert rv.status_code == 400
        assert "reserved" in rv.json["error"]["message"].lower()

        # Try to rename to "_"
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "_"},
        )
        assert rv.status_code == 400
        assert "reserved" in rv.json["error"]["message"].lower()

    def test_change_username_token_still_valid(self):
        """Test that JWT tokens remain valid after username change."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Login and get token
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "testuser", "password": "testpass"},
        )
        assert rv.status_code == 200
        user_token = rv.json["access_token"]

        # Change username using the token
        rv = self.client.put(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name_new": "renameduser"},
        )
        assert rv.status_code == 200

        # Verify the old token still works (it has user_id, not username)
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "renameduser"

    def test_change_username_permission_denied(self):
        """Test that non-admin cannot change other user's username."""
        # Create two regular users
        with self.app.app_context():
            add_user(
                name="user1",
                password="pass1",
                email="user1@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            add_user(
                name="user2",
                password="pass2",
                email="user2@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Login as user1
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": "user1", "password": "pass1"},
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Try to change user2's username
        rv = self.client.put(
            BASE_URL + "/users/user2/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name_new": "renameduser2"},
        )
        assert rv.status_code == 403

    def test_change_username_combined_with_other_fields(self):
        """Test that username can be changed along with other fields."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="old@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Change username and email together
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "name_new": "newusername",
                "email": "new@example.com",
                "full_name": "New Full Name",
            },
        )
        assert rv.status_code == 200

        # Verify all changes
        rv = self.client.get(
            BASE_URL + "/users/newusername/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "newusername"
        assert rv.json["email"] == "new@example.com"
        assert rv.json["full_name"] == "New Full Name"

    def test_change_username_to_same_name(self):
        """Test that changing username to the same name succeeds (no-op)."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="testuser",
                password="testpass",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )

        # Change username to the same name
        rv = self.client.put(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "testuser"},
        )
        assert rv.status_code == 200

        # Verify user still exists
        rv = self.client.get(
            BASE_URL + "/users/testuser/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "testuser"

    def test_change_username_oidc_account_preserved(self):
        """Test that OIDC account associations are preserved after username change."""
        # Create a user
        with self.app.app_context():
            add_user(
                name="oidcuser",
                password="testpass",
                email="oidc@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            # Get user GUID and create OIDC association
            user_id = get_guid("oidcuser")
            create_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-user-12345",
                email="oidc@example.com",
            )
            # Verify OIDC account exists before rename
            oidc_accounts_before = get_user_oidc_accounts(user_id)
            assert len(oidc_accounts_before) == 1
            assert oidc_accounts_before[0]["provider_id"] == "google"
            assert oidc_accounts_before[0]["subject_id"] == "google-user-12345"

        # Change username
        rv = self.client.put(
            BASE_URL + "/users/oidcuser/",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name_new": "renamedoidcuser"},
        )
        assert rv.status_code == 200

        # Verify the username changed
        rv = self.client.get(
            BASE_URL + "/users/renamedoidcuser/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert rv.status_code == 200
        assert rv.json["name"] == "renamedoidcuser"

        # Verify in database that the OIDC link still exists and points to the same user_id
        with self.app.app_context():
            new_user_id = get_guid("renamedoidcuser")
            # User ID should remain the same (GUIDs don't change)
            assert new_user_id == user_id
            # OIDC account associations should be preserved
            oidc_accounts_after = get_user_oidc_accounts(new_user_id)
            assert len(oidc_accounts_after) == 1
            assert oidc_accounts_after[0]["provider_id"] == "google"
            assert oidc_accounts_after[0]["subject_id"] == "google-user-12345"
