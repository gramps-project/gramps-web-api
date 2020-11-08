"""Tests for the /api/types endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestTypes(unittest.TestCase):
    """Test cases for the /api/types endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_types_endpoint(self):
        """Test response for types listing."""
        # check expected number of type classes found
        result = self.client.get("/api/types/")
        self.assertEqual(len(result.json), 2)
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json["default"],
            schema=API_SCHEMA["definitions"]["DefaultTypes"],
            resolver=resolver,
        )
        validate(
            instance=result.json["custom"],
            schema=API_SCHEMA["definitions"]["CustomTypes"],
            resolver=resolver,
        )


class TestDefaultTypes(unittest.TestCase):
    """Test cases for the /api/types/default endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_default_types_endpoint(self):
        """Test response for default types listing."""
        # check expected number of record types found
        result = self.client.get("/api/types/default/")
        self.assertGreaterEqual(len(result.json), 16)
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["DefaultTypes"],
            resolver=resolver,
        )

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
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["CustomTypes"],
            resolver=resolver,
        )

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
