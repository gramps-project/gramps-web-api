"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestMediaObjects(unittest.TestCase):
    """Test cases for the /api/media endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_media_endpoint_schema(self):
        """Test all media objects against the media schema."""
        rv = self.client.get("/api/media/?extend=all&profile")
        # check expected number of media objects found
        assert len(rv.json) == get_object_count("media")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for media in rv.json:
            validate(
                instance=media,
                schema=API_SCHEMA["definitions"]["Media"],
                resolver=resolver,
            )
