"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestTags(unittest.TestCase):
    """Test cases for the /api/tags endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tags_endpoint_404(self):
        """Test non-existent tag response."""
        get_response = self.client.get("/api/tags/does_not_exist")
        assert get_response.status_code == 404

    def test_tags_endpoint(self):
        """Test tags response."""
        get_response = self.client.get("/api/tags/")
        assert len(get_response.json) == 2
        assert get_response.json[0]["name"] == "complete"

    def test_tag_endpoint(self):
        """Test tag response."""
        get_response = self.client.get("/api/tags/bb80c2b235b0a1b3f49")
        assert get_response.json["name"] == "ToDo"

    def test_tags_endpoint_schema(self):
        """Test all tags against the tag schema."""
        rv = self.client.get("/api/tags/")
        # check expected number of tags found
        assert len(rv.json) == get_object_count("tags")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for tag in rv.json:
            validate(
                instance=tag, schema=API_SCHEMA["definitions"]["Tag"], resolver=resolver
            )
