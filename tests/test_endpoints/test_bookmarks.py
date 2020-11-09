"""Tests for the /api/bookmarks endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from tests.test_endpoints import API_SCHEMA, get_test_client


class TestBookmarks(unittest.TestCase):
    """Test cases for the /api/bookmarks endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_bookmarks_endpoint_schema(self):
        """Test bookmarks against the bookmark schema."""
        # check response conforms to schema
        result = self.client.get("/api/bookmarks/")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Bookmarks"],
            resolver=resolver,
        )
        # check bad entry returns 404
        result = self.client.get("/api/bookmarks/junk")
        self.assertEqual(result.status_code, 404)
        # check valid response returned for families
        result = self.client.get("/api/bookmarks/families")
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.json[0], str)
