#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025   David Straub
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

"""Tests for the /people/<handle>/ydna/ endpoint."""

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


def get_headers(client, user: str, password: str):
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def make_handle():
    return str(uuid.uuid4())


class TestYDnaEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API YDNA"
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

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_without_token(self):
        rv = self.client.get("/api/people/nope/ydna")
        assert rv.status_code == 401

    def test_person_not_found(self):
        headers = get_headers(self.client, "user", "123")
        rv = self.client.get("/api/people/nope/ydna", headers=headers)
        assert rv.status_code == 404

    def test_no_ydna(self):
        headers = get_headers(self.client, "admin", "123")
        person = {
            "primary_name": {
                "surname_list": [{"_class": "Surname", "surname": "Doe"}],
                "first_name": "John",
            },
            "gender": 1,
        }
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 201
        handle = rv.json[0]["handle"]
        rv = self.client.get(f"/api/people/{handle}/ydna", headers=headers)
        assert rv.status_code == 200
        assert rv.json == {}

    def test_with_ydna(self):
        headers = get_headers(self.client, "admin", "123")
        handle = make_handle()
        ydna_string = "M269+, CTS1078+, P312+, U106-, L21-, Z290-, Z2103+, FGC3845-"
        person = {
            "_class": "Person",
            "handle": handle,
            "primary_name": {
                "_class": "Name",
                "surname_list": [{"_class": "Surname", "surname": "Smith"}],
                "first_name": "Adam",
            },
            "gender": 1,
            "attribute_list": [
                {"_class": "Attribute", "type": "Y-DNA", "value": ydna_string}
            ],
        }
        rv = self.client.post("/api/objects/", json=[person], headers=headers)
        assert rv.status_code == 201
        rv = self.client.get(f"/api/people/{handle}/ydna", headers=headers)
        assert rv.status_code == 200
        assert "clade_lineage" in rv.json
        assert all(
            "name" in item and "age_info" in item for item in rv.json["clade_lineage"]
        )
        assert "raw_data" not in rv.json
        rv = self.client.get(f"/api/people/{handle}/ydna?raw=1", headers=headers)
        assert "raw_data" in rv.json
        assert rv.json["raw_data"] == ydna_string
