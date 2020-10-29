"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestEvents(unittest.TestCase):
    """Test cases for the /api/events endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_events_endpoint_schema(self):
        """Test all events against the event schema."""
        rv = self.client.get("/api/events/?extend=all&profile")
        # check expected number of events found
        assert len(rv.json) == get_object_count("events")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for event in rv.json:
            validate(
                instance=event,
                schema=API_SCHEMA["definitions"]["Event"],
                resolver=resolver,
            )
