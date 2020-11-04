"""Tests for the /api/sources endpoints using example_gramps."""

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


class TestSources(unittest.TestCase):
    """Test cases for the /api/sources endpoint for a list of sources."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_sources_endpoint(self):
        """Test reponse for sources."""
        # check expected number of sources found
        rv = self.client.get("/api/sources/")
        assert len(rv.json) == get_object_count("sources")
        # check first record is expected source
        assert rv.json[0]["gramps_id"] == "S0002"
        assert rv.json[0]["handle"] == "VUBKMQTA2XZG1V6QP8"
        assert rv.json[0]["title"] == "World of the Wierd"
        # check last record is expected source
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "S0001"
        assert rv.json[last]["handle"] == "c140d4ef77841431905"
        assert rv.json[last]["title"] == "All possible citations"

    def test_sources_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/sources/?junk_parm=1")
        assert rv.status_code == 422

    def test_sources_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "S0000",
            "handle": "b39fe3f390e30bd2b99",
            "title": "Baptize registry 1850 - 1867 Great Falls Church",
        }
        run_test_endpoint_gramps_id(self.client, "/api/sources/", driver)

    def test_sources_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/sources/")

    def test_sources_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/sources/", ["author", "pubinfo", "title"]
        )

    def test_sources_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/sources/", ["abbrev", "reporef_list", "tag_list"]
        )

    def test_sources_endpoint_rules(self):
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
                '{"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"HasNote"}]}',
                '{"function":"or","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"HasNote"}]}',
                '{"function":"xor","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"HasNote"}]}',
                '{"function":"one","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"HasNote"}]}',
                '{"invert":true,"rules":[{"name":"HasNote"}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/sources/", driver)

    def test_sources_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "reporef_list", "key": "repositories", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/sources/", driver, ["S0000"])

    def test_sources_endpoint_schema(self):
        """Test all sources against the source schema."""
        rv = self.client.get("/api/sources/?extend=all")
        # check expected number of sources found
        assert len(rv.json) == get_object_count("sources")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for source in rv.json:
            validate(
                instance=source,
                schema=API_SCHEMA["definitions"]["Source"],
                resolver=resolver,
            )


class TestSourcesHandle(unittest.TestCase):
    """Test cases for the /api/sources/{handle} endpoint for a specific source."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_sources_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent source
        rv = self.client.get("/api/sources/does_not_exist")
        assert rv.status_code == 404

    def test_sources_handle_endpoint(self):
        """Test response for specific source."""
        # check expected source returned
        rv = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX")
        assert rv.json["gramps_id"] == "S0003"
        assert rv.json["title"] == "Import from test2.ged"

    def test_sources_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX?junk_parm=1")
        assert rv.status_code == 422

    def test_sources_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/sources/X5TJQC9JXU4RKT6VAX")

    def test_sources_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/sources/X5TJQC9JXU4RKT6VAX",
            ["handle", "pubinfo", "title"],
        )

    def test_sources_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/sources/X5TJQC9JXU4RKT6VAX",
            ["handle", "media_list", "private"],
        )

    def test_sources_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "reporef_list", "key": "repositories", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/sources/X5TJQC9JXU4RKT6VAX", driver)

    def test_sources_handle_endpoint_schema(self):
        """Test the source schema with extensions."""
        # check source record conforms to expected schema
        rv = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Source"],
            resolver=resolver,
        )
