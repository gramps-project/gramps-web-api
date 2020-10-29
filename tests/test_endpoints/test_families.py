"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestFamilies(unittest.TestCase):
    """Test cases for the /api/families endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_families_endpoint_schema(self):
        """Test all families against the family schema."""
        rv = self.client.get("/api/families/?extend=all&profile")
        # check expected number of families found
        assert len(rv.json) == get_object_count("families")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for family in rv.json:
            validate(
                instance=family,
                schema=API_SCHEMA["definitions"]["Family"],
                resolver=resolver,
            )
