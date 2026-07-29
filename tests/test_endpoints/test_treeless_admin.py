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

"""Tests for site admins without a tree in multi-tree mode."""

import os
import unittest
from unittest.mock import patch

from flask_jwt_extended.utils import decode_token
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, get_all_user_details, user_db
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL


class TestTreelessAdmin(unittest.TestCase):
    """Test cases for a site admin without a tree (multi-tree mode)."""

    def setUp(self):
        self.name = "Test Web API Treeless"
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
            # the state the onboarding dialog leaves behind: admin, no tree
            add_user(
                name="admin",
                password="123",
                email="admin@example.com",
                role=ROLE_ADMIN,
                tree=None,
            )
            add_user(
                name="owner",
                password="123",
                email="owner@example.com",
                role=ROLE_OWNER,
                tree=self.tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def _login(self, username):
        return self.client.post(
            BASE_URL + "/token/", json={"username": username, "password": "123"}
        )

    def _token(self, username):
        return self._login(username).json["access_token"]

    def _headers(self, username):
        return {"Authorization": f"Bearer {self._token(username)}"}

    def test_treeless_admin_can_log_in(self):
        """A treeless admin gets a token without a tree claim."""
        rv = self._login("admin")
        assert rv.status_code == 200
        with self.app.app_context():
            token = decode_token(rv.json["access_token"])
        assert "tree" not in token
        assert "ViewOtherTree" in token["permissions"]

    def test_treeless_admin_can_refresh(self):
        """The refresh endpoint also tolerates a missing tree."""
        refresh_token = self._login("admin").json["refresh_token"]
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert rv.status_code == 200
        with self.app.app_context():
            token = decode_token(rv.json["access_token"])
        assert "tree" not in token

    def test_treeless_non_admin_is_forbidden(self):
        """A non-admin without a tree is still refused."""
        with self.app.app_context():
            add_user(
                name="stray",
                password="123",
                email="stray@example.com",
                role=ROLE_OWNER,
                tree=None,
            )
        rv = self._login("stray")
        assert rv.status_code == 403

    def test_treeless_admin_can_list_and_create_trees(self):
        """The bootstrap path: list trees, then create one."""
        headers = self._headers("admin")
        rv = self.client.get(BASE_URL + "/trees/", headers=headers)
        assert rv.status_code == 200
        assert self.tree in [tree["id"] for tree in rv.json]
        rv = self.client.post(
            BASE_URL + "/trees/", headers=headers, json={"name": "My New Tree"}
        )
        assert rv.status_code == 201
        assert rv.json["name"] == "My New Tree"
        self.dbman.remove_database("My New Tree")

    def test_treeless_admin_can_edit_other_tree(self):
        """Editing a tree the admin does not belong to is allowed."""
        rv = self.client.put(
            BASE_URL + f"/trees/{self.tree}",
            headers=self._headers("admin"),
            json={"quota_people": 1000},
        )
        assert rv.status_code == 200
        rv = self.client.put(
            BASE_URL + f"/trees/{self.tree}/config",
            headers=self._headers("admin"),
            json={"theme": "dark"},
        )
        assert rv.status_code == 200

    def test_treeless_admin_own_tree_endpoints_fail(self):
        """Endpoints resolving the *own* tree fail cleanly."""
        headers = self._headers("admin")
        for url in ["/trees/-", "/trees/-/config"]:
            rv = self.client.get(BASE_URL + url, headers=headers)
            assert rv.status_code == 403, url

    def test_treeless_admin_can_manage_users(self):
        """Users can be listed and viewed without a tree."""
        headers = self._headers("admin")
        rv = self.client.get(BASE_URL + "/users/", headers=headers)
        assert rv.status_code == 200
        assert {"admin", "owner"} <= {user["name"] for user in rv.json}
        rv = self.client.get(BASE_URL + "/users/-/", headers=headers)
        assert rv.status_code == 200
        assert rv.json["name"] == "admin"
        rv = self.client.get(BASE_URL + "/users/owner/", headers=headers)
        assert rv.status_code == 200

    def test_treeless_admin_cannot_create_treeless_user(self):
        """Creating a non-admin user without a tree is refused."""
        rv = self.client.post(
            BASE_URL + "/users/newbie/",
            headers=self._headers("admin"),
            json={
                "email": "newbie@example.com",
                "full_name": "New Bie",
                "password": "123",
                "role": ROLE_OWNER,
            },
        )
        assert rv.status_code == 422
        rv = self.client.post(
            BASE_URL + "/users/newbie/",
            headers=self._headers("admin"),
            json={
                "email": "newbie@example.com",
                "full_name": "New Bie",
                "password": "123",
                "role": ROLE_OWNER,
                "tree": self.tree,
            },
        )
        assert rv.status_code == 201

    def test_missing_tree_does_not_widen_user_query(self):
        """A tree of None must not be read as "all trees"."""
        with self.app.app_context():
            # "" and NULL are both "no tree", as in fill_tree()
            add_user(
                name="empty",
                password="123",
                email="empty@example.com",
                role=ROLE_ADMIN,
                tree="",
            )
            # what a treeless caller's tree ID resolves to
            treeless = get_all_user_details(tree=None)
            assert {user["name"] for user in treeless} == {"admin", "empty"}
            # widening is opt-in and explicit
            everyone = get_all_user_details(tree=None, all_trees=True)
            assert {user["name"] for user in everyone} == {"admin", "empty", "owner"}
            # a real tree ID is unaffected
            scoped = get_all_user_details(tree=self.tree)
            assert {user["name"] for user in scoped} == {"owner"}
            # ... and picks up treeless users only when asked
            scoped = get_all_user_details(tree=self.tree, include_treeless=True)
            assert {user["name"] for user in scoped} == {"owner", "admin", "empty"}

    def test_treeless_admin_cannot_bulk_create_treeless_user(self):
        """Bulk creation follows the same rule as single creation."""
        headers = self._headers("admin")
        rv = self.client.post(
            BASE_URL + "/users/",
            headers=headers,
            json=[
                {
                    "name": "bulk1",
                    "email": "bulk1@example.com",
                    "full_name": "Bulk One",
                    "role": ROLE_OWNER,
                }
            ],
        )
        assert rv.status_code == 422
        # ... but another site admin may be treeless
        rv = self.client.post(
            BASE_URL + "/users/",
            headers=headers,
            json=[
                {
                    "name": "bulk2",
                    "email": "bulk2@example.com",
                    "full_name": "Bulk Two",
                    "role": ROLE_ADMIN,
                }
            ],
        )
        assert rv.status_code == 201

    def test_treeless_admin_cannot_be_demoted_without_tree(self):
        """Demoting a treeless admin would create a user who cannot log in."""
        headers = self._headers("admin")
        rv = self.client.put(
            BASE_URL + "/users/admin/", headers=headers, json={"role": ROLE_OWNER}
        )
        assert rv.status_code == 422
        # assigning a tree in the same request is fine
        rv = self.client.put(
            BASE_URL + "/users/admin/",
            headers=headers,
            json={"role": ROLE_OWNER, "tree": self.tree},
        )
        assert rv.status_code == 200

    def test_demoting_admin_with_tree_is_allowed(self):
        """The guard only applies to treeless admins."""
        rv = self.client.put(
            BASE_URL + "/users/owner/",
            headers=self._headers("admin"),
            json={"role": ROLE_OWNER},
        )
        assert rv.status_code == 200

    def test_onboarding_refresh_picks_up_new_tree(self):
        """The documented onboarding flow: assign a tree, then refresh."""
        tokens = self._login("admin").json
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        rv = self.client.post(
            BASE_URL + "/trees/", headers=headers, json={"name": "Refresh Tree"}
        )
        assert rv.status_code == 201
        new_tree = rv.json["id"]
        try:
            rv = self.client.put(
                BASE_URL + "/users/-/", headers=headers, json={"tree": new_tree}
            )
            assert rv.status_code == 200
            rv = self.client.post(
                BASE_URL + "/token/refresh/",
                headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
            )
            assert rv.status_code == 200
            with self.app.app_context():
                token = decode_token(rv.json["access_token"])
            assert token["tree"] == new_tree
        finally:
            self.dbman.remove_database("Refresh Tree")

    def test_treeless_admin_cannot_mint_access_token(self):
        """Persistent access tokens are tree-scoped."""
        rv = self.client.post(
            BASE_URL + "/users/-/access-tokens/anniversaries_ics/",
            headers=self._headers("admin"),
        )
        assert rv.status_code == 403

    def test_treeless_admin_cannot_read_data(self):
        """Data endpoints fail with a clear message rather than a crash."""
        headers = self._headers("admin")
        for url in ["/metadata/", "/people/", "/tasks/"]:
            rv = self.client.get(BASE_URL + url, headers=headers)
            assert rv.status_code == 403, url

    def test_admin_can_assign_own_tree(self):
        """The full bootstrap: create a tree, assign it, log in again."""
        headers = self._headers("admin")
        rv = self.client.post(
            BASE_URL + "/trees/", headers=headers, json={"name": "Bootstrap Tree"}
        )
        assert rv.status_code == 201
        new_tree = rv.json["id"]
        try:
            rv = self.client.put(
                BASE_URL + "/users/-/", headers=headers, json={"tree": new_tree}
            )
            assert rv.status_code == 200
            with self.app.app_context():
                token = decode_token(self._token("admin"))
            assert token["tree"] == new_tree
            rv = self.client.get(
                BASE_URL + "/metadata/", headers=self._headers("admin")
            )
            assert rv.status_code == 200
        finally:
            self.dbman.remove_database("Bootstrap Tree")


if __name__ == "__main__":
    unittest.main()
