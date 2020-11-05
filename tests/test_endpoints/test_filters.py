"""Tests for the /api/filters endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from gramps_webapi.const import GRAMPS_NAMESPACES

from . import API_SCHEMA, get_test_client


class TestFilters(unittest.TestCase):
    """Test cases for the /api/filters/{namespace} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_404(self):
        """Test response for unsupported namespace."""
        # check 404 returned for non-existent namespace
        rv = self.client.get("/api/filters/nothing")
        assert rv.status_code == 404

    def test_filters_endpoint_schema(self):
        """Test all namespaces against the filters schema."""
        for namespace in GRAMPS_NAMESPACES:
            rv = self.client.get("/api/filters/" + namespace)
            # check no custom filters present yet
            assert rv.json["filters"] == []
            # check rules were returned
            assert "rules" in rv.json
            # check all rule records found conform to expected schema
            resolver = RefResolver(
                base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA}
            )
            for rule in rv.json["rules"]:
                validate(
                    instance=rule,
                    schema=API_SCHEMA["definitions"]["FilterRuleDescription"],
                    resolver=resolver,
                )
