"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestPlaces(unittest.TestCase):
    """Test cases for the /api/places endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_places_endpoint_schema(self):
        """Test all places against the place schema."""
        rv = self.client.get("/api/places/?extend=all&profile")
        # check expected number of places found
        assert len(rv.json) == get_object_count("places")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for place in rv.json:
            validate(
                instance=place,
                schema=API_SCHEMA["definitions"]["Place"],
                resolver=resolver,
            )
