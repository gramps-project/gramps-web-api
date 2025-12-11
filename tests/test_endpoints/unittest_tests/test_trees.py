#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David Straub
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
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL


class TestTrees(unittest.TestCase):
    """Test cases for the /api/trees endpoints."""

    def setUp(self):
        self.name = "Test Web API"
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
            add_user(
                name="owner",
                password="123",
                email="owner@example.com",
                role=ROLE_OWNER,
                tree=self.tree,
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

    def test_list_trees_admin(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]
        rv = self.client.get(
            BASE_URL + "/trees/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        trees = rv.json
        trees_dict = {tree["id"]: tree["name"] for tree in trees}
        assert trees_dict[self.tree] == self.name
        # admin can see more trees
        assert len(trees) > 1

    def test_list_trees_owner(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        token = rv.json["access_token"]
        rv = self.client.get(
            BASE_URL + "/trees/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        trees = rv.json
        # owner can see only one tree
        assert trees == [{"id": self.tree, "name": self.name, "enabled": True}]

    def test_get_tree(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        token_owner = rv.json["access_token"]
        rv = self.client.get(
            BASE_URL + "/trees/..", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 422
        # owner should get a 403 for non existing tree - not authorized
        rv = self.client.get(
            BASE_URL + "/trees/notexist",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 403
        # admin should get 404 thouogh
        rv = self.client.get(
            BASE_URL + "/trees/notexist", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 404
        rv = self.client.get(
            BASE_URL + f"/trees/{self.tree}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        assert rv.json == {"name": self.name, "id": self.tree, "enabled": True}

    def test_post_tree(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        token = rv.json["access_token"]
        # wrong parameter name
        rv = self.client.post(
            BASE_URL + "/trees/",
            headers={"Authorization": f"Bearer {token}"},
            json={"value": "some name"},
        )
        assert rv.status_code == 422
        # missing authorization
        rv = self.client.post(
            BASE_URL + "/trees/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "some name"},
        )
        assert rv.status_code == 403
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]
        # OK
        rv = self.client.post(
            BASE_URL + "/trees/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "some name", "quota_media": 1000000},
        )
        assert rv.status_code == 201
        assert rv.json["id"]
        assert rv.json["name"] == "some name"
        assert rv.json["quota_media"] == 1000000
        assert rv.json["quota_people"] is None
        assert rv.json["enabled"]

    def test_rename_tree(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        token_owner = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/trees/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "my old name"},
        )
        assert rv.status_code == 201
        tree_id = rv.json["id"]
        # missing authorization
        rv = self.client.put(
            BASE_URL + f"/trees/{tree_id}",
            headers={"Authorization": f"Bearer {token_owner}"},
            json={"name": "my new name"},
        )
        assert rv.status_code == 403
        # OK
        rv = self.client.put(
            BASE_URL + f"/trees/{tree_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "my new name"},
        )
        assert rv.status_code == 200
        assert rv.json == {"old_name": "my old name", "new_name": "my new name"}

    def test_disable_tree(self):
        # fetch tokens
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        token_owner = rv.json["access_token"]
        token_owner_refresh = rv.json["refresh_token"]
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        # owner can't disable
        rv = self.client.post(
            BASE_URL + f"/trees/{self.tree}/disable",
            headers={"Authorization": f"Bearer {token_owner}"},
        )
        assert rv.status_code == 403
        # admin can disable
        rv = self.client.post(
            BASE_URL + f"/trees/{self.tree}/disable",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 201
        # token does not work
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 503
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {token_owner_refresh}"},
        )
        assert rv.status_code == 503
        rv = self.client.post(
            BASE_URL + f"/trees/{self.tree}/enable",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 201
        # works again
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {token_owner_refresh}"},
        )
        assert rv.status_code == 200
        # and disable again
        rv = self.client.post(
            BASE_URL + f"/trees/{self.tree}/disable",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 201
        # token does not work
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 503
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {token_owner_refresh}"},
        )
        assert rv.status_code == 503
        rv = self.client.post(
            BASE_URL + f"/trees/{self.tree}/enable",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 201
        # works again
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "owner", "password": "123"}
        )
        assert rv.status_code == 200
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {token_owner_refresh}"},
        )
        assert rv.status_code == 200

    def test_disable_nonexistant_tree(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "123"}
        )
        assert rv.status_code == 200
        token_admin = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/trees/idontexist/disable",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert rv.status_code == 404
