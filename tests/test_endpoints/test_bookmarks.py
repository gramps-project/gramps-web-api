"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestBookmarks(unittest.TestCase):
    """Test cases for the /api/bookmarks endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_bookmarks_endpoint_schema(self):
        """Test bookmarks against the bookmark schema."""
        rv = self.client.get("/api/bookmarks/")
        # check one response returned for namespace list
        assert len(rv.json) == 1
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["NameSpaces"],
            resolver=resolver,
        )
        rv = self.client.get("/api/bookmarks/families")
        # check one response returned for families
        assert len(rv.json) == 1
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Bookmarks"],
            resolver=resolver,
        )
        rv = self.client.get("/api/bookmarks/people")
        # check one response returned for people
        assert len(rv.json) == 1
        # check record conforms to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Bookmarks"],
            resolver=resolver,
        )
