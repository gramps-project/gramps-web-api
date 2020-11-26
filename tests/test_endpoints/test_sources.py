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

"""Tests for the /api/sources endpoints using example_gramps."""

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


class TestSources(unittest.TestCase):
    """Test cases for the /api/sources endpoint for a list of sources."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_sources_endpoint(self):
        """Test reponse for sources."""
        # check expected number of sources found
        result = self.client.get("/api/sources/")
        self.assertEqual(len(result.json), get_object_count("sources"))
        # check first record is expected source
        self.assertEqual(result.json[0]["gramps_id"], "S0001")
        self.assertEqual(result.json[0]["handle"], "c140d4ef77841431905")
        self.assertEqual(result.json[0]["title"], "All possible citations")
        # check last record is expected source
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "S0002")
        self.assertEqual(result.json[last]["handle"], "VUBKMQTA2XZG1V6QP8")
        self.assertEqual(result.json[last]["title"], "World of the Wierd")

    def test_sources_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/sources/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_sources_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "S0000",
            "handle": "b39fe3f390e30bd2b99",
            "title": "Baptize registry 1850 - 1867 Great Falls Church",
        }
        run_test_endpoint_gramps_id(self, "/api/sources/", driver)

    def test_sources_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/sources/")

    def test_sources_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self, "/api/sources/", ["author", "pubinfo", "title"])

    def test_sources_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/sources/", ["abbrev", "reporef_list", "tag_list"]
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
                '{"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]}'
                + ',{"name":"HasNote"}]}',
                '{"function":"or","rules":[{"name":"MatchesTitleSubstringOf",'
                + '"values":["Church"]},{"name":"HasNote"}]}',
                '{"function":"xor","rules":[{"name":"MatchesTitleSubstringOf",'
                + '"values":["Church"]},{"name":"HasNote"}]}',
                '{"function":"one","rules":[{"name":"MatchesTitleSubstringOf",'
                + '"values":["Church"]},{"name":"HasNote"}]}',
                '{"invert":true,"rules":[{"name":"HasNote"}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/sources/", driver)

    def test_sources_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "reporef_list", "key": "repositories", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/sources/", driver, ["S0000"])

    def test_sources_endpoint_schema(self):
        """Test all sources against the source schema."""
        result = self.client.get("/api/sources/?extend=all")
        # check expected number of sources found
        self.assertEqual(len(result.json), get_object_count("sources"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for source in result.json:
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
        result = self.client.get("/api/sources/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_sources_handle_endpoint(self):
        """Test response for specific source."""
        # check expected source returned
        result = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX")
        self.assertEqual(result.json["gramps_id"], "S0003")
        self.assertEqual(result.json["title"], "Import from test2.ged")

    def test_sources_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_sources_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/sources/X5TJQC9JXU4RKT6VAX")

    def test_sources_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/sources/X5TJQC9JXU4RKT6VAX",
            ["handle", "pubinfo", "title"],
        )

    def test_sources_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
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
        run_test_endpoint_extend(self, "/api/sources/X5TJQC9JXU4RKT6VAX", driver)

    def test_sources_handle_endpoint_schema(self):
        """Test the source schema with extensions."""
        # check source record conforms to expected schema
        result = self.client.get("/api/sources/X5TJQC9JXU4RKT6VAX?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Source"],
            resolver=resolver,
        )
