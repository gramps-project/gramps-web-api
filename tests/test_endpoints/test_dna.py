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

from gramps_webapi.api.resources.dna import get_side, is_x_chromosome
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
MATCH4 = """chromosome,start,end,cMs
1,56950055,64247327,10.9
X,56950055,64247327,10.9"""


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def make_handle() -> str:
    """Make a new valid handle."""
    return str(uuid.uuid4())


def make_person(handle, first_name, gender, matches=(), note_handle=None):
    """Make a person object with DNA associations to the matches."""
    return {
        "_class": "Person",
        "handle": handle,
        "primary_name": {
            "_class": "Name",
            "surname_list": [{"_class": "Surname", "surname": "Doe"}],
            "first_name": first_name,
        },
        "gender": gender,
        "person_ref_list": [
            {
                "_class": "PersonRef",
                "ref": match_handle,
                "rel": "DNA",
                "note_list": [note_handle],
            }
            for match_handle in matches
        ],
    }


def make_family(handle, father=None, mother=None, children=()):
    """Make a family object."""
    family = {
        "_class": "Family",
        "handle": handle,
        "child_ref_list": [{"_class": "ChildRef", "ref": child} for child in children],
    }
    if father:
        family["father_handle"] = father
    if mother:
        family["mother_handle"] = mother
    return family


def make_note(handle, text):
    """Make a note object."""
    return {
        "_class": "Note",
        "handle": handle,
        "text": {"_class": "StyledText", "string": text},
    }


class TestGetSide(unittest.TestCase):
    """Tests for the side rule, independent of the order of the paths."""

    def test_unrelated(self):
        assert get_side([(-1, None, "", [], "", [])]) == "U"

    def test_one_side(self):
        data = [(4, "h1", "ff", [], "ff", []), (4, "h2", "fm", [], "fm", [])]
        assert get_side(data) == "P"
        assert get_side([(2, "h1", "f", [], "f", [])]) == "P"
        assert get_side([(2, "h1", "m", [], "m", [])]) == "M"

    def test_both_sides(self):
        for data in [
            [(4, "h1", "ff", [], "ff", []), (4, "h2", "mf", [], "mf", [])],
            [(4, "h2", "mf", [], "mf", []), (4, "h1", "ff", [], "ff", [])],
        ]:
            assert get_side(data) == "U"

    def test_longer_path_ignored(self):
        for data in [
            [(2, "h1", "f", [], "f", []), (6, "h2", "mmm", [], "mmm", [])],
            [(6, "h2", "mmm", [], "mmm", []), (2, "h1", "f", [], "f", [])],
        ]:
            assert get_side(data) == "P"

    def test_sibling_or_ancestor(self):
        assert get_side([(1, "h1", "s", [], "", [])]) == "U"
        assert get_side([(1, "h1", "", [], "f", [])]) == "U"
        data = [(2, "h1", "f", [], "f", []), (2, "h2", "", [], "mf", [])]
        assert get_side(data) == "U"

    def test_is_x_chromosome(self):
        for label in ["X", "x", "23", "chrX", "chr23", " X "]:
            assert is_x_chromosome(label)
        for label in ["1", "22", "Y", "24", "MT", "chr7", ""]:
            assert not is_x_chromosome(label)


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

    def test_direct_line_side(self):
        """Test the side when the person is a parent or grandparent of the match."""
        headers = get_headers(self.client, "admin", "123")
        handle_grandf = make_handle()
        handle_father = make_handle()
        handle_son = make_handle()
        handle_f1 = make_handle()
        handle_f2 = make_handle()
        handle_n = make_handle()

        def person(handle, first_name, match_handle):
            return {
                "_class": "Person",
                "handle": handle,
                "primary_name": {
                    "_class": "Name",
                    "surname_list": [{"_class": "Surname", "surname": "Doe"}],
                    "first_name": first_name,
                },
                "gender": 1,
                "person_ref_list": [
                    {
                        "_class": "PersonRef",
                        "ref": match_handle,
                        "rel": "DNA",
                        "note_list": [handle_n],
                    }
                ],
            }

        objects = [
            person(handle_grandf, "Grandfather", handle_son),
            person(handle_father, "Father", handle_son),
            person(handle_son, "Son", handle_father),
            {
                "_class": "Family",
                "handle": handle_f1,
                "father_handle": handle_grandf,
                "child_ref_list": [{"_class": "ChildRef", "ref": handle_father}],
            },
            {
                "_class": "Family",
                "handle": handle_f2,
                "father_handle": handle_father,
                "child_ref_list": [{"_class": "ChildRef", "ref": handle_son}],
            },
            {
                "_class": "Note",
                "handle": handle_n,
                "text": {"_class": "StyledText", "string": MATCH1},
            },
        ]
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        assert rv.status_code == 201
        # the son inherited the shared DNA from his father: paternal side
        rv = self.client.get(f"/api/people/{handle_son}/dna/matches", headers=headers)
        assert rv.status_code == 200
        assert {segment["side"] for segment in rv.json[0]["segments"]} == {"P"}
        # for the father and the grandfather, the side is unknown
        for handle in [handle_father, handle_grandf]:
            rv = self.client.get(f"/api/people/{handle}/dna/matches", headers=headers)
            assert rv.status_code == 200
            assert len(rv.json) == 1
            assert {segment["side"] for segment in rv.json[0]["segments"]} == {"U"}

    def _post_objects(self, objects):
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        assert rv.status_code == 201

    def _get_sides(self, handle):
        """Get the sides of the segments of the person's only match."""
        headers = get_headers(self.client, "admin", "123")
        rv = self.client.get(f"/api/people/{handle}/dna/matches", headers=headers)
        assert rv.status_code == 200
        assert len(rv.json) == 1
        return {
            (segment["chromosome"], segment["side"])
            for segment in rv.json[0]["segments"]
        }

    def test_side_ancestor_and_parent_of_parent(self):
        """Test a person who is both a grandparent and an uncle of the match."""
        # X is G's father; G is D's father; X and D are M's parents
        h_x, h_g, h_d, h_m = (make_handle() for _ in range(4))
        h_f1, h_f2, h_f3, h_n = (make_handle() for _ in range(4))
        self._post_objects(
            [
                make_person(h_x, "X", 1),
                make_person(h_g, "G", 1, matches=[h_m], note_handle=h_n),
                make_person(h_d, "D", 0),
                make_person(h_m, "M", 1),
                make_family(h_f1, father=h_x, children=[h_g]),
                make_family(h_f2, father=h_g, children=[h_d]),
                make_family(h_f3, father=h_x, mother=h_d, children=[h_m]),
                make_note(h_n, MATCH1),
            ]
        )
        assert self._get_sides(h_g) == {("1", "U"), ("5", "U")}

    def test_side_parentless_siblings(self):
        """Test siblings in a family without parents."""
        h_p, h_s, h_f, h_n = (make_handle() for _ in range(4))
        self._post_objects(
            [
                make_person(h_p, "P", 1, matches=[h_s], note_handle=h_n),
                make_person(h_s, "S", 1),
                make_family(h_f, children=[h_p, h_s]),
                make_note(h_n, MATCH1),
            ]
        )
        # the sibling's DNA can come from either of P's parents
        assert self._get_sides(h_p) == {("1", "U"), ("5", "U")}

    def test_side_parentless_nephew(self):
        """Test a nephew through a sibling in a family without parents."""
        # P and S are children of a family without parents; S is M's mother
        h_p, h_s, h_m = (make_handle() for _ in range(3))
        h_f1, h_f2, h_n = (make_handle() for _ in range(3))
        self._post_objects(
            [
                make_person(h_p, "P", 1, matches=[h_m], note_handle=h_n),
                make_person(h_s, "S", 0),
                make_person(h_m, "M", 1, matches=[h_p], note_handle=h_n),
                make_family(h_f1, children=[h_p, h_s]),
                make_family(h_f2, mother=h_s, children=[h_m]),
                make_note(h_n, MATCH1),
            ]
        )
        # the uncle's side is unknown, the nephew's is his mother's
        assert self._get_sides(h_p) == {("1", "U"), ("5", "U")}
        assert self._get_sides(h_m) == {("1", "M"), ("5", "M")}

    def test_side_double_first_cousins(self):
        """Test double first cousins."""
        # two brothers married two sisters
        h_gf1, h_gm1, h_gf2, h_gm2 = (make_handle() for _ in range(4))
        h_f1, h_f2, h_m1, h_m2 = (make_handle() for _ in range(4))
        h_a, h_b, h_n = (make_handle() for _ in range(3))
        h_fam = [make_handle() for _ in range(4)]
        self._post_objects(
            [
                make_person(h_gf1, "GF1", 1),
                make_person(h_gm1, "GM1", 0),
                make_person(h_gf2, "GF2", 1),
                make_person(h_gm2, "GM2", 0),
                make_person(h_f1, "F1", 1),
                make_person(h_f2, "F2", 1),
                make_person(h_m1, "M1", 0),
                make_person(h_m2, "M2", 0),
                make_person(h_a, "A", 1, matches=[h_b], note_handle=h_n),
                make_person(h_b, "B", 1),
                make_family(
                    h_fam[0], father=h_gf1, mother=h_gm1, children=[h_f1, h_f2]
                ),
                make_family(
                    h_fam[1], father=h_gf2, mother=h_gm2, children=[h_m1, h_m2]
                ),
                make_family(h_fam[2], father=h_f1, mother=h_m1, children=[h_a]),
                make_family(h_fam[3], father=h_f2, mother=h_m2, children=[h_b]),
                make_note(h_n, MATCH1),
            ]
        )
        assert self._get_sides(h_a) == {("1", "U"), ("5", "U")}

    def test_side_relationship_loop(self):
        """Test the single tuple returned when a relationship loop is detected."""
        h_a, h_b, h_n = (make_handle() for _ in range(3))
        self._post_objects(
            [
                make_person(h_a, "A", 1, matches=[h_b], note_handle=h_n),
                make_person(h_b, "B", 1),
                make_note(h_n, MATCH1),
            ]
        )
        loop_result = ((-1, None, -1, [], -1, []), ["Relationship loop detected"])
        with patch(
            "gramps.gen.relationship.RelationshipCalculator.get_relationship_distance_new",
            return_value=loop_result,
        ):
            assert self._get_sides(h_a) == {("1", "U"), ("5", "U")}

    def test_side_x_chromosome(self):
        """Test that a male's X chromosome is maternal."""
        h_f, h_d, h_s, h_fam, h_n = (make_handle() for _ in range(5))
        self._post_objects(
            [
                make_person(h_f, "Father", 1, matches=[h_d], note_handle=h_n),
                make_person(h_d, "Daughter", 0, matches=[h_f], note_handle=h_n),
                make_person(h_s, "Son", 1, matches=[h_f], note_handle=h_n),
                make_family(h_fam, father=h_f, children=[h_d, h_s]),
                make_note(h_n, MATCH4),
            ]
        )
        # the father's X always comes from his mother
        assert self._get_sides(h_f) == {("1", "U"), ("X", "M")}
        # a daughter's X from her father is paternal
        assert self._get_sides(h_d) == {("1", "P"), ("X", "P")}
        # a son never has his father's X
        assert self._get_sides(h_s) == {("1", "P"), ("X", "M")}

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
        assert len(data["ancestor_profiles"]) == 1
        assert data["ancestor_profiles"][0]["handle"] == handle_grandf
        assert data["ancestor_profiles"][0]["name_given"] == "Grandfather"
        assert data["ancestor_profiles"][0]["name_surname"] == "Doe"
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
            # John is male, so his X is maternal
            "side": "M",
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
