#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the /api/name-groups endpoint using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_invalid_syntax,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_token

TEST_URL = BASE_URL + "/name-groups/"


class TestNameGroups(unittest.TestCase):
    """Test cases for the /api/name-groups endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_name_groups_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_name_groups_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "NameGroupMapping")


class TestNameGroupsSurname(unittest.TestCase):
    """Test cases for the /api/name-groups/{surname} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_name_groups_surname_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "Fernández")

    def test_get_name_groups_surname_expected_result(self):
        """Test response querying surname."""
        rv = check_success(self, TEST_URL + "Fernández")
        self.assertEqual(rv, {"surname": "Fernández", "group": "Fernandez"})


class TestNameGroupsSurname(unittest.TestCase):
    """Test cases for the /api/name-groups/{surname}/{group} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_post_name_groups_surname_requires_token(self):
        """Test authorization required."""
        rv = self.client.post(TEST_URL + "Stephen/Steven")
        self.assertEqual(rv.status_code, 401)

    def test_post_name_groups_surname_bad_mapping(self):
        """Test adding a incomplete mapping."""
        token, headers = fetch_token(self.client)
        rv = self.client.post(TEST_URL + "Stephen", headers=headers)
        self.assertEqual(rv.status_code, 400)
        rv = self.client.post(TEST_URL + "Stephen/", headers=headers)
        self.assertEqual(rv.status_code, 404)

    def test_post_name_groups_surname_add_mapping(self):
        """Test adding a mapping."""
        token, headers = fetch_token(self.client)
        rv = self.client.post(TEST_URL + "Stephen/Steven", headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, TEST_URL + "Stephen")
        self.assertEqual(rv, {"surname": "Stephen", "group": "Steven"})
        rv = check_success(self, TEST_URL + "Steven")
        self.assertEqual(rv, {"surname": "Steven", "group": "Steven"})
