"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client


class TestNotes(unittest.TestCase):
    """Test cases for the /api/notes endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_notes_endpoint_schema(self):
        """Test all notes against the note schema."""
        rv = self.client.get("/api/notes/?extend=all&profile")
        # check expected number of notes found
        assert len(rv.json) == get_object_count("notes")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for note in rv.json:
            validate(
                instance=note,
                schema=API_SCHEMA["definitions"]["Note"],
                resolver=resolver,
            )
