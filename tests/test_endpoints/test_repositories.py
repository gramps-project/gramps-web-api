#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the /api/repositories endpoints using example_gramps."""

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


class TestRepositories(unittest.TestCase):
    """Test cases for the /api/repositories endpoint for a list of repositories."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_repositories_endpoint(self):
        """Test reponse for repositories."""
        # check expected number of repositories found
        result = self.client.get("/api/repositories/")
        self.assertEqual(len(result.json), get_object_count("repositories"))
        # checked number passed back in header as well
        count = result.headers.pop("X-Total-Count")
        self.assertEqual(count, str(get_object_count("repositories")))
        # check first record is expected repository
        self.assertEqual(result.json[0]["gramps_id"], "R0002")
        self.assertEqual(result.json[0]["handle"], "a701e99f93e5434f6f3")
        self.assertEqual(result.json[0]["type"], "Library")
        # check last record is expected repository
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "R0000")
        self.assertEqual(result.json[last]["handle"], "b39fe38593f3f8c4f12")
        self.assertEqual(result.json[last]["type"], "Library")

    def test_repositories_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/repositories/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_repositories_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "R0003",
            "handle": "a701ead12841521cd4d",
            "type": "Collection",
        }
        run_test_endpoint_gramps_id(self, "/api/repositories/", driver)

    def test_repositories_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/repositories/")

    def test_repositories_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self, "/api/repositories/", ["address_list", "note_list", "urls"]
        )

    def test_repositories_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/repositories/", ["change", "private", "tag_list"]
        )

    def test_repositories_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasTag","values":["ToDo"]}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasTag", "values":["ToDo"]}]}',
                '{"function":"none","rules":[{"name":"HasTag","values":["ToDo"]}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasTag","values":["ToDo"]}]}',
                '{"rules":[{"name":"MatchesNameSubstringOf",'
                + '"values":["Library"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"function":"or","rules":[{"name":"MatchesNameSubstringOf",'
                + '"values":["Library"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"function":"xor","rules":[{"name":"MatchesNameSubstringOf",'
                + '"values":["Library"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"function":"one","rules":[{"name":"MatchesNameSubstringOf",'
                + '"values":["Library"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"invert":true,"rules":[{"name":"HasTag","values":["ToDo"]}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/repositories/", driver)

    def test_repositories_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/repositories/", driver, ["R0003"])

    def test_repositories_endpoint_schema(self):
        """Test all repositories against the repository schema."""
        result = self.client.get("/api/repositories/?extend=all")
        # check expected number of repositories found
        self.assertEqual(len(result.json), get_object_count("repositories"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for repository in result.json:
            validate(
                instance=repository,
                schema=API_SCHEMA["definitions"]["Repository"],
                resolver=resolver,
            )


class TestRepositoriesHandle(unittest.TestCase):
    """Test cases for the /api/repositories/{handle} endpoint for a repository."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_repositories_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent repositorie
        result = self.client.get("/api/repositories/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_repositories_handle_endpoint(self):
        """Test response for specific repository."""
        # check expected repository returned
        result = self.client.get("/api/repositories/b39fe38593f3f8c4f12")
        self.assertEqual(result.json["gramps_id"], "R0000")
        self.assertEqual(result.json["type"], "Library")

    def test_repositories_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/repositories/b39fe38593f3f8c4f12?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_repositories_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/repositories/b39fe38593f3f8c4f12")

    def test_repositories_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/repositories/b39fe38593f3f8c4f12",
            ["handle", "name", "type"],
        )

    def test_repositories_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/repositories/b39fe38593f3f8c4f12",
            ["handle", "note_list", "change"],
        )

    def test_repositories_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/repositories/b39fe38593f3f8c4f12", driver)

    def test_repositories_handle_endpoint_schema(self):
        """Test the repository schema with extensions."""
        # check repository record conforms to expected schema
        result = self.client.get("/api/repositories/b39fe38593f3f8c4f12?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Repository"],
            resolver=resolver,
        )
