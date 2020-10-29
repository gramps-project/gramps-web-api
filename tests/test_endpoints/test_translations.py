"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestTranslations(unittest.TestCase):
    """Test cases for the /api/translations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_translations_endpoint_schema(self):
        """Test all translations against the translation schema."""
        rv = self.client.get("/api/translations/")
        # check expected number of translations found
        assert len(rv.json) >= 39
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for translation in rv.json:
            validate(
                instance=translation,
                schema=API_SCHEMA["definitions"]["Translation"],
                resolver=resolver,
            )
