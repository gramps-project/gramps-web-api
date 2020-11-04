"""Tests for the `gramps_webapi.api` module."""

import unittest

import yaml
from jsonschema import Draft4Validator, validate
from pkg_resources import resource_filename


class TestSchema(unittest.TestCase):
    """Test cases to validate schema format."""

    def test_schema(self):
        """Check schema for validity."""
        # check it loads okay
        with open(
            resource_filename("gramps_webapi", "data/apispec.yaml")
        ) as file_handle:
            api_schema = yaml.safe_load(file_handle)
        # check structure
        Draft4Validator.check_schema(api_schema)
