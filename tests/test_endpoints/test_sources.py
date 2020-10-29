"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestSources(unittest.TestCase):
    """Test cases for the /api/sources endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_sources_endpoint_schema(self):
        """Test all sources against the source schema."""
        rv = self.client.get("/api/sources/?extend=all&profile")
        # check expected number of sources found
        assert len(rv.json) == get_object_count("sources")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for source in rv.json:
            validate(
                instance=source,
                schema=API_SCHEMA["definitions"]["Source"],
                resolver=resolver,
            )
