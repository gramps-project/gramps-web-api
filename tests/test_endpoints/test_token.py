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

from tests.test_endpoints import get_test_client


class TestToken(unittest.TestCase):
    """Test cases for the /api/login and /api/refresh endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_token_endpoint(self):
        """Test login endpoint."""
        result = self.client.post("/api/login/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, {"access_token": 1, "refresh_token": 1})

    def test_refresh_token_endpoint(self):
        """Test refresh endpoint."""
        result = self.client.post("/api/refresh/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, {"access_token": 1})
