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

from gramps_webapi.api.resources.metadata import _parse_rate_limit
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_GUEST

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

    def test_get_metadata_server_capabilities(self):
        """Test the server block reports capabilities and client-relevant config."""
        res = check_conforms_to_openapi_schema(self, TEST_URL, "Metadata")
        server = res["server"]
        for key in [
            "multi_tree",
            "task_queue",
            "ocr",
            "semantic_search",
            "chat",
            "face_detection",
            "email",
        ]:
            self.assertIsInstance(server[key], bool, key)
        self.assertIsInstance(server["ocr_languages"], list)
        self.assertIsInstance(server["thumbnails"]["pdf"], bool)
        self.assertIsInstance(server["thumbnails"]["video"], bool)
        self.assertIsInstance(server["max_thumbnail_file_bytes"], int)
        # the rate limit mini-language is parsed server-side into amount per window
        self.assertEqual(
            server["rate_limit_media_archive"],
            [{"amount": 1, "window_seconds": 86400}],
        )
        # no upload limit is configured in the test config, so the key is omitted
        self.assertNotIn("max_media_archive_upload_bytes", server)

    def test_get_metadata_server_visible_to_guest(self):
        """Test that the server block is returned for the lowest role, too."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        rv = self.client.get(TEST_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("email", rv.json["server"])
        self.assertIn("max_thumbnail_file_bytes", rv.json["server"])
        # deprecations remain restricted to users allowed to view settings
        self.assertNotIn("deprecations", rv.json)


class TestParseRateLimit(unittest.TestCase):
    """Test cases for parsing rate limit strings."""

    def test_parse_rate_limit_forms(self):
        """Test the equivalent forms of the rate limit mini-language."""
        for limit_string in ["1 per day", "1/day", "1 per 1 day"]:
            self.assertEqual(
                _parse_rate_limit(limit_string),
                [{"amount": 1, "window_seconds": 86400}],
                limit_string,
            )

    def test_parse_rate_limit_multiples(self):
        """Test a window spanning multiple units."""
        self.assertEqual(
            _parse_rate_limit("2 per 5 minutes"),
            [{"amount": 2, "window_seconds": 300}],
        )

    def test_parse_rate_limit_multiple_limits(self):
        """Test that several simultaneous limits are all reported."""
        self.assertEqual(
            _parse_rate_limit("100/hour;1000/day"),
            [
                {"amount": 100, "window_seconds": 3600},
                {"amount": 1000, "window_seconds": 86400},
            ],
        )

    def test_parse_rate_limit_invalid(self):
        """Test that an unparseable limit does not raise."""
        self.assertIsNone(_parse_rate_limit("once in a blue moon"))


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
