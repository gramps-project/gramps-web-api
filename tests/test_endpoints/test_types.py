"""Tests for the /api/types endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestDefaultTypes(unittest.TestCase):
    """Test cases for the /api/types/default endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_default_types_endpoint(self):
        """Test response for default types listing."""
        # check expected number of types found
        result = self.client.get("/api/types/default/")
        self.assertGreaterEqual(len(result.json), 16)
        # check first record is expected type
        self.assertEqual(result.json[0], "attribute_types")
        # check last record is expected type
        last = len(result.json) - 1
        self.assertEqual(result.json[last], "url_types")

    def test_default_types_type_endpoint(self):
        """Test response for default types type listing."""
        # check valid response for each type in listing
        type_list = self.client.get("/api/types/default/")
        for item in type_list.json:
            result = self.client.get("/api/types/default/" + item)
            self.assertEqual(result.status_code, 200)
        # check 404 for invalid type
        result = self.client.get("/api/types/default/junk")
        self.assertEqual(result.status_code, 404)

    def test_default_types_type_map_endpoint(self):
        """Test response for default types type map listing."""
        # check valid response for each type in listing
        type_list = self.client.get("/api/types/default/")
        for item in type_list.json:
            result = self.client.get("/api/types/default/" + item + "/map")
            self.assertEqual(result.status_code, 200)
            self.assertIsInstance(result.json, type({}))
        # check 404 for invalid path
        result = self.client.get("/api/types/default/junk/map")
        self.assertEqual(result.status_code, 404)
        result = self.client.get("/api/types/default/event_type/junk")
        self.assertEqual(result.status_code, 404)


class TestCustomTypes(unittest.TestCase):
    """Test cases for the /api/types/custom endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_custom_types_endpoint(self):
        """Test response for custom types listing."""
        # check expected number of types found
        result = self.client.get("/api/types/custom/")
        self.assertGreaterEqual(len(result.json), 16)
        # check first record is expected type
        self.assertEqual(result.json[0], "child_reference_types")
        # check last record is expected type
        last = len(result.json) - 1
        self.assertEqual(result.json[last], "url_types")

    def test_custom_types_type_endpoint(self):
        """Test response for custom types type listing."""
        # check valid response for each type in listing
        type_list = self.client.get("/api/types/custom/")
        for item in type_list.json:
            result = self.client.get("/api/types/custom/" + item)
            self.assertEqual(result.status_code, 200)
        # check 404 for invalid type
        result = self.client.get("/api/types/custom/junk")
        self.assertEqual(result.status_code, 404)
