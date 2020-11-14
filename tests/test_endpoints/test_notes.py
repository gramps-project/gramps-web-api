"""Tests for the /api/notes endpoints using example_gramps."""

import re
import unittest
from typing import List

from jsonschema import RefResolver, validate

from tests.test_endpoints import API_SCHEMA, get_object_count, get_test_client
from tests.test_endpoints.runners import (
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
        result = self.client.get("/api/notes/")
        self.assertEqual(len(result.json), get_object_count("notes"))
        # check first record is expected note
        self.assertEqual(result.json[0]["gramps_id"], "N0001")
        self.assertEqual(result.json[0]["handle"], "ac380498bac48eedee8")
        self.assertEqual(result.json[0]["type"], "Name Note")
        # check last record is expected note
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "_custom1")
        self.assertEqual(result.json[last]["handle"], "d0436be64ac277b615b79b34e72")
        self.assertEqual(result.json[last]["type"], "General")

    def test_notes_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/notes/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_notes_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "_header1",
            "handle": "d0436bba4ec328d3b631259a4ee",
            "type": "General",
        }
        run_test_endpoint_gramps_id(self, "/api/notes/", driver)

    def test_notes_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/notes/")

    def test_notes_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self, "/api/notes/", ["handle", "text", "type"])

    def test_notes_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/notes/", ["change", "format", "tag_list"]
        )

    def test_notes_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasType","values":["Person Note"]}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasType",'
                + '"values":["Person Note"]}]}',
                '{"function":"none","rules":[{"name":"HasType",'
                + '"values":["Person Note"]}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasType","values":["Person Note"]}]}',
                '{"rules":[{"name":"HasType","values":["Person Note"]},'
                + '{"name":"NotePrivate"}]}',
                '{"function":"or","rules":[{"name":"HasType",'
                + '"values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"function":"xor","rules":[{"name":"HasType",'
                + '"values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"function":"one","rules":[{"name":"HasType",'
                + '"values":["Person Note"]},{"name":"NotePrivate"}]}',
                '{"invert":true,"rules":[{"name":"HasType","values":["Person Note"]}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/notes/", driver)

    def test_notes_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/notes/", driver, ["N0003"])

    def test_notes_endpoint_schema(self):
        """Test all notes against the note schema."""
        result = self.client.get("/api/notes/?extend=all")
        # check expected number of notes found
        self.assertEqual(len(result.json), get_object_count("notes"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for note in result.json:
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
        result = self.client.get("/api/notes/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_notes_handle_endpoint(self):
        """Test response for specific note."""
        # check expected note returned
        result = self.client.get("/api/notes/ac3804aac6b762b75a5")
        self.assertEqual(result.json["gramps_id"], "N0008")
        self.assertEqual(result.json["type"], "Repository Note")

    def test_notes_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/notes/ac3804aac6b762b75a5?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_notes_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/notes/ac3804aac6b762b75a5")

    def test_notes_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self, "/api/notes/ac3804aac6b762b75a5", ["handle", "text", "type"],
        )

    def test_notes_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/notes/ac3804aac6b762b75a5", ["change", "format", "private"],
        )

    def test_notes_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/notes/ac3804aac6b762b75a5", driver)

    def test_notes_handle_endpoint_schema(self):
        """Test the note schema with extensions."""
        # check note record conforms to expected schema
        result = self.client.get("/api/notes/ac3804aac6b762b75a5?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Note"],
            resolver=resolver,
        )

    def test_notes_handle_endpoint_formats_html(self):
        """Test response for formats parm."""
        result = self.client.get("/api/notes/b39ff01f75c1f76859a?formats=html")
        self.assertIn("formatted", result.json)
        self.assertIn("html", result.json["formatted"])
        html = result.json["formatted"]["html"]
        self.assertIsInstance(html, str)
        # strip tags
        html_stripped = re.sub("<[^<]+?>", "", html)
        # strip whitespace
        html_stripped = re.sub(r"\s", "", html_stripped)
        text_stripped = re.sub(r"\s", "", result.json["text"]["string"])
        # the HTML stripped of tags should be equal to the pure text string,
        # up to white space
        assert text_stripped == html_stripped
