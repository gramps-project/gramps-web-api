#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for the /api/places/coordinates/ endpoint."""

import os
import unittest
import uuid
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL, get_object_count, get_test_client
from .checks import check_requires_token, check_success

TEST_URL = BASE_URL + "/places/coordinates/"


class TestPlaceCoordinatesExampleDb(unittest.TestCase):
    """Test cases for /api/places/coordinates/ with the example tree."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_all_places_returned(self):
        """Test that every place is returned exactly once."""
        rv = check_success(self, TEST_URL)
        self.assertEqual(len(rv), get_object_count("places"))
        places = check_success(self, BASE_URL + "/places/?keys=handle")
        self.assertEqual(
            sorted(place["handle"] for place in rv),
            sorted(place["handle"] for place in places),
        )
        for place in rv:
            self.assertEqual(set(place), {"handle", "name", "lat", "long"})

    def test_matches_profile(self):
        """Test that name and coordinates agree with the place profile."""
        rv = check_success(self, TEST_URL)
        profiles = check_success(
            self, BASE_URL + "/places/?profile=self&place_hierarchy=0"
        )
        expected = {}
        for place in profiles:
            lat, long = place["profile"]["lat"], place["profile"]["long"]
            if lat == 0 and long == 0:
                # the profile encodes missing coordinates as 0, 0
                lat, long = None, None
            expected[place["handle"]] = {
                "name": place["profile"]["name"],
                "lat": lat,
                "long": long,
            }
        for place in rv:
            handle = place.pop("handle")
            self.assertEqual(place, expected[handle])


class TestPlaceCoordinatesPrivacy(unittest.TestCase):
    """Test cases for /api/places/coordinates/ with private and invalid places."""

    @classmethod
    def setUpClass(cls):
        """Create a tree with public, private, and invalid places."""
        cls.name = "Test Place Coordinates"
        cls.dbman = CLIDbManager(DbState())
        dbpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="guest", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=tree)
        cls.places = {
            "public": ("Public", "50.5", "-7.25", False),
            "private": ("Private", "10", "20", True),
            "missing": ("Missing", "", "", False),
            "invalid": ("Invalid", "not a latitude", "20", False),
        }
        cls.handles = {key: str(uuid.uuid4()) for key in cls.places}
        headers = cls.get_headers("owner")
        for key, (name, lat, long, private) in cls.places.items():
            rv = cls.client.post(
                BASE_URL + "/places/",
                json={
                    "_class": "Place",
                    "handle": cls.handles[key],
                    "name": {"_class": "PlaceName", "value": name},
                    "lat": lat,
                    "long": long,
                    "private": private,
                },
                headers=headers,
            )
            assert rv.status_code == 201, rv.json

    @classmethod
    def tearDownClass(cls):
        """Remove the test tree."""
        cls.dbman.remove_database(cls.name)

    @classmethod
    def get_headers(cls, user: str) -> dict[str, str]:
        """Get the auth headers for a user."""
        rv = cls.client.post("/api/token/", json={"username": user, "password": "123"})
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def get_places(self, user: str) -> dict[str, dict]:
        """Get the coordinates response as seen by a user, keyed by handle."""
        rv = self.client.get(TEST_URL, headers=self.get_headers(user))
        self.assertEqual(rv.status_code, 200)
        return {place.pop("handle"): place for place in rv.json}

    def test_owner_sees_private_place(self):
        """Test that the owner gets all places, with parsed coordinates."""
        places = self.get_places("owner")
        self.assertEqual(
            places,
            {
                self.handles["public"]: {"name": "Public", "lat": 50.5, "long": -7.25},
                self.handles["private"]: {"name": "Private", "lat": 10.0, "long": 20.0},
                self.handles["missing"]: {"name": "Missing", "lat": None, "long": None},
                self.handles["invalid"]: {"name": "Invalid", "lat": None, "long": None},
            },
        )

    def test_guest_does_not_see_private_place(self):
        """Test that a guest does not get private places."""
        places = self.get_places("guest")
        self.assertNotIn(self.handles["private"], places)
        self.assertEqual(
            set(places),
            {self.handles[key] for key in ["public", "missing", "invalid"]},
        )
