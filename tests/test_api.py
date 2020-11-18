#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Tests for the `gramps_webapi.api` module."""

import unittest
from unittest.mock import patch

import yaml
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Person, Surname
from jsonschema import validate
from pkg_resources import resource_filename

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_CONFIG


def _add_person(gender, first_name, surname, trans, db):
    person = Person()
    person.gender = gender
    _name = person.primary_name
    _name.first_name = first_name
    surname1 = Surname()
    surname1.surname = surname
    _name.set_surname_list([surname1])
    person.gramps_id = "person001"
    db.add_person(person, trans)


class TestPerson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_CONFIG}):
            cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        dbstate = self.app.config["DB_MANAGER"].get_db(force_unlock=True)
        with DbTxn("Add test objects", dbstate.db) as trans:
            _add_person(Person.MALE, "John", "Allen", trans, dbstate.db)
        dbstate.db.close()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_person_endpoint_404(self):
        rv = self.client.get("/api/people/does_not_exist")
        assert rv.status_code == 404

    def test_people_endpoint(self):
        rv = self.client.get("/api/people/?profile=all")
        it = rv.json[0]
        assert len(it["handle"]) > 20
        assert isinstance(it["change"], int)
        assert it["gramps_id"] == "person001"
        assert it["profile"]["name_given"] == "John"
        assert it["profile"]["name_surname"] == "Allen"
        assert it["gender"] == 1  # male
        assert it["birth_ref_index"] == -1
        assert it["death_ref_index"] == -1
        rv = self.client.get("/api/people/?gramps_id=person001&profile=all")
        it = rv.json[0]
        assert len(it["handle"]) > 20
        assert isinstance(it["change"], int)
        assert it["gramps_id"] == "person001"
        assert it["profile"]["name_given"] == "John"
        assert it["profile"]["name_surname"] == "Allen"
        assert it["gender"] == 1  # male
        assert it["birth_ref_index"] == -1
        assert it["death_ref_index"] == -1

    def test_person_endpoint(self):
        rv = self.client.get("/api/people/")
        it = rv.json[0]
        rv = self.client.get("/api/people/" + it["handle"] + "?profile=all")
        assert len(rv.json["handle"]) > 20
        assert isinstance(rv.json["change"], int)
        assert rv.json["gramps_id"] == "person001"
        assert rv.json["profile"]["name_given"] == "John"
        assert rv.json["profile"]["name_surname"] == "Allen"
        assert rv.json["gender"] == 1  # male
        assert rv.json["birth_ref_index"] == -1
        assert rv.json["death_ref_index"] == -1

    def test_token_endpoint(self):
        rv = self.client.post("/api/login/", data={})
        assert rv.status_code == 200
        assert rv.json == {"access_token": 1, "refresh_token": 1}

    def test_refresh_token_endpoint(self):
        rv = self.client.post("/api/refresh/")
        assert rv.status_code == 200
        assert rv.json == {"access_token": 1}

    def test_person_schema(self):
        with open(resource_filename("gramps_webapi", "data/apispec.yaml")) as f:
            api_schema = yaml.safe_load(f)
        person_schema = api_schema["definitions"]["Person"]
        for person in self.client.get("/api/people/").json:
            validate(instance=person, schema=person_schema)
