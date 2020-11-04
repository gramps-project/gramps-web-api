"""Tests for the /api/citations endpoints using example_gramps."""

import unittest
from typing import Dict, List

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


class TestCitations(unittest.TestCase):
    """Test cases for the /api/citations endpoint for a list of citations."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_citations_endpoint(self):
        """Test reponse for citations."""
        # check expected number of citations found
        rv = self.client.get("/api/citations/")
        assert len(rv.json) == get_object_count("citations")
        # check first record is expected citation
        assert rv.json[0]["gramps_id"] == "C0000"
        assert rv.json[0]["handle"] == "c140d2362f25a92643b"
        assert rv.json[0]["source_handle"] == "b39fe3f390e30bd2b99"
        # check last record is expected citation
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "C2853"
        assert rv.json[last]["handle"] == "c140e0925ac0adcf8c4"
        assert rv.json[last]["source_handle"] == "c140d4ef77841431905"

    def test_citations_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/citations/?junk_parm=1")
        assert rv.status_code == 422

    def test_citations_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "C2849",
            "handle": "c140dde678c5c4f4537",
            "source_handle": "c140d4ef77841431905",
        }
        run_test_endpoint_gramps_id(self.client, "/api/citations/", driver)

    def test_citations_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/citations/")

    def test_citations_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/citations/", ["confidence", "handle", "page"]
        )

    def test_citations_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/citations/", ["change", "media_list", "tag_list"]
        )

    def test_citations_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasNote"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasNote"}]}',
                '{"function":"none","rules":[{"name":"HasNote"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasNote"}]}',
                '{"rules":[{"name":"MatchesPageSubstringOf","values":["Page"]},{"name":"HasNote"}]}',
                '{"function":"or","rules":[{"name":"MatchesPageSubstringOf","values":["Page"]},{"name":"HasNote"}]}',
                '{"function":"xor","rules":[{"name":"MatchesPageSubstringOf","values":["Page"]},{"name":"HasNote"}]}',
                '{"function":"one","rules":[{"name":"MatchesPageSubstringOf","values":["Page"]},{"name":"HasNote"}]}',
                '{"invert":true,"rules":[{"name":"HasNote"}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/citations/", driver)

    def test_citations_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "source_handle", "key": "source", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/citations/", driver, ["C2849"])

    def test_citations_endpoint_schema(self):
        """Test all citations against the citation schema."""
        rv = self.client.get("/api/citations/?extend=all")
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


class TestCitationsHandle(unittest.TestCase):
    """Test cases for the /api/citations/{handle} endpoint for a specific citation."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_citations_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent citation
        rv = self.client.get("/api/citations/does_not_exist")
        assert rv.status_code == 404

    def test_citations_handle_endpoint(self):
        """Test response for specific citation."""
        # check expected citation returned
        rv = self.client.get("/api/citations/c140db880395cadf318")
        assert rv.json["gramps_id"] == "C2844"
        assert rv.json["source_handle"] == "c140d4ef77841431905"

    def test_citations_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/citations/c140db880395cadf318?junk_parm=1")
        assert rv.status_code == 422

    def test_citations_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/citations/c140db880395cadf318")

    def test_citations_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/citations/c140db880395cadf318",
            ["handle", "page", "private"],
        )

    def test_citations_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/citations/c140db880395cadf318",
            ["handle", "media_list", "tag_list"],
        )

    def test_citations_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "source_handle", "key": "source", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(
            self.client, "/api/citations/c140db880395cadf318", driver
        )

    def test_citations_handle_endpoint_schema(self):
        """Test the citation schema with extensions."""
        # check citation record conforms to expected schema
        rv = self.client.get("/api/citations/c140db880395cadf318?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Citation"],
            resolver=resolver,
        )
