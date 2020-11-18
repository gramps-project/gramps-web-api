"""Tests for the /api/metadata endpoint using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestMetadata(unittest.TestCase):
    """Test cases for the /api/metadata endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_metadata_endpoint_schema(self):
        """Test response for default types listing."""
        # check expected number of record types found
        result = self.client.get("/api/metadata/")
        self.assertEqual(result.status_code, 200)
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Metadata"],
            resolver=resolver,
        )
