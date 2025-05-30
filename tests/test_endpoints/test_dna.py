#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023-25   David Straub
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

"""Tests for the /people/<handle>/dna/ endpoints."""

import os
import unittest
import uuid
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

MATCH1 = """chromosome,start,end,cMs,SNP
1,56950055,64247327,10.9,1404
5,850055,950055,12,1700
"""
MATCH2 = """chromosome	start	end	cMs	SNP	Side
2	56950055	64247327	10.9	1404	M"""
MATCH3 = """chromosome,start,end,cMs
X,56950055,64247327,10.9"""


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def make_handle() -> str:
    """Make a new valid handle."""
    return str(uuid.uuid4())


class TestDnaMatches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API DNA"
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

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_without_token(self):
        """Test without token."""
        rv = self.client.get("/api/people/nope/dna/matches")
        assert rv.status_code == 401

    def test_person_not_found(self):
        """Test with non-existing person."""
        headers = get_headers(self.client, "user", "123")
        rv = self.client.get("/api/people/nope/dna/matches", headers=headers)
        assert rv.status_code == 404

    def test_no_assoc(self):
        """Test without association."""
        headers = get_headers(self.client, "admin", "123")
        person = {
            "primary_name": {
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
        rv = self.client.post("/api/people/", json=person, headers=headers)
        assert rv.status_code == 201
        handle = rv.json[0]["handle"]
        rv = self.client.get(f"/api/people/{handle}/dna/matches", headers=headers)
        assert rv.status_code == 200
        assert rv.json == []

    def test_one(self):
        """Full test."""
        headers = get_headers(self.client, "admin", "123")
        handle_p1 = make_handle()
        handle_p2 = make_handle()
        handle_p3 = make_handle()
        handle_p4 = make_handle()
        handle_grandf = make_handle()
        handle_f1 = make_handle()
        handle_f2 = make_handle()
        handle_f3 = make_handle()
        handle_n1 = make_handle()
        handle_n2 = make_handle()
        handle_n3 = make_handle()
        handle_c = make_handle()
        objects = [
            {
                "_class": "Person",
                "handle": handle_p1,
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
                "person_ref_list": [
                    {
                        "_class": "PersonRef",
                        "note_list": [handle_n1, handle_n2],
                        "citation_list": [handle_c],
                        "rel": "DNA",
                        "ref": handle_p2,
                    }
                ],
            },
            {
                "_class": "Person",
                "handle": handle_p2,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [
                        {
                            "_class": "Surname",
                            "surname": "Mustermann",
                        }
                    ],
                    "first_name": "Max",
                },
                "gender": 1,
            },
            {
                "_class": "Person",
                "handle": handle_p3,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [
                        {
                            "_class": "Surname",
                            "surname": "Mustermann",
                        }
                    ],
                    "first_name": "Mother",
                },
                "gender": 0,
            },
            {
                "_class": "Person",
                "handle": handle_p4,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [
                        {
                            "_class": "Surname",
                            "surname": "Doe",
                        }
                    ],
                    "first_name": "Father",
                },
                "gender": 1,
            },
            {
                "_class": "Person",
                "handle": handle_grandf,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [
                        {
                            "_class": "Surname",
                            "surname": "Doe",
                        }
                    ],
                    "first_name": "Grandfather",
                },
                "gender": 1,
            },
            {
                "_class": "Family",
                "handle": handle_f1,
                "father_handle": handle_p4,
                "child_ref_list": [{"_class": "ChildRef", "ref": handle_p1}],
            },
            {
                "_class": "Family",
                "handle": handle_f2,
                "mother_handle": handle_p3,
                "child_ref_list": [{"_class": "ChildRef", "ref": handle_p2}],
            },
            {
                "_class": "Family",
                "handle": handle_f3,
                "father_handle": handle_grandf,
                "child_ref_list": [
                    {"_class": "ChildRef", "ref": handle_p3},
                    {"_class": "ChildRef", "ref": handle_p4},
                ],
            },
            {
                "_class": "Citation",
                "handle": handle_c,
                "note_list": [handle_n3],
            },
            {
                "_class": "Note",
                "handle": handle_n1,
                "text": {"_class": "StyledText", "string": MATCH1},
            },
            {
                "_class": "Note",
                "handle": handle_n2,
                "text": {"_class": "StyledText", "string": MATCH2},
            },
            {
                "_class": "Note",
                "handle": handle_n3,
                "text": {"_class": "StyledText", "string": MATCH3},
            },
        ]
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get(
            f"/api/people/{handle_p1}/dna/matches?locale=fr", headers=headers
        )
        assert rv.status_code == 200
        assert len(rv.json) == 1
        data = rv.json[0]
        assert data["handle"] == handle_p2
        assert data["ancestor_handles"] == [handle_grandf]
        assert data["relation"] == "le premier cousin"
        assert len(data["segments"]) == 4
        assert data["segments"][0] == {
            "chromosome": "1",
            "start": 56950055,
            "stop": 64247327,
            "side": "P",
            "cM": 10.9,
            "SNPs": 1404,
            "comment": "",
        }
        assert data["segments"][1] == {
            "chromosome": "5",
            "start": 850055,
            "stop": 950055,
            "side": "P",
            "cM": 12,
            "SNPs": 1700,
            "comment": "",
        }
        assert data["segments"][2] == {
            "chromosome": "2",
            "start": 56950055,
            "stop": 64247327,
            "side": "M",
            "cM": 10.9,
            "SNPs": 1404,
            "comment": "",
        }
        assert data["segments"][3] == {
            "chromosome": "X",
            "start": 56950055,
            "stop": 64247327,
            "side": "P",
            "cM": 10.9,
            "SNPs": 0,
            "comment": "",
        }
        # empty string
        rv = self.client.post(
            f"/api/parsers/dna-match", headers=headers, json={"string": ""}
        )
        assert rv.status_code == 200
        assert rv.json == []
        rv = self.client.post(
            f"/api/parsers/dna-match", headers=headers, json={"string": MATCH1}
        )
        assert rv.status_code == 200
        data = rv.json
        assert data
        assert len(data) == 2
