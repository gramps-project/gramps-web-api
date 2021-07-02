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

"""Tests for the `gramps_webapi.api` module."""

import unittest

from gramps_webapi.auth.const import ROLE_OWNER

from . import BASE_URL, TEST_USERS, get_test_client


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
