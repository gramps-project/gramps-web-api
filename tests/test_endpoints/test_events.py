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

"""Tests for the /api/events endpoints using example_gramps."""

import unittest
from typing import Dict, List

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


class TestEvents(unittest.TestCase):
    """Test cases for the /api/events endpoint for a list of events."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_events_endpoint(self):
        """Test reponse for events."""
        # check expected number of events found
        result = self.client.get("/api/events/")
        self.assertEqual(len(result.json), get_object_count("events"))
        # checked number passed back in header as well
        count = result.headers.pop("X-Total-Count")
        self.assertEqual(count, str(get_object_count("events")))
        # check first record is expected event
        self.assertEqual(result.json[0]["gramps_id"], "E0000")
        self.assertEqual(
            result.json[0]["description"], "Birth of Warner, Sarah Suzanne"
        )
        self.assertEqual(result.json[0]["place"], "08TJQCCFIX31BXPNXN")
        # check last record is expected event
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "E3431")
        self.assertEqual(result.json[last]["description"], "")
        self.assertEqual(result.json[last]["place"], "")

    def test_events_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/events/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_events_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "E0523",
            "handle": "a5af0ebb51337f15e61",
            "place": "PH0KQCXU2AQ7P3TFHB",
        }
        run_test_endpoint_gramps_id(self, "/api/events/", driver)

    def test_events_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/events/")

    def test_events_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self, "/api/events/", ["handle", "description", "place"])

    def test_events_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/events/", ["change", "description", "tag_list"]
        )

    def test_events_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasType","values":["Marriage"]}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasType","values":["Marriage"]}]}',
                '{"function":"none","rules":[{"name":"HasType",'
                + '"values":["Marriage"]}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasType","values":["Marriage"]}]}',
                '{"rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
                '{"function":"or","rules":[{"name":"HasType","values":["Death"]},'
                + '{"name":"HasNote"}]}',
                '{"function":"xor","rules":[{"name":"HasType","values":["Death"]},'
                + '{"name":"HasNote"}]}',
                '{"function":"one","rules":[{"name":"HasType","values":["Death"]},'
                + '{"name":"HasNote"}]}',
                '{"invert":true,"rules":[{"name":"HasType","values":["Married"]}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/events/", driver)

    def test_events_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if missing or bad argument
        result = self.client.get("/api/events/?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/events/?profile=3")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/events/?profile=alpha")
        self.assertEqual(result.status_code, 422)
        # check expected number of events found
        result = self.client.get("/api/events/?profile=all")
        self.assertEqual(len(result.json), get_object_count("events"))
        # check all expected profile attributes present for first event
        self.assertEqual(
            result.json[0]["profile"],
            {
                "date": "1987-08-29",
                "place": "Gainesville, Llano, TX, USA",
                "type": "Birth",
            },
        )

    def test_events_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "place", "key": "place", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/events/", driver, ["E0341"])

    def test_events_endpoint_schema(self):
        """Test all events against the event schema."""
        result = self.client.get("/api/events/?extend=all&profile=all")
        # check expected number of events found
        self.assertEqual(len(result.json), get_object_count("events"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for event in result.json:
            validate(
                instance=event,
                schema=API_SCHEMA["definitions"]["Event"],
                resolver=resolver,
            )


class TestEventsHandle(unittest.TestCase):
    """Test cases for the /api/events/{handle} endpoint for a specific event."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_events_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent event
        result = self.client.get("/api/events/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_events_handle_endpoint(self):
        """Test response for specific event."""
        # check expected event returned
        result = self.client.get("/api/events/a5af0eb6dd140de132c")
        self.assertEqual(result.json["gramps_id"], "E0043")
        self.assertEqual(result.json["place"], "P4EKQC5TG9HPIOXHN2")

    def test_events_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/events/a5af0eb6dd140de132c?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_events_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/events/a5af0eb6dd140de132c")

    def test_events_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/events/a5af0eb6dd140de132c",
            ["handle", "description", "type"],
        )

    def test_events_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/events/a5af0eb6dd140de132c",
            ["handle", "media_list", "private"],
        )

    def test_events_handle_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed missing or bad argument
        result = self.client.get("/api/events/a5af0eb6dd140de132c?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/events/a5af0eb6dd140de132c?profile=3")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/events/a5af0eb6dd140de132c?profile=omega")
        self.assertEqual(result.status_code, 422)
        # check some key expected profile attributes present
        result = self.client.get("/api/events/a5af0eb6dd140de132c?profile=all")
        self.assertEqual(
            result.json["profile"],
            {
                "date": "1250",
                "place": "Atchison, Atchison, KS, USA",
                "type": "Birth",
            },
        )

    def test_events_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "place", "key": "place", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/events/a5af0eb6dd140de132c", driver)

    def test_event_handle_endpoint_schema(self):
        """Test the event schema with extensions."""
        # check event record conforms to expected schema
        result = self.client.get(
            "/api/events/a5af0eb6dd140de132c?extend=all&profile=all"
        )
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Event"],
            resolver=resolver,
        )
