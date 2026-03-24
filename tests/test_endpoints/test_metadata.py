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

"""Tests for the /api/metadata endpoint using example_gramps."""

import unittest

from gramps_webapi.auth.const import ROLE_EDITOR

from . import BASE_URL, get_test_client
from .checks import check_conforms_to_openapi_schema, check_requires_token
from .util import fetch_header

TEST_URL = BASE_URL + "/metadata/"
TEST_RESEARCHER_URL = BASE_URL + "/metadata/researcher/"


class TestMetadata(unittest.TestCase):
    """Test cases for the /api/metadata endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_metadata_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_metadata_conforms_to_schema(self):
        """Test conforms to schema."""
        res = check_conforms_to_openapi_schema(self, TEST_URL, "Metadata")
        assert res["database"]["type"] == "sqlite"
        assert "search" in res
        assert "sifts" in res["search"]
        assert "version" in res["search"]["sifts"]
        assert "count" in res["search"]["sifts"]
        assert res["search"]["sifts"]["count"] > 1


class TestMetadataResearcher(unittest.TestCase):
    """Test cases for the /api/metadata/researcher/ endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_researcher_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_RESEARCHER_URL)

    def test_get_researcher_conforms_to_schema(self):
        """Test GET conforms to schema."""
        check_conforms_to_openapi_schema(self, TEST_RESEARCHER_URL, "Researcher")

    def test_put_researcher_requires_token(self):
        """Test PUT requires authorization."""
        rv = self.client.put(TEST_RESEARCHER_URL, json={"name": "Test"})
        self.assertEqual(rv.status_code, 401)

    def test_put_researcher_editor_forbidden(self):
        """Test that editor role cannot update researcher info."""
        header = fetch_header(self.client, role=ROLE_EDITOR)
        rv = self.client.put(
            TEST_RESEARCHER_URL,
            json={"name": "Test User"},
            headers=header,
        )
        self.assertEqual(rv.status_code, 403)

    def test_put_researcher_updates_and_returns(self):
        """Test that owner can update researcher info and it is returned."""
        header = fetch_header(self.client)
        payload = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "city": "Springfield",
            "state": "IL",
            "country": "US",
            "phone": "555-1234",
            "addr": "123 Main St",
            "postal": "62701",
        }
        rv = self.client.put(TEST_RESEARCHER_URL, json=payload, headers=header)
        self.assertEqual(rv.status_code, 200)
        data = rv.json
        self.assertEqual(data["name"], "Jane Doe")
        self.assertEqual(data["email"], "jane@example.com")
        self.assertEqual(data["city"], "Springfield")

        # Verify GET returns the updated values
        rv2 = self.client.get(TEST_RESEARCHER_URL, headers=header)
        self.assertEqual(rv2.status_code, 200)
        self.assertEqual(rv2.json["name"], "Jane Doe")
        self.assertEqual(rv2.json["email"], "jane@example.com")
