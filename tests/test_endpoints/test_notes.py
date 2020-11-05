"""Tests for the /api/notes endpoints using example_gramps."""

import unittest
from typing import List

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client
from .runners import (
    run_test_endpoint_extend,
    run_test_endpoint_gramps_id,
    run_test_endpoint_keys,
    run_test_endpoint_rules,
    run_test_endpoint_skipkeys,
    run_test_endpoint_strip,
)


class TestNotes(unittest.TestCase):
    """Test cases for the /api/notes endpoint for a list of notes."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_notes_endpoint(self):
        """Test reponse for notes."""
        # check expected number of notes found
        rv = self.client.get("/api/notes/")
        assert len(rv.json) == get_object_count("notes")
        # check first record is expected note
        assert rv.json[0]["gramps_id"] == "N0001"
        assert rv.json[0]["handle"] == "ac380498bac48eedee8"
        assert rv.json[0]["type"] == "Name Note"
        # check last record is expected note
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "_custom1"
        assert rv.json[last]["handle"] == "d0436be64ac277b615b79b34e72"
        assert rv.json[last]["type"] == "General"

    def test_notes_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/notes/?junk_parm=1")
        assert rv.status_code == 422

    def test_notes_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "_header1",
            "handle": "d0436bba4ec328d3b631259a4ee",
            "type": "General",
        }
        run_test_endpoint_gramps_id(self.client, "/api/notes/", driver)

    def test_notes_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/notes/")

    def test_notes_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self.client, "/api/notes/", ["handle", "text", "type"])

    def test_notes_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/notes/", ["change", "format", "tag_list"]
        )

    def test_notes_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasType","values":["Person Note"]}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasType","values":["Person Note"]}]}',
                '{"function":"none","rules":[{"name":"HasType","values":["Person Note"]}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasType","values":["Person Note"]}]}',
                '{"rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"function":"or","rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"function":"xor","rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"function":"one","rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"invert":true,"rules":[{"name":"HasType","values":["Person Note"]}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/notes/", driver)

    def test_notes_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/notes/", driver, ["N0003"])

    def test_notes_endpoint_schema(self):
        """Test all notes against the note schema."""
        rv = self.client.get("/api/notes/?extend=all")
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


class TestNotesHandle(unittest.TestCase):
    """Test cases for the /api/notes/{handle} endpoint for a specific note."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_notes_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent note
        rv = self.client.get("/api/notes/does_not_exist")
        assert rv.status_code == 404

    def test_notes_handle_endpoint(self):
        """Test response for specific note."""
        # check expected note returned
        rv = self.client.get("/api/notes/ac3804aac6b762b75a5")
        assert rv.json["gramps_id"] == "N0008"
        assert rv.json["type"] == "Repository Note"

    def test_notes_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/notes/ac3804aac6b762b75a5?junk_parm=1")
        assert rv.status_code == 422

    def test_notes_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/notes/ac3804aac6b762b75a5")

    def test_notes_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/notes/ac3804aac6b762b75a5",
            ["handle", "text", "type"],
        )

    def test_notes_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/notes/ac3804aac6b762b75a5",
            ["change", "format", "private"],
        )

    def test_notes_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/notes/ac3804aac6b762b75a5", driver)

    def test_notes_handle_endpoint_schema(self):
        """Test the note schema with extensions."""
        # check note record conforms to expected schema
        rv = self.client.get("/api/notes/ac3804aac6b762b75a5?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Note"],
            resolver=resolver,
        )
