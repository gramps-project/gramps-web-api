"""Tests for the /api/events endpoints using example_gramps."""

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


class TestEvents(unittest.TestCase):
    """Test cases for the /api/events endpoint for a list of events."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_events_endpoint(self):
        """Test reponse for events."""
        # check expected number of events found
        rv = self.client.get("/api/events/")
        assert len(rv.json) == get_object_count("events")
        # check first record is expected event
        assert rv.json[0]["gramps_id"] == "E0000"
        assert rv.json[0]["description"] == "Birth of Warner, Sarah Suzanne"
        assert rv.json[0]["place"] == "08TJQCCFIX31BXPNXN"
        # check last record is expected event
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "E3431"
        assert rv.json[last]["description"] == ""
        assert rv.json[last]["place"] == ""

    def test_events_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/events/?junk_parm=1")
        assert rv.status_code == 422

    def test_events_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "E0523",
            "handle": "a5af0ebb51337f15e61",
            "place": "PH0KQCXU2AQ7P3TFHB",
        }
        run_test_endpoint_gramps_id(self.client, "/api/events/", driver)

    def test_events_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/events/")

    def test_events_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/events/", ["handle", "description", "place"]
        )

    def test_events_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/events/", ["change", "description", "tag_list"]
        )

    def test_events_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"HasType","values":["Marriage"]}]}'],
            422: [
                '{"some":"where","rules":[{"name":"HasType","values":["Marriage"]}]}',
                '{"function":"none","rules":[{"name":"HasType","values":["Marriage"]}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasType","values":["Marriage"]}]}',
                '{"rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
                '{"function":"or","rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
                '{"function":"xor","rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
                '{"function":"one","rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
                '{"invert":true,"rules":[{"name":"HasType","values":["Married"]}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/events/", driver)

    def test_events_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed argument
        rv = self.client.get("/api/events/?profile=1")
        assert rv.status_code == 422
        # check expected number of events found
        rv = self.client.get("/api/events/?profile")
        assert len(rv.json) == get_object_count("events")
        # check all expected profile attributes present for first event
        assert rv.json[0]["profile"] == {
            "date": "1987-08-29",
            "place": "Gainesville, Llano, TX, USA",
            "type": "Birth",
        }

    def test_events_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "place", "key": "place", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/events/", driver, ["E0341"])

    def test_events_endpoint_schema(self):
        """Test all events against the event schema."""
        rv = self.client.get("/api/events/?extend=all&profile")
        # check expected number of events found
        assert len(rv.json) == get_object_count("events")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for event in rv.json:
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
        rv = self.client.get("/api/events/does_not_exist")
        assert rv.status_code == 404

    def test_events_handle_endpoint(self):
        """Test response for specific event."""
        # check expected event returned
        rv = self.client.get("/api/events/a5af0eb6dd140de132c")
        assert rv.json["gramps_id"] == "E0043"
        assert rv.json["place"] == "P4EKQC5TG9HPIOXHN2"

    def test_events_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/events/a5af0eb6dd140de132c?junk_parm=1")
        assert rv.status_code == 422

    def test_events_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/events/a5af0eb6dd140de132c")

    def test_events_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/events/a5af0eb6dd140de132c",
            ["handle", "description", "type"],
        )

    def test_events_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/events/a5af0eb6dd140de132c",
            ["handle", "media_list", "private"],
        )

    def test_events_handle_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed argument
        rv = self.client.get("/api/events/a5af0eb6dd140de132c?profile=1")
        assert rv.status_code == 422
        # check some key expected profile attributes present
        rv = self.client.get("/api/events/a5af0eb6dd140de132c?profile")
        assert rv.json["profile"] == {
            "date": "1250",
            "place": "Atchison, Atchison, KS, USA",
            "type": "Birth",
        }

    def test_events_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "place", "key": "place", "type": Dict},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/events/a5af0eb6dd140de132c", driver)

    def test_event_handle_endpoint_schema(self):
        """Test the event schema with extensions."""
        # check event record conforms to expected schema
        rv = self.client.get("/api/events/a5af0eb6dd140de132c?extend=all&profile")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Event"],
            resolver=resolver,
        )
