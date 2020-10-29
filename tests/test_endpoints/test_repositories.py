"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestRepositories(unittest.TestCase):
    """Test cases for the /api/repositories endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_repositories_endpoint_schema(self):
        """Test all repositories against the repository schema."""
        rv = self.client.get("/api/repositories/?extend=all&profile")
        # check expected number of repositories found
        assert len(rv.json) == get_object_count("repositories")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for repository in rv.json:
            validate(
                instance=repository,
                schema=API_SCHEMA["definitions"]["Repository"],
                resolver=resolver,
            )
