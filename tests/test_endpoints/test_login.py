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

"""Tests for the `gramps_webapi.api` module."""

import unittest

from gramps_webapi.auth.const import ROLE_OWNER

from . import BASE_URL, TEST_USERS, get_test_client


class TestLogin(unittest.TestCase):
    """Test cases for the /api/login endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_login_no_credentials(self):
        """Test login response no credentials."""
        rv = self.client.post(BASE_URL + "/login/")
        self.assertEqual(rv.status_code, 401)

    def test_login_wrong_password(self):
        """Test login response for wrong password."""
        rv = self.client.post(
            BASE_URL + "/login/",
            json={"username": TEST_USERS[ROLE_OWNER]["name"], "password": "notreal"},
        )
        self.assertEqual(rv.status_code, 403)

    def test_login_wrong_username(self):
        """Test login response for wrong username."""
        rv = self.client.post(
            BASE_URL + "/login/",
            json={
                "username": "notreal",
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 403)

    def test_login_response(self):
        """Test login response."""
        rv = self.client.post(
            BASE_URL + "/login/",
            json={
                "username": TEST_USERS[ROLE_OWNER]["name"],
                "password": TEST_USERS[ROLE_OWNER]["password"],
            },
        )
        self.assertEqual(rv.status_code, 200)
        self.assertIn("access_token", rv.json)
        self.assertIn("refresh_token", rv.json)
