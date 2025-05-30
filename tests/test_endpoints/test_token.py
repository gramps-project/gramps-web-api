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

"""Tests for the `gramps_webapi.api` module."""

import unittest
from unittest.mock import patch

from flask_jwt_extended.utils import decode_token
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

from . import BASE_URL, TEST_USERS, get_test_client
from .util import fetch_header


class TestToken(unittest.TestCase):
    """Test cases for the /api/token endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_login_no_credentials(self):
        """Test login response no credentials."""
        rv = self.client.post(BASE_URL + "/token/")
        self.assertEqual(rv.status_code, 422)

    def test_login_wrong_password(self):
        """Test login response for wrong password."""
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": TEST_USERS[ROLE_OWNER]["name"], "password": "notreal"},
        )
        self.assertEqual(rv.status_code, 403)

    def test_login_wrong_username(self):
        """Test login response for wrong username."""
        rv = self.client.post(
            BASE_URL + "/token/",
            json={
                "username": "notreal",
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 403)

    def test_login_response(self):
        """Test login response."""
        rv = self.client.post(
            BASE_URL + "/token/",
            json={
                "username": TEST_USERS[ROLE_OWNER]["name"],
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 200)
        self.assertIn("access_token", rv.json)
        self.assertIn("refresh_token", rv.json)

    def test_create_owner_response(self):
        """Test response to create_owner."""
        rv = self.client.get(f"{BASE_URL}/token/create_owner/")
        self.assertEqual(rv.status_code, 405)

    def test_create_owner_post_response(self):
        """Test response to create_owner."""
        rv = self.client.post(f"{BASE_URL}/token/create_owner/")
        self.assertEqual(rv.status_code, 405)

    def test_create_owner_tree_response(self):
        """Test response to create_owner."""
        headers = fetch_header(self.client)
        rv = self.client.get(f"{BASE_URL}/trees/-", headers=headers)
        assert rv.status_code == 200
        tree = rv.json["id"]
        rv = self.client.post(f"{BASE_URL}/token/create_owner/", json={"tree": tree})
        self.assertEqual(rv.status_code, 405)


class TestTokenRefresh(unittest.TestCase):
    """Test cases for the /api/token/refresh endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_refresh_no_header(self):
        """Test refresh response no header."""
        rv = self.client.post(BASE_URL + "/token/refresh/")
        self.assertEqual(rv.status_code, 401)

    def test_refresh_bad_token(self):
        """Test refresh response bad token format."""
        rv = self.client.post(
            BASE_URL + "/token/refresh/", headers={"Authorization": "Bearer invalid"}
        )
        self.assertEqual(rv.status_code, 422)

    def test_refresh_wrong_token(self):
        """Test refresh response wrong token presented."""
        rv = self.client.post(
            BASE_URL + "/token/",
            json={
                "username": TEST_USERS[ROLE_OWNER]["name"],
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 200)
        access_token = rv.json["access_token"]
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": "Bearer {}".format(access_token)},
        )
        self.assertEqual(rv.status_code, 422)

    def test_refresh_response(self):
        """Test refresh response."""
        rv = self.client.post(
            BASE_URL + "/token/",
            json={
                "username": TEST_USERS[ROLE_OWNER]["name"],
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 200)
        refresh_token = rv.json["refresh_token"]
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": "Bearer {}".format(refresh_token)},
        )
        self.assertIn("access_token", rv.json)
        self.assertNotIn("refresh_token", rv.json)


class TestTokenCreateOwner(unittest.TestCase):
    """Test cases for the /api/token/create_owner endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            db_manager = WebDbManager(name=cls.name, create_if_missing=False)
            cls.tree_id = db_manager.dirname

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_create_admin_response_get(self):
        """Test response to create_owner."""
        rv = self.client.get(f"{BASE_URL}/token/create_owner/")
        self.assertEqual(rv.status_code, 200)
        self.assertIn("access_token", rv.json)
        encoded_token = rv.json["access_token"]
        with self.app.app_context():
            token = decode_token(encoded_token)
        assert token["limited_scope"] == "create_admin"

    def test_create_admin_response_post(self):
        """Test response to create_owner."""
        rv = self.client.post(f"{BASE_URL}/token/create_owner/")
        self.assertEqual(rv.status_code, 201)
        self.assertIn("access_token", rv.json)
        encoded_token = rv.json["access_token"]
        with self.app.app_context():
            token = decode_token(encoded_token)
        assert token["limited_scope"] == "create_admin"

    def test_create_admin_response_post_tree_wrong(self):
        """Test response to create_owner."""
        rv = self.client.post(
            f"{BASE_URL}/token/create_owner/", json={"tree": "idontexist"}
        )
        self.assertEqual(rv.status_code, 404)

    def test_create_admin_response_post_tree_empty_string(self):
        """Test response to create_owner."""
        rv = self.client.post(f"{BASE_URL}/token/create_owner/", json={"tree": ""})
        self.assertEqual(rv.status_code, 201)
        self.assertIn("access_token", rv.json)
        encoded_token = rv.json["access_token"]
        with self.app.app_context():
            token = decode_token(encoded_token)
        assert token["limited_scope"] == "create_admin"

    def test_create_admin_response_post_tree(self):
        """Test response to create_owner."""
        rv = self.client.post(
            f"{BASE_URL}/token/create_owner/", json={"tree": self.tree_id}
        )
        self.assertEqual(rv.status_code, 201)
        self.assertIn("access_token", rv.json)
        encoded_token = rv.json["access_token"]
        with self.app.app_context():
            token = decode_token(encoded_token)
        assert token["limited_scope"] == "create_owner"
