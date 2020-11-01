"""Tests for the /api/places endpoints using example_gramps."""

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


class TestPlaces(unittest.TestCase):
    """Test cases for the /api/places endpoint for a list of places."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_places_endpoint(self):
        """Test reponse for places."""
        # check expected number of places found
        rv = self.client.get("/api/places/")
        assert len(rv.json) == get_object_count("places")
        # check first record is expected place
        assert rv.json[0]["gramps_id"] == "P0852"
        assert rv.json[0]["handle"] == "00BKQC7SA8C9NCGB0A"
        assert rv.json[0]["title"] == "Deltona, FL"
        # check last record is expected place
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "P0441"
        assert rv.json[last]["handle"] == "dd445e5bfcc17bd1838"
        assert rv.json[last]["title"] == ""

    def test_places_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/places/?junk_parm=1")
        assert rv.status_code == 422

    def test_places_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "P1108",
            "handle": "B9VKQCD14KD2OH3QZY",
            "title": "York, PA",
        }
        run_test_endpoint_gramps_id(self.client, "/api/places/", driver)

    def test_places_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/places/")

    def test_places_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/places/", ["handle", "place_type", "title"]
        )

    def test_places_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/places/", ["alt_loc", "code", "placeref_list"]
        )

    def test_places_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self.client, "/api/places/", driver, ["P1108"])

    def test_places_endpoint_schema(self):
        """Test all places against the place schema."""
        rv = self.client.get("/api/places/?extend=all")
        # check expected number of places found
        assert len(rv.json) == get_object_count("places")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for place in rv.json:
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
        rv = self.client.get("/api/places/does_not_exist")
        assert rv.status_code == 404

    def test_places_handle_endpoint(self):
        """Test response for specific place."""
        # check expected place returned
        rv = self.client.get("/api/places/09UJQCF3TNGH9GU0P1")
        assert rv.json["gramps_id"] == "P0863"
        assert rv.json["title"] == "Bowling Green, KY"

    def test_places_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/places/09UJQCF3TNGH9GU0P1?junk_parm=1")
        assert rv.status_code == 422

    def test_places_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/places/09UJQCF3TNGH9GU0P1")

    def test_places_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/places/09UJQCF3TNGH9GU0P1",
            ["handle", "lat", "long"],
        )

    def test_places_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
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
        run_test_endpoint_extend(self.client, "/api/places/09UJQCF3TNGH9GU0P1", driver)

    def test_places_handle_endpoint_schema(self):
        """Test the place schema with extensions."""
        # check place record conforms to expected schema
        rv = self.client.get("/api/places/09UJQCF3TNGH9GU0P1?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Place"],
            resolver=resolver,
        )
