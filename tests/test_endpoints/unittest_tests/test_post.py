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

import os
import unittest
import uuid
from copy import deepcopy
from time import sleep
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.dbstate import DbState

from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, set_tree_details, user_db
from gramps_webapi.auth.const import (
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

_ = glocale.translation.gettext


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
        dbpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
            add_user(
                name="contributor", password="123", role=ROLE_CONTRIBUTOR, tree=tree
            )
            add_user(name="editor", password="123", role=ROLE_EDITOR, tree=tree)
            set_tree_details(tree, quota_people=3)

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
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
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
            "date": {
                "_class": "Date",
                "dateval": [2, 10, 1764, False],
            },
            "type": {"_class": "EventType", "string": "Birth"},
        }
        objects = [person, birth]
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
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

    def test_objects_add_person_seperate(self):
        """Add a person, then a birth event, check birth ref index."""
        handle_person = make_handle()
        handle_birth = make_handle()
        person = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
            },
            # "event_ref_list": [
            #     {
            #         "_class": "EventRef",
            #         "ref": handle_birth,
            #         "role": {"_class": "EventRoleType", "string": "Primary"},
            #     },
            # ],
            # "birth_ref_index": 0,
            "gender": 1,
        }
        birth = {
            "_class": "Event",
            "handle": handle_birth,
            "date": {
                "_class": "Date",
                "dateval": [2, 10, 1764, False],
            },
            "type": {"_class": "EventType", "string": _("Birth")},
        }
        person_birth = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
            },
            "event_ref_list": [
                {
                    "_class": "EventRef",
                    "ref": handle_birth,
                    "role": {"_class": "EventRoleType", "string": _("Primary")},
                },
            ],
            "gender": 1,
        }
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/people/", json=person, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.post("/api/events/", json=birth, headers=headers)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/people/{handle_person}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        person_dict = rv.json
        self.assertEqual(person_dict["birth_ref_index"], -1)
        rv = self.client.put(
            f"/api/people/{handle_person}", json=person_birth, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get(f"/api/people/{handle_person}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        person_dict = rv.json
        self.assertEqual(person_dict["birth_ref_index"], 0)

    def test_objects_add_family(self):
        """Add three people and then create a new family."""
        handle_father = make_handle()
        handle_mother = make_handle()
        handle_child = make_handle()
        handle_family = make_handle()
        people = [
            {
                "_class": "Person",
                "handle": handle,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [{"_class": "Surname", "surname": surname}],
                    "first_name": firstname,
                },
                "gender": gender,
            }
            for (handle, gender, firstname, surname) in [
                (handle_father, 1, "Father", "Family"),
                (handle_mother, 0, "Mother", "Family"),
                (handle_child, 1, "Son", "Family"),
            ]
        ]
        headers_admin = get_headers(self.client, "admin", "123")
        rv = self.client.get("/api/people/", headers=headers_admin)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers_admin)
        headers_contributor = get_headers(self.client, "contributor", "123")
        headers_editor = get_headers(self.client, "editor", "123")
        rv = self.client.post("/api/objects/", json=people, headers=headers_contributor)
        self.assertEqual(rv.status_code, 201)
        # check return value
        out = rv.json
        self.assertEqual(len(out), 3)
        family_json = {
            "_class": "Family",
            "handle": handle_family,
            "father_handle": handle_father,
            "mother_handle": handle_mother,
            "child_ref_list": [{"_class": "ChildRef", "ref": handle_child}],
        }
        # posting a family as contributor should fail
        rv = self.client.post(
            "/api/families/", json=family_json, headers=headers_contributor
        )
        self.assertEqual(rv.status_code, 403)
        # posting a family as contributor to the objects endpoint should also fail
        rv = self.client.post(
            "/api/objects/", json=[family_json], headers=headers_contributor
        )
        self.assertEqual(rv.status_code, 403)
        # Now that should work
        rv = self.client.post(
            "/api/families/", json=family_json, headers=headers_editor
        )
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/families/{handle_family}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        family = rv.json
        self.assertEqual(family["handle"], handle_family)
        self.assertEqual(family["father_handle"], handle_father)
        self.assertEqual(family["mother_handle"], handle_mother)
        self.assertListEqual(
            [childref["ref"] for childref in family["child_ref_list"]], [handle_child]
        )
        rv = self.client.get(f"/api/people/{handle_father}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        father = rv.json
        self.assertEqual(father["handle"], handle_father)
        self.assertListEqual(father["family_list"], [handle_family])
        self.assertListEqual(father["parent_family_list"], [])
        rv = self.client.get(f"/api/people/{handle_mother}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        mother = rv.json
        self.assertEqual(mother["handle"], handle_mother)
        self.assertListEqual(mother["family_list"], [handle_family])
        self.assertListEqual(mother["parent_family_list"], [])
        rv = self.client.get(f"/api/people/{handle_child}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        child = rv.json
        self.assertEqual(child["handle"], handle_child)
        self.assertListEqual(child["family_list"], [])
        self.assertListEqual(child["parent_family_list"], [handle_family])
        # and now, interchange father & son
        family_new = deepcopy(family_json)
        family_new["father_handle"] = handle_child
        family_new["child_ref_list"][0]["ref"] = handle_father
        rv = self.client.put(
            f"/api/families/{handle_family}", json=family_new, headers=headers_editor
        )
        self.assertEqual(rv.status_code, 200)
        # ... and check the refs have been updated correctly
        rv = self.client.get(f"/api/people/{handle_father}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        father = rv.json
        self.assertListEqual(father["family_list"], [])
        self.assertListEqual(father["parent_family_list"], [handle_family])
        rv = self.client.get(f"/api/people/{handle_child}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        child = rv.json
        self.assertListEqual(child["family_list"], [handle_family])
        self.assertListEqual(child["parent_family_list"], [])

    def test_objects_errors(self):
        """Test adding multiple objects with and without errors."""
        handle_person = make_handle()
        handle_birth = make_handle()
        person = {
            "_class": "Person",
            "handle": handle_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
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
            "date": {
                "_class": "Date",
                "dateval": [2, 10, 1764, False],
            },
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
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
            },
            "gender": 1,
        }
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
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

    def test_search_add_note(self):
        """Test whether adding a note updates the search index correctly."""
        gramps_id = make_handle().replace("-", "")  # random Gramps ID
        handle = make_handle()
        headers = get_headers(self.client, "admin", "123")
        # not added yet: shouldn't find anything
        rv = self.client.get(f"/api/search/?query={gramps_id}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, [])
        obj = {
            "_class": "Note",
            "handle": handle,
            "gramps_id": gramps_id,
            "text": {"_class": "StyledText", "string": "My searchable note."},
        }
        rv = self.client.post("/api/notes/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # now it should be there
        rv = self.client.get(f"/api/search/?query={gramps_id}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        data = rv.json
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["handle"], handle)
        self.assertEqual(data[0]["object_type"], "note")

    def test_search_add_person(self):
        """Test whether adding a person with event updates the search index."""
        handle_person = make_handle()
        gramps_id_person = make_handle().replace("-", "")  # random Gramps ID
        handle_birth = make_handle()
        gramps_id_birth = make_handle().replace("-", "")  # random Gramps ID
        person = {
            "_class": "Person",
            "handle": handle_person,
            "gramps_id": gramps_id_person,
            "primary_name": {
                "_class": "Name",
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
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
            "gramps_id": gramps_id_birth,
            "date": {
                "_class": "Date",
                "dateval": [2, 10, 1764, False],
            },
            "type": {"_class": "EventType", "string": "Birth"},
        }
        objects = [person, birth]
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # now they should be there
        rv = self.client.get(f"/api/search/?query={gramps_id_person}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        data = rv.json
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["handle"], handle_person)
        self.assertEqual(data[0]["object_type"], "person")
        rv = self.client.get(f"/api/search/?query={gramps_id_birth}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        data = rv.json
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["handle"], handle_birth)
        self.assertEqual(data[0]["object_type"], "event")

    def test_search_locked(self):
        """Torture test for search."""
        # this was originally meant as a torture test for the whoosh async writer
        # when we still had whoosh as backend.
        headers = get_headers(self.client, "admin", "123")
        with self.app.app_context():
            db_manager = WebDbManager(name=self.name, create_if_missing=False)
            tree = db_manager.dirname
            indexer = get_search_indexer(tree)
            label = make_handle().replace("-", "")
            content = {"text": {"_class": "StyledText", "string": label}}
            for _ in range(10):
                # write 10 objects
                rv = self.client.post(
                    "/api/notes/",
                    json=content,
                    headers=headers,
                )
                self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/search/?query={label}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        data = rv.json
        # check all 10 exist in the index
        self.assertEqual(len(data), 10)

    def test_add_people_quota(self):
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
        person = {
            "primary_name": {
                "first_name": "Person1",
            },
            "gender": 1,
        }
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/people/", headers=headers)
        assert len(rv.json) == 1
        person = {
            "primary_name": {
                "first_name": "Person2",
            },
            "gender": 1,
        }
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/people/", headers=headers)
        assert len(rv.json) == 2
        person = {
            "primary_name": {
                "first_name": "Person3",
            },
            "gender": 1,
        }
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/people/", headers=headers)
        assert len(rv.json) == 3
        person = {
            "primary_name": {
                "first_name": "Person4",
            },
            "gender": 1,
        }
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 405
        rv = self.client.get("/api/people/", headers=headers)
        assert len(rv.json) == 3
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)

    def test_add_people_quota_objects(self):
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
        people = [
            {
                "_class": "Person",
                "primary_name": {
                    "_class": "Name",
                    "first_name": f"Person{i}",
                },
                "gender": 1,
            }
            for i in range(4)
        ]
        rv = self.client.post("/api/objects/", json=people[:3], headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/people/", headers=headers)
        assert len(rv.json) == 3
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
        rv = self.client.post("/api/objects/", json=people[:4], headers=headers)
        assert rv.status_code == 405

    def test_add_person_types(self):
        """Add a person and check that types are handled correctly even
        when using incomplete dicts."""
        handle_person = make_handle()
        person = {
            "handle": handle_person,
            "primary_name": {
                "surname_list": [
                    {
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
                "type": "Married Name",
            },
            "gender": 1,
        }
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/people/", headers=headers)
        rv = self.client.get("/api/people/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing people
        for handle in handles:
            self.client.delete(f"/api/people/{handle}", headers=headers)
        rv = self.client.post("/api/people/", json=person, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # check return value
        out = rv.json
        assert len(out) == 1
        rv = self.client.get(
            f"/api/people/{handle_person}?locale=de",
            headers=headers,
        )
        assert rv.status_code == 200
        person_dict = rv.json
        assert person_dict["primary_name"]["first_name"] == "John"
        assert person_dict["primary_name"]["surname_list"][0]["surname"] == "Doe"
        assert person_dict["primary_name"]["type"] == "Married Name"

    def test_add_event_types(self):
        handle_event = make_handle()
        event = {
            "handle": handle_event,
            "change": 1746095141,
            "date": {
                "format": None,
                "calendar": 0,
                "modifier": 0,
                "quality": 0,
                "dateval": [2, 2, 1991, False],
            },
            "_class": "Event",
            "type": "Adopted",
        }
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/events/", headers=headers)
        rv = self.client.get("/api/events/", headers=headers)
        handles = [obj["handle"] for obj in rv.json]
        # delete existing events
        for handle in handles:
            self.client.delete(f"/api/events/{handle}", headers=headers)
        rv = self.client.post("/api/events/", json=event, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # check return value
        out = rv.json
        assert len(out) == 1
        rv = self.client.get(
            f"/api/events/{handle_event}?locale=de&profile=self",
            headers=headers,
        )
        assert rv.status_code == 200
        event_dict = rv.json
        assert event_dict["type"] == "Adopted"
        # This being correctly translated tests that the type has been correctly
        # detected as a default type rather than a custom type
        assert event_dict["profile"]["type"] == "Adoptiert"
