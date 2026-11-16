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

"""Tests for setting another user's password with PUT /users/<name>/ (#918)."""

import os
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, get_user_details, user_db
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_MEMBER, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL


class TestUserSetPassword(unittest.TestCase):
    """An owner or admin sets the password of a user with a lower role."""

    def setUp(self):
        self.name = "Test Web API set password"
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
            add_user(name="admin", password="a", role=ROLE_ADMIN, tree=self.tree)
            add_user(name="owner", password="o", role=ROLE_OWNER, tree=self.tree)
            add_user(name="owner2", password="o2", role=ROLE_OWNER, tree=self.tree)
            add_user(
                name="member",
                password="m",
                email="member@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            add_user(name="member2", password="m2", role=ROLE_MEMBER, tree=self.tree)
            add_user(
                name="elsewhere", password="e", role=ROLE_MEMBER, tree="other-tree"
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def _login(self, name, password):
        return self.client.post(
            BASE_URL + "/token/", json={"username": name, "password": password}
        )

    def _tokens(self, name, password):
        rv = self._login(name, password)
        self.assertEqual(rv.status_code, 200)
        return rv.json

    def _put(self, as_tokens, user_name, body):
        return self.client.put(
            BASE_URL + f"/users/{user_name}/",
            headers={"Authorization": f"Bearer {as_tokens['access_token']}"},
            json=body,
        )

    def _refresh(self, refresh_token):
        return self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )

    def test_owner_sets_a_members_password(self):
        owner = self._tokens("owner", "o")
        member = self._tokens("member", "m")
        rv = self._put(owner, "member", {"password": "new"})
        self.assertEqual(rv.status_code, 200)
        # the password is never echoed back
        self.assertEqual(rv.data, b"")
        self.assertEqual(self._login("member", "m").status_code, 403)
        self.assertEqual(self._login("member", "new").status_code, 200)
        # the member's existing sessions end; the owner's do not
        self.assertEqual(self._refresh(member["refresh_token"]).status_code, 403)
        self.assertEqual(self._refresh(owner["refresh_token"]).status_code, 200)

    def test_admin_sets_an_owners_password(self):
        admin = self._tokens("admin", "a")
        rv = self._put(admin, "owner", {"password": "new"})
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._login("owner", "new").status_code, 200)

    def test_equal_role_is_refused(self):
        owner = self._tokens("owner", "o")
        rv = self._put(owner, "owner2", {"password": "new"})
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self._login("owner2", "o2").status_code, 200)
        admin = self._tokens("admin", "a")
        with self.app.app_context():
            add_user(name="admin2", password="a2", role=ROLE_ADMIN, tree=self.tree)
        rv = self._put(admin, "admin2", {"password": "new"})
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self._login("admin2", "a2").status_code, 200)

    def test_higher_role_is_refused(self):
        owner = self._tokens("owner", "o")
        rv = self._put(owner, "admin", {"password": "new"})
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self._login("admin", "a").status_code, 200)

    def test_a_refused_password_applies_no_other_field(self):
        owner = self._tokens("owner", "o")
        rv = self._put(
            owner, "owner2", {"password": "new", "email": "takeover@example.com"}
        )
        self.assertEqual(rv.status_code, 403)
        self.assertIsNone(get_user_details("owner2")["email"])

    def test_password_and_other_fields_together(self):
        owner = self._tokens("owner", "o")
        rv = self._put(
            owner, "member", {"password": "new", "email": "changed@example.com"}
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(get_user_details("member")["email"], "changed@example.com")
        self.assertEqual(self._login("member", "new").status_code, 200)

    def test_own_user_is_refused(self):
        owner = self._tokens("owner", "o")
        for user_name in ("-", "owner"):
            rv = self._put(owner, user_name, {"password": "new"})
            self.assertEqual(rv.status_code, 400, user_name)
        self.assertEqual(self._login("owner", "o").status_code, 200)

    def test_empty_password_is_refused(self):
        owner = self._tokens("owner", "o")
        rv = self._put(owner, "member", {"password": ""})
        self.assertEqual(rv.status_code, 400)
        self.assertEqual(self._login("member", "m").status_code, 200)

    def test_member_cannot_set_another_members_password(self):
        member = self._tokens("member", "m")
        rv = self._put(member, "member2", {"password": "new"})
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self._login("member2", "m2").status_code, 200)

    def test_owner_cannot_set_a_password_in_another_tree(self):
        owner = self._tokens("owner", "o")
        rv = self._put(owner, "elsewhere", {"password": "new"})
        self.assertEqual(rv.status_code, 403)
        with self.app.app_context():
            self.assertTrue(get_user_details("elsewhere"))

    def test_refused_while_local_auth_is_disabled(self):
        owner = self._tokens("owner", "o")
        with patch.dict(
            self.app.config, {"OIDC_ENABLED": True, "OIDC_DISABLE_LOCAL_AUTH": True}
        ):
            rv = self._put(owner, "member", {"password": "new"})
        self.assertEqual(rv.status_code, 405)
        self.assertEqual(self._login("member", "m").status_code, 200)
        # the setting has no effect while OIDC is disabled
        with patch.dict(
            self.app.config, {"OIDC_ENABLED": False, "OIDC_DISABLE_LOCAL_AUTH": True}
        ):
            rv = self._put(owner, "member", {"password": "new"})
        self.assertEqual(rv.status_code, 200)

    def test_without_password_other_edits_still_allow_equal_roles(self):
        # the stricter check is for the password only (#1132 is unchanged)
        owner = self._tokens("owner", "o")
        rv = self._put(owner, "owner2", {"email": "owner2@example.com"})
        self.assertEqual(rv.status_code, 200)
