#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the /api/name-groups endpoint using example_gramps."""

import unittest

from gramps_webapi.auth.const import ROLE_MEMBER

from . import BASE_URL, get_test_client
from .checks import check_conforms_to_schema, check_requires_token, check_success
from .util import fetch_header

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


class TestNameGroupsSurnameGroup(unittest.TestCase):
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
        header = fetch_header(self.client)
        rv = self.client.post(TEST_URL + "Stephen", headers=header)
        self.assertEqual(rv.status_code, 400)
        rv = self.client.post(TEST_URL + "Stephen/", headers=header)
        self.assertEqual(rv.status_code, 404)

    def test_post_name_groups_surname_insufficient_authorization(self):
        """Test adding a mapping."""
        header = fetch_header(self.client, role=ROLE_MEMBER)
        rv = self.client.post(TEST_URL + "Stephen/Steven", headers=header)
        self.assertEqual(rv.status_code, 403)

    def test_post_name_groups_surname_add_mapping(self):
        """Test adding a mapping."""
        header = fetch_header(self.client)
        rv = self.client.post(TEST_URL + "Stephen/Steven", headers=header)
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, TEST_URL + "Stephen")
        self.assertEqual(rv, {"surname": "Stephen", "group": "Steven"})
        rv = check_success(self, TEST_URL + "Steven")
        self.assertEqual(rv, {"surname": "Steven", "group": "Steven"})
