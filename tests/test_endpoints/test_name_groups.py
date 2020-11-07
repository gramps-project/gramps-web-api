"""Tests for the /api/name-groups endpoint using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestNameGroups(unittest.TestCase):
    """Test cases for the /api/name-groups endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_name_groups_endpoint(self):
        """Test name groups."""
        # check response returned for name groups listing
        result = self.client.get("/api/name-groups/")
        self.assertEqual(result.json[0], {"surname": "Fernández", "group": "Fernandez"})
        # check response returned for specific surname
        result = self.client.get("/api/name-groups/Fernández")
        self.assertEqual(result.json, {"surname": "Fernández", "group": "Fernandez"})
        # check response setting incomplete new group mapping
        result = self.client.post("/api/name-groups/Stephen")
        self.assertEqual(result.status_code, 400)
        result = self.client.post("/api/name-groups/Stephen/")
        self.assertEqual(result.status_code, 404)
        # check response setting new group mapping
        result = self.client.post("/api/name-groups/Stephen/Steven")
        self.assertEqual(result.status_code, 201)
        # check response returned for surname group mapping just created
        result = self.client.get("/api/name-groups/Stephen")
        self.assertEqual(result.json, {"surname": "Stephen", "group": "Steven"})
        result = self.client.get("/api/name-groups/Steven")
        self.assertEqual(result.json, {"surname": "Steven", "group": "Steven"})

    def test_name_groups_endpoint_schema(self):
        """Test name groups against the name group schema."""
        # check record conforms to expected schema
        result = self.client.get("/api/name-groups/")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for group in result.json:
            validate(
                instance=group,
                schema=API_SCHEMA["definitions"]["NameGroupMapping"],
                resolver=resolver,
            )
