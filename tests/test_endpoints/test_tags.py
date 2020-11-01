"""Tests for the /api/tags endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestTags(unittest.TestCase):
    """Test cases for the /api/tags endpoint for a list of tags."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tags_endpoint(self):
        """Test response for tags."""
        # check expected number of tags found
        rv = self.client.get("/api/tags/")
        assert len(rv.json) == get_object_count("tags")
        # check first record is expected tag
        assert rv.json[0]["name"] == "complete"
        # check last record is expected tag
        last = len(rv.json) - 1
        assert rv.json[last]["name"] == "ToDo"

    def test_tags_endpoint_schema(self):
        """Test all tags against the tag schema."""
        # check all records found conform to expected schema
        rv = self.client.get("/api/tags/")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for tag in rv.json:
            validate(
                instance=tag, schema=API_SCHEMA["definitions"]["Tag"], resolver=resolver
            )


class TestTagsHandle(unittest.TestCase):
    """Test cases for the /api/tags/{handle} endpoint for a tag."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tags_handle_endpoint_404(self):
        """Test non-existent tag response."""
        # check 404 returned for non-existent tag
        rv = self.client.get("/api/tags/does_not_exist")
        assert rv.status_code == 404

    def test_tags_handle_endpoint(self):
        """Test tag response."""
        # check expected tag returned
        rv = self.client.get("/api/tags/bb80c2b235b0a1b3f49")
        assert rv.json["name"] == "ToDo"
