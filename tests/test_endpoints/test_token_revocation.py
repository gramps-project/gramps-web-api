#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Tests for ending refresh tokens on a password change or a disabled account."""

import os
import unittest
from unittest.mock import patch

from flask_jwt_extended import create_refresh_token
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, get_guid, modify_user, user_db
from gramps_webapi.auth.const import (
    ROLE_DISABLED,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL


class TestTokenRevocation(unittest.TestCase):
    """Refresh tokens stop working after a password change or when disabled."""

    def setUp(self):
        self.name = "Test Web API token revocation"
        self.dbman = CLIDbManager(DbState())
        dbpath, _name = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=self.tree)
            add_user(name="member", password="456", role=ROLE_MEMBER, tree=self.tree)
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def _login(self, name, password):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": name, "password": password}
        )
        self.assertEqual(rv.status_code, 200)
        return rv.json

    def _refresh(self, refresh_token):
        return self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

    def test_refresh_works_without_changes(self):
        tokens = self._login("member", "456")
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 200)

    def test_own_password_change_ends_other_sessions(self):
        tokens = self._login("member", "456")
        other_session = self._login("member", "456")
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"old_password": "456", "new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 403)
        self.assertEqual(self._refresh(other_session["refresh_token"]).status_code, 403)
        # a new login with the new password gets a working refresh token
        new_tokens = self._login("member", "789")
        self.assertEqual(self._refresh(new_tokens["refresh_token"]).status_code, 200)

    def test_own_password_change_keeps_this_session(self):
        tokens = self._login("member", "456")
        rv = self.client.post(
            BASE_URL + "/users/-/password/change",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"old_password": "456", "new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        # the response carries a new token pair for the session that changed it
        self.assertEqual(self._refresh(rv.json["refresh_token"]).status_code, 200)
        rv = self.client.get(
            BASE_URL + "/users/-/",
            headers={"Authorization": f"Bearer {rv.json['access_token']}"},
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["name"], "member")

    def test_changing_another_users_password_returns_no_tokens(self):
        owner_tokens = self._login("owner", "123")
        member_tokens = self._login("member", "456")
        rv = self.client.post(
            BASE_URL + "/users/member/password/change",
            headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            json={"old_password": "456", "new_password": "789"},
        )
        self.assertEqual(rv.status_code, 201)
        self.assertNotIn("refresh_token", rv.json or {})
        self.assertEqual(self._refresh(member_tokens["refresh_token"]).status_code, 403)
        self.assertEqual(self._refresh(owner_tokens["refresh_token"]).status_code, 200)

    def test_password_set_elsewhere_ends_sessions(self):
        # the reset-password flow and any future admin path go through modify_user
        tokens = self._login("member", "456")
        with self.app.app_context():
            modify_user(name="member", password="789")
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 403)

    def test_disabling_ends_sessions(self):
        member_tokens = self._login("member", "456")
        owner_tokens = self._login("owner", "123")
        rv = self.client.put(
            BASE_URL + "/users/member/",
            headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            json={"role": ROLE_DISABLED},
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._refresh(member_tokens["refresh_token"]).status_code, 403)

    def test_enabling_again_does_not_revive_old_sessions(self):
        tokens = self._login("member", "456")
        with self.app.app_context():
            modify_user(name="member", role=ROLE_DISABLED)
            modify_user(name="member", role=ROLE_MEMBER)
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 403)
        new_tokens = self._login("member", "456")
        self.assertEqual(self._refresh(new_tokens["refresh_token"]).status_code, 200)

    def test_other_changes_keep_sessions(self):
        tokens = self._login("member", "456")
        with self.app.app_context():
            modify_user(name="member", email="member@example.com", fullname="M")
            modify_user(name="member", role=ROLE_OWNER)
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 200)

    def test_password_change_keeps_other_users_sessions(self):
        tokens = self._login("owner", "123")
        with self.app.app_context():
            modify_user(name="member", password="789")
        self.assertEqual(self._refresh(tokens["refresh_token"]).status_code, 200)

    def test_refresh_token_without_version_claim(self):
        # refresh tokens issued before this change have no version claim; they
        # keep working until the user's version is first increased
        with self.app.app_context():
            user_id = get_guid("member")
            old_token = create_refresh_token(identity=str(user_id))
        self.assertEqual(self._refresh(old_token).status_code, 200)
        with self.app.app_context():
            modify_user(name="member", password="789")
        self.assertEqual(self._refresh(old_token).status_code, 403)
