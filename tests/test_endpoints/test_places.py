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

"""Tests for the /api/places endpoints using example_gramps."""

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


class TestPlaces(unittest.TestCase):
    """Test cases for the /api/places endpoint for a list of places."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_places_endpoint(self):
        """Test reponse for places."""
        # check expected number of places found
        result = self.client.get("/api/places/")
        self.assertEqual(len(result.json), get_object_count("places"))
        # check first record is expected place
        self.assertEqual(result.json[0]["gramps_id"], "P0441")
        self.assertEqual(result.json[0]["handle"], "dd445e5bfcc17bd1838")
        # check last record is expected place
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "P0438")
        self.assertEqual(result.json[last]["handle"], "d583a5b8b586fb992c8")
        self.assertEqual(result.json[last]["title"], "Σιάτιστα")

    def test_places_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/places/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_places_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "P1108",
            "handle": "B9VKQCD14KD2OH3QZY",
            "title": "York, PA",
        }
        run_test_endpoint_gramps_id(self, "/api/places/", driver)

    def test_places_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/places/")

    def test_places_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self, "/api/places/", ["handle", "place_type", "title"])

    def test_places_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/places/", ["alt_loc", "code", "placeref_list"]
        )

    def test_places_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasNoLatOrLon"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasNoLatOrLon"}]}',
                '{"function":"none","rules":[{"name":"HasNoLatOrLon"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasNoLatOrLon"}]}',
                '{"rules":[{"name":"HasNoLatOrLon"},'
                + '{"name":"HasTag","values":["None"]}]}',
                '{"function":"or","rules":[{"name":"HasNoLatOrLon"},'
                + '{"name":"HasTag","values":["None"]}]}',
                '{"function":"xor","rules":[{"name":"HasNoLatOrLon"},'
                + '{"name":"HasTag","values":["None"]}]}',
                '{"function":"one","rules":[{"name":"HasNoLatOrLon"},'
                + '{"name":"HasTag","values":["None"]}]}',
                '{"invert":true,"rules":[{"name":"HasNoLatOrLon"}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/places/", driver)

    def test_places_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/places/", driver, ["P1108"])

    def test_places_endpoint_schema(self):
        """Test all places against the place schema."""
        result = self.client.get("/api/places/?extend=all")
        # check expected number of places found
        self.assertEqual(len(result.json), get_object_count("places"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for place in result.json:
            validate(
                instance=place,
                schema=API_SCHEMA["definitions"]["Place"],
                resolver=resolver,
            )


class TestPlacesHandle(unittest.TestCase):
    """Test cases for the /api/places/{handle} endpoint for a specific place."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_places_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent place
        result = self.client.get("/api/places/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_places_handle_endpoint(self):
        """Test response for specific place."""
        # check expected place returned
        result = self.client.get("/api/places/09UJQCF3TNGH9GU0P1")
        self.assertEqual(result.json["gramps_id"], "P0863")
        self.assertEqual(result.json["title"], "Bowling Green, KY")

    def test_places_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/places/09UJQCF3TNGH9GU0P1?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_places_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/places/09UJQCF3TNGH9GU0P1")

    def test_places_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/places/09UJQCF3TNGH9GU0P1",
            ["handle", "lat", "long"],
        )

    def test_places_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/places/09UJQCF3TNGH9GU0P1",
            ["handle", "media_list", "private"],
        )

    def test_places_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/places/09UJQCF3TNGH9GU0P1", driver)

    def test_places_handle_endpoint_schema(self):
        """Test the place schema with extensions."""
        # check place record conforms to expected schema
        result = self.client.get("/api/places/09UJQCF3TNGH9GU0P1?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Place"],
            resolver=resolver,
        )
