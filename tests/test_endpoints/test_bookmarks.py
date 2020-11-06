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
        # check one response returned for namespace list
        result = self.client.get("/api/bookmarks/")
        self.assertEqual(len(result.json), 1)
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["NameSpaces"],
            resolver=resolver,
        )
        # check one response returned for families
        result = self.client.get("/api/bookmarks/families")
        self.assertEqual(len(result.json), 1)
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Bookmarks"],
            resolver=resolver,
        )
        # check one response returned for people
        result = self.client.get("/api/bookmarks/people")
        self.assertEqual(len(result.json), 1)
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Bookmarks"],
            resolver=resolver,
        )
