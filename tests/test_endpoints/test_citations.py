"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestCitations(unittest.TestCase):
    """Test cases for the /api/citations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_citations_endpoint_schema(self):
        """Test all citations against the citation schema."""
        rv = self.client.get("/api/citations/?extend=all&profile")
        # check expected number of citations found
        assert len(rv.json) == get_object_count("citations")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for citation in rv.json:
            validate(
                instance=citation,
                schema=API_SCHEMA["definitions"]["Citation"],
                resolver=resolver,
            )
