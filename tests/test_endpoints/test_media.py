"""Tests for the /api/media endpoints using example_gramps."""

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


class TestMedia(unittest.TestCase):
    """Test cases for the /api/media endpoint for a list of media."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_media_endpoint(self):
        """Test reponse for media."""
        # check expected number of media found
        rv = self.client.get("/api/media/")
        assert len(rv.json) == get_object_count("media")
        # check first record is expected media
        assert rv.json[0]["gramps_id"] == "O0010"
        assert rv.json[0]["handle"] == "238CGQ939HG18SS5MG"
        assert rv.json[0]["path"] == "1897_expeditionsmannschaft_rio_a.jpg"
        # check last record is expected media
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "O0000"
        assert rv.json[last]["handle"] == "b39fe1cfc1305ac4a21"
        assert rv.json[last]["path"] == "scanned_microfilm.png"

    def test_media_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/media/?junk_parm=1")
        assert rv.status_code == 422

    def test_media_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "O0006",
            "handle": "F0QIGQFT275JFJ75E8",
            "path": "Alimehemet.jpg",
        }
        run_test_endpoint_gramps_id(self.client, "/api/media/", driver)

    def test_media_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/media/")

    def test_media_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self.client, "/api/media/", ["checksum", "path", "mime"])

    def test_media_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/media/", ["citation_list", "desc", "tag_list"]
        )

    def test_media_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"MediaPrivate"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"MediaPrivate"}]}',
                '{"function":"none","rules":[{"name":"MediaPrivate"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"MediaPrivate"}]}',
                '{"rules":[{"name":"HasTag","values":["ToDo"]},{"name":"MediaPrivate"}]}',
                '{"function":"or","rules":[{"name":"HasTag","values":["ToDo"]},{"name":"MediaPrivate"}]}',
                '{"function":"xor","rules":[{"name":"HasTag","values":["ToDo"]},{"name":"MediaPrivate"}]}',
                '{"function":"one","rules":[{"name":"HasTag","values":["ToDo"]},{"name":"MediaPrivate"}]}',
                '{"invert":true,"rules":[{"name":"MediaPrivate"}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/media/", driver)

    def test_media_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/media/", driver, ["O0006"])

    def test_media_endpoint_schema(self):
        """Test all media against the media schema."""
        rv = self.client.get("/api/media/?extend=all")
        # check expected number of media found
        assert len(rv.json) == get_object_count("media")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for media in rv.json:
            validate(
                instance=media,
                schema=API_SCHEMA["definitions"]["Media"],
                resolver=resolver,
            )


class TestMediaHandle(unittest.TestCase):
    """Test cases for the /api/media/{handle} endpoint for specific media."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_media_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent media
        rv = self.client.get("/api/media/does_not_exist")
        assert rv.status_code == 404

    def test_media_handle_endpoint(self):
        """Test response for specific media."""
        # check expected media returned
        rv = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM")
        assert rv.json["gramps_id"] == "O0008"
        assert rv.json["path"] == "654px-Aksel_Andersson.jpg"

    def test_media_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM?junk_parm=1")
        assert rv.status_code == 422

    def test_media_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/media/B1AUFQV7H8R9NR4SZM")

    def test_media_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/media/B1AUFQV7H8R9NR4SZM",
            ["handle", "attribute_list", "path"],
        )

    def test_media_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/media/B1AUFQV7H8R9NR4SZM",
            ["handle", "note_list", "private"],
        )

    def test_media_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/media/B1AUFQV7H8R9NR4SZM", driver)

    def test_media_handle_endpoint_schema(self):
        """Test the media schema with extensions."""
        # check media record conforms to expected schema
        rv = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Media"],
            resolver=resolver,
        )
