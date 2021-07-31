#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Tests object creation via POST."""

import unittest
import uuid
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def make_handle() -> str:
    """Make a new valid handle."""
    return str(uuid.uuid4())


class TestObjectCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        sqlauth = cls.app.config["AUTH_PROVIDER"]
        sqlauth.create_table()
        sqlauth.add_user(name="user", password="123", role=ROLE_GUEST)
        sqlauth.add_user(name="admin", password="123", role=ROLE_OWNER)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_objects_add_note(self):
        """Add a single note via objects."""
        handle = make_handle()
        obj = [
            {
                "_class": "Note",
                "handle": handle,
                "text": {"_class": "StyledText", "string": "My first note."},
            }
        ]
        headers = get_headers(self.client, "user", "123")
        rv = self.client.post("/api/objects/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 403)
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/objects/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["handle"], handle)
        self.assertEqual(obj_dict["text"]["string"], "My first note.")

    def test_add_note(self):
        """Add a single note."""
        handle = make_handle()
        obj = {
            "handle": handle,
            "text": {"_class": "StyledText", "string": "My first note."},
        }
        headers = get_headers(self.client, "user", "123")
        rv = self.client.post("/api/notes/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 403)
        headers = get_headers(self.client, "admin", "123")
        wrong_obj = {"_class": "Person", "handle": handle}
        rv = self.client.post("/api/notes/", json=wrong_obj, headers=headers)
        self.assertEqual(rv.status_code, 400)
        rv = self.client.post("/api/notes/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["handle"], handle)
        self.assertEqual(obj_dict["text"]["string"], "My first note.")

    def test_objects_add_person(self):
        """Add a person with a birth event."""
        handle_person = make_handle()
        handle_birth = make_handle()
        person = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [{"_class": "Surname", "surname": "Doe",}],
                "first_name": "John",
            },
            "event_ref_list": [
                {
                    "_class": "EventRef",
                    "ref": handle_birth,
                    "role": {"_class": "EventRoleType", "string": "Primary"},
                },
            ],
            "birth_ref_index": 0,
            "gender": 1,
        }
        birth = {
            "_class": "Event",
            "handle": handle_birth,
            "date": {"_class": "Date", "dateval": [2, 10, 1764, False],},
            "type": {"_class": "EventType", "string": "Birth"},
        }
        objects = [person, birth]
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # check return value
        out = rv.json
        self.assertEqual(len(out), 2)
        rv = self.client.get(
            f"/api/people/{handle_person}?extend=event_ref_list", headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        person_dict = rv.json
        self.assertEqual(person_dict["handle"], handle_person)
        self.assertEqual(person_dict["primary_name"]["first_name"], "John")
        self.assertEqual(
            person_dict["primary_name"]["surname_list"][0]["surname"], "Doe"
        )
        self.assertEqual(person_dict["extended"]["events"][0]["handle"], handle_birth)
        self.assertEqual(
            person_dict["extended"]["events"][0]["date"]["dateval"],
            [2, 10, 1764, False],
        )

    def test_objects_errors(self):
        """Test adding multiple objects with and without errors."""
        handle_person = make_handle()
        handle_birth = make_handle()
        person = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [{"_class": "Surname", "surname": "Doe",}],
                "first_name": "John",
            },
            "event_ref_list": [
                {
                    "_class": "EventRef",
                    "ref": handle_birth,
                    "role": {"_class": "EventRoleType", "string": "Primary"},
                },
            ],
            "birth_ref_index": 0,
            "gender": 1,
        }
        birth = {
            "_class": "Event",
            "handle": handle_birth,
            "date": {"_class": "Date", "dateval": [2, 10, 1764, False],},
            "type": {"_class": "EventType", "string": "Birth"},
        }
        # erroneously use string as date
        objects = [person, {**birth, "date": "1764-10-2"}]
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        self.assertEqual(rv.status_code, 400)
        # make sure the objects don't exist
        rv = self.client.get(f"/api/people/{handle_person}", headers=headers)
        self.assertEqual(rv.status_code, 404)
        rv = self.client.get(f"/api/events/{handle_birth}", headers=headers)
        self.assertEqual(rv.status_code, 404)

    def test_people_add_person(self):
        """Add a person with a birth event."""
        handle_person = make_handle()
        handle_birth = make_handle()
        person = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [{"_class": "Surname", "surname": "Doe",}],
                "first_name": "John",
            },
            "gender": 1,
        }
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/people/", json=person, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/people/{handle_person}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        person_dict = rv.json
        self.assertEqual(person_dict["handle"], handle_person)
        self.assertEqual(person_dict["primary_name"]["first_name"], "John")
        self.assertEqual(
            person_dict["primary_name"]["surname_list"][0]["surname"], "Doe"
        )

    def test_add_tag(self):
        """Add a single tag."""
        handle = make_handle()
        obj = {"handle": handle, "name": "MyTag"}
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/tags/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # check return value
        out = rv.json
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["_class"], "Tag")
        self.assertEqual(out[0]["handle"], handle)
        self.assertEqual(out[0]["old"], None)
        self.assertEqual(out[0]["new"]["name"], "MyTag")
        self.assertEqual(out[0]["type"], "add")
        # check get
        rv = self.client.get(f"/api/tags/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["name"], obj["name"])

    def test_add_event(self):
        """Add a single event."""
        handle = make_handle()
        obj = {"handle": handle, "description": "My Event"}
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/events/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/events/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["description"], obj["description"])

    def test_add_source(self):
        """Add a single source."""
        handle = make_handle()
        obj = {"handle": handle, "title": "My Source"}
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/sources/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/sources/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["title"], obj["title"])

    def test_add_citation(self):
        """Add a single citation."""
        handle = make_handle()
        obj = {"handle": handle, "page": "p. 300"}
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/citations/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/citations/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["page"], obj["page"])

    def test_add_repository(self):
        """Add a single repository."""
        handle = make_handle()
        obj = {"handle": handle, "name": "My Repository"}
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/repositories/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/repositories/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["name"], obj["name"])
