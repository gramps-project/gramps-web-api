"""Tests for the /api/repositories endpoints using example_gramps."""

import unittest
from typing import List

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client
from .runners import (
    run_test_endpoint_extend,
    run_test_endpoint_gramps_id,
    run_test_endpoint_keys,
    run_test_endpoint_skipkeys,
    run_test_endpoint_strip,
)


class TestRepositories(unittest.TestCase):
    """Test cases for the /api/repositories endpoint for a list of repositories."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_repositories_endpoint(self):
        """Test reponse for repositories."""
        # check expected number of repositories found
        rv = self.client.get("/api/repositories/")
        assert len(rv.json) == get_object_count("repositories")
        # check first record is expected repository
        assert rv.json[0]["gramps_id"] == "R0002"
        assert rv.json[0]["handle"] == "a701e99f93e5434f6f3"
        assert rv.json[0]["type"] == "Library"
        # check last record is expected repository
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "R0000"
        assert rv.json[last]["handle"] == "b39fe38593f3f8c4f12"
        assert rv.json[last]["type"] == "Library"

    def test_repositories_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/repositories/?junk_parm=1")
        assert rv.status_code == 422

    def test_repositories_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "R0003",
            "handle": "a701ead12841521cd4d",
            "type": "Collection",
        }
        run_test_endpoint_gramps_id(self.client, "/api/repositories/", driver)

    def test_repositories_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/repositories/")

    def test_repositories_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/repositories/", ["address_list", "note_list", "urls"]
        )

    def test_repositories_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/repositories/", ["change", "private", "tag_list"]
        )

    def test_repositories_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/repositories/", driver, ["R0003"])

    def test_repositories_endpoint_schema(self):
        """Test all repositories against the repository schema."""
        rv = self.client.get("/api/repositories/?extend=all")
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


class TestRepositoriesHandle(unittest.TestCase):
    """Test cases for the /api/repositories/{handle} endpoint for a specific repository."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_repositories_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent repositorie
        rv = self.client.get("/api/repositories/does_not_exist")
        assert rv.status_code == 404

    def test_repositories_handle_endpoint(self):
        """Test response for specific repository."""
        # check expected repository returned
        rv = self.client.get("/api/repositories/b39fe38593f3f8c4f12")
        assert rv.json["gramps_id"] == "R0000"
        assert rv.json["type"] == "Library"

    def test_repositories_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/repositories/b39fe38593f3f8c4f12?junk_parm=1")
        assert rv.status_code == 422

    def test_repositories_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/repositories/b39fe38593f3f8c4f12")

    def test_repositories_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/repositories/b39fe38593f3f8c4f12",
            ["handle", "name", "type"],
        )

    def test_repositories_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/repositories/b39fe38593f3f8c4f12",
            ["handle", "note_list", "change"],
        )

    def test_repositories_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(
            self.client, "/api/repositories/b39fe38593f3f8c4f12", driver
        )

    def test_repositories_handle_endpoint_schema(self):
        """Test the repository schema with extensions."""
        # check repository record conforms to expected schema
        rv = self.client.get("/api/repositories/b39fe38593f3f8c4f12?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Repository"],
            resolver=resolver,
        )
