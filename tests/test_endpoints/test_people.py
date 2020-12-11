#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Tests for the /api/people endpoints using example_gramps."""

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


class TestPeople(unittest.TestCase):
    """Test cases for the /api/people endpoint for a list of people."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_people_endpoint(self):
        """Test reponse for people."""
        # check expected number of people found
        result = self.client.get("/api/people/")
        self.assertEqual(len(result.json), get_object_count("people"))
        # checked number passed back in header as well
        count = result.headers.pop("X-Total-Count")
        self.assertEqual(count, str(get_object_count("people")))
        # check first record is expected person
        self.assertEqual(result.json[0]["gramps_id"], "I2110")
        self.assertEqual(result.json[0]["primary_name"]["first_name"], "محمد")
        self.assertEqual(
            result.json[0]["primary_name"]["surname_list"][0]["surname"], ""
        )
        # check last record is expected person
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "I0247")
        self.assertEqual(result.json[last]["primary_name"]["first_name"], "Allen")
        self.assertEqual(
            result.json[last]["primary_name"]["surname_list"][0]["surname"], "鈴木"
        )

    def test_people_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/people/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_people_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {"gramps_id": "I0044", "handle": "GNUJQCL9MD64AM56OH"}
        run_test_endpoint_gramps_id(self, "/api/people/", driver)

    def test_people_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/people/")

    def test_people_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self, "/api/people/", ["handle", "primary_name", "event_ref_list"]
        )

    def test_people_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/people/", ["handle", "lds_ord_list", "person_ref_list"]
        )

    def test_people_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"IsMale"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"IsMale"}]}',
                '{"function":"none","rules":[{"name":"IsMale"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"HasUnknownGender"}]}',
                '{"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}',
                '{"function":"or","rules":[{"name":"HasTag",'
                + '"values":["complete"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"function":"xor","rules":[{"name":"IsFemale"},'
                + '{"name":"MultipleMarriages"}]}',
                '{"function":"one","rules":[{"name":"IsFemale"},'
                + '{"name":"MultipleMarriages"}]}',
                '{"invert":true,"rules":[{"name":"IsMale"},'
                + '{"name":"MultipleMarriages"}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/people/", driver)

    def test_people_endpoint_profile(self):
        """Test response for missing or bad parm."""
        # check 422 returned if passed argument
        result = self.client.get("/api/people/?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/people/?profile=3")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/people/?profile=alpha")
        self.assertEqual(result.status_code, 422)
        # check expected number of people found
        result = self.client.get("/api/people/?profile=all")
        self.assertEqual(len(result.json), get_object_count("people"))
        # check all expected profile attributes present for first person
        self.assertEqual(
            result.json[0]["profile"],
            {
                "birth": {
                    "age": "0 days",
                    "date": "570-04-19",
                    "place": "",
                    "type": "Birth",
                },
                "death": {
                    "age": "62 years, 1 months, 19 days",
                    "date": "632-06-08",
                    "place": "",
                    "type": "Death",
                },
                "events": [
                    {
                        "age": "0 days",
                        "date": "570-04-19",
                        "place": "",
                        "type": "Birth",
                    },
                    {
                        "age": "62 years, 1 months, 19 days",
                        "date": "632-06-08",
                        "place": "",
                        "type": "Death",
                    },
                    {
                        "age": "39 years, 8 months, 13 days",
                        "date": "610",
                        "place": "",
                        "type": "Marriage",
                    },
                ],
                "families": [
                    {
                        "children": [],
                        "divorce": {},
                        "events": [],
                        "father": {
                            "birth": {
                                "age": "0 days",
                                "date": "570-04-19",
                                "place": "",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "62 years, 1 months, 19 days",
                                "date": "632-06-08",
                                "place": "",
                                "type": "Death",
                            },
                            "handle": "cc8205d872f532ab14e",
                            "gramps_id": "I2110",
                            "name_given": "محمد",
                            "name_surname": "",
                            "sex": "M",
                        },
                        "handle": "cc8205d874433c12fd8",
                        "gramps_id": "F0743",
                        "marriage": {},
                        "mother": {
                            "birth": {},
                            "death": {},
                            "handle": "cc8205d87831c772e87",
                            "gramps_id": "I2105",
                            "name_given": "عائشة",
                            "name_surname": "",
                            "sex": "F",
                        },
                        "relationship": "Married",
                    },
                    {
                        "children": [
                            {
                                "birth": {},
                                "death": {},
                                "handle": "cc8205d87fd529000ff",
                                "gramps_id": "I2107",
                                "name_given": "القاسم",
                                "name_surname": "",
                                "sex": "M",
                            },
                            {
                                "birth": {},
                                "death": {},
                                "handle": "cc8205d883763f02abd",
                                "gramps_id": "I2108",
                                "name_given": "عبد الله",
                                "name_surname": "",
                                "sex": "M",
                            },
                            {
                                "birth": {},
                                "death": {},
                                "handle": "cc8205d887376aacba2",
                                "gramps_id": "I2109",
                                "name_given": "أم كلثوم",
                                "name_surname": "",
                                "sex": "F",
                            },
                        ],
                        "divorce": {},
                        "events": [],
                        "father": {
                            "birth": {
                                "age": "0 days",
                                "date": "570-04-19",
                                "place": "",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "62 years, 1 months, 19 days",
                                "date": "632-06-08",
                                "place": "",
                                "type": "Death",
                            },
                            "handle": "cc8205d872f532ab14e",
                            "gramps_id": "I2110",
                            "name_given": "محمد",
                            "name_surname": "",
                            "sex": "M",
                        },
                        "gramps_id": "F0744",
                        "handle": "cc8205d87492b90b437",
                        "marriage": {},
                        "mother": {
                            "birth": {},
                            "death": {},
                            "gramps_id": "I2106",
                            "handle": "cc8205d87c20350420b",
                            "name_given": "خديجة",
                            "name_surname": "",
                            "sex": "F",
                        },
                        "relationship": "Married",
                    },
                ],
                "handle": "cc8205d872f532ab14e",
                "gramps_id": "I2110",
                "name_given": "محمد",
                "name_surname": "",
                "other_parent_families": [],
                "primary_parent_family": {},
                "sex": "M",
            },
        )

    def test_people_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "event_ref_list", "key": "events", "type": List},
            {"arg": "families", "key": "families", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "parent_families", "key": "parent_families", "type": List},
            {"arg": "person_ref_list", "key": "people", "type": List},
            {
                "arg": "primary_parent_family",
                "key": "primary_parent_family",
                "type": Dict,
            },
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/people/", driver, ["I0044"])

    def test_people_endpoint_schema(self):
        """Test all people against the people schema."""
        # check expected number of people found
        result = self.client.get("/api/people/?extend=all&profile=all")
        self.assertEqual(len(result.json), get_object_count("people"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for person in result.json:
            validate(
                instance=person,
                schema=API_SCHEMA["definitions"]["Person"],
                resolver=resolver,
            )


class TestPeopleHandle(unittest.TestCase):
    """Test cases for the /api/people/{handle} endpoint for a specific person."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_people_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent person
        result = self.client.get("/api/people/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_people_handle_endpoint(self):
        """Test response for specific person."""
        # check expected person returned
        result = self.client.get("/api/people/GNUJQCL9MD64AM56OH")
        self.assertEqual(result.json["gramps_id"], "I0044")
        self.assertEqual(result.json["primary_name"]["first_name"], "Lewis Anderson")
        self.assertEqual(
            result.json["primary_name"]["surname_list"][1]["surname"], "Zieliński"
        )

    def test_people_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/people/GNUJQCL9MD64AM56OH?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_people_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/people/1QTJQCP5QMT2X7YJDK")

    def test_people_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/people/1QTJQCP5QMT2X7YJDK",
            ["handle", "primary_name", "event_ref_list"],
        )

    def test_people_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/people/1QTJQCP5QMT2X7YJDK",
            ["handle", "lds_ord_list", "person_ref_list"],
        )

    def test_people_handle_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed no or bad argument
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=1")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=omega")
        self.assertEqual(result.status_code, 422)
        # check some request variations work
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=self")
        self.assertNotIn("events", result.json["profile"])
        self.assertNotIn("families", result.json["profile"])
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=families")
        self.assertIn("families", result.json["profile"])
        self.assertNotIn("events", result.json["profile"])
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=events")
        self.assertIn("events", result.json["profile"])
        self.assertNotIn("families", result.json["profile"])
        # check key expected profile attributes present for full request
        result = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=all")
        self.assertEqual(
            result.json["profile"],
            {
                "birth": {
                    "age": "0 days",
                    "date": "1906-09-05",
                    "place": "Central City, Muhlenberg, KY, USA",
                    "type": "Birth",
                },
                "death": {
                    "age": "86 years, 9 months, 1 days",
                    "date": "1993-06-06",
                    "place": "Sevierville, TN, USA",
                    "type": "Death",
                },
                "events": [
                    {
                        "age": "0 days",
                        "date": "1906-09-05",
                        "place": "Central City, Muhlenberg, KY, USA",
                        "type": "Birth",
                    },
                    {
                        "age": "86 years, 9 months, 1 days",
                        "date": "1993-06-06",
                        "place": "Sevierville, TN, USA",
                        "type": "Death",
                    },
                    {
                        "age": "86 years, 9 months, 3 days",
                        "date": "1993-06-08",
                        "place": "Wenatchee, WA, USA",
                        "type": "Burial",
                    },
                ],
                "families": [],
                "gramps_id": "I0138",
                "handle": "0PWJQCZYFXOS0HGREE",
                "name_given": "Mary Grace Elizabeth",
                "name_surname": "Warner",
                "other_parent_families": [],
                "primary_parent_family": {
                    "children": [
                        {
                            "birth": {
                                "age": "0 days",
                                "date": "1889-08-11",
                                "place": "Panama City, Bay, FL, USA",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "72 years, 1 days",
                                "date": "1961-08-12",
                                "place": "Butte, MT, USA",
                                "type": "Death",
                            },
                            "handle": "ENTJQCZXQV1IRKJXUL",
                            "gramps_id": "I0020",
                            "name_given": "Martin Bogarte",
                            "name_surname": "Warner",
                            "sex": "M",
                        },
                        {
                            "birth": {
                                "age": "0 days",
                                "date": "1892-09-25",
                                "place": "New Castle, Henry, IN, USA",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "78 years, 2 months, 22 days",
                                "date": "1970-12-17",
                                "place": "",
                                "type": "Death",
                            },
                            "handle": "4OWJQC0KHBI9AR3QX3",
                            "gramps_id": "I0137",
                            "name_given": "Julia Angeline",
                            "name_surname": "Warner",
                            "sex": "F",
                        },
                        {
                            "birth": {
                                "age": "0 days",
                                "date": "1906-09-05",
                                "place": "Central City, Muhlenberg, KY, USA",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "86 years, 9 months, 1 days",
                                "date": "1993-06-06",
                                "place": "Sevierville, TN, USA",
                                "type": "Death",
                            },
                            "handle": "0PWJQCZYFXOS0HGREE",
                            "gramps_id": "I0138",
                            "name_given": "Mary Grace Elizabeth",
                            "name_surname": "Warner",
                            "sex": "F",
                        },
                    ],
                    "divorce": {},
                    "events": [
                        {
                            "date": "1888-08-09",
                            "place": "Springfield, Sangamon, IL, USA",
                            "span": "0 days",
                            "type": "Marriage",
                        }
                    ],
                    "father": {
                        "birth": {
                            "age": "0 days",
                            "date": "1867-01-23",
                            "place": "Durango, La Plata, CO, USA",
                            "type": "Birth",
                        },
                        "death": {
                            "age": "52 years, 1 months, 18 days",
                            "date": "1919-03-10",
                            "place": "Kokomo, Howard, IN, USA",
                            "type": "Death",
                        },
                        "handle": "SOTJQCKJPETYI38BRM",
                        "gramps_id": "I0021",
                        "name_given": "Warren W.",
                        "name_surname": "Warner",
                        "sex": "M",
                    },
                    "handle": "LOTJQC78O5B4WQGJRP",
                    "gramps_id": "F0004",
                    "marriage": {
                        "date": "1888-08-09",
                        "place": "Springfield, Sangamon, IL, USA",
                        "span": "0 days",
                        "type": "Marriage",
                    },
                    "mother": {
                        "birth": {
                            "age": "0 days",
                            "date": "1869-07-08",
                            "place": "Oxnard, Ventura, CA, USA",
                            "type": "Birth",
                        },
                        "death": {
                            "age": "72 years, 9 months, 13 days",
                            "date": "1942-04-21",
                            "place": "Kokomo, Howard, IN, USA",
                            "type": "Death",
                        },
                        "handle": "1QTJQCP5QMT2X7YJDK",
                        "gramps_id": "I0022",
                        "name_given": "Abigail",
                        "name_surname": "Ball",
                        "sex": "F",
                    },
                    "relationship": "Married",
                },
                "sex": "F",
            },
        )

    def test_people_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "event_ref_list", "key": "events", "type": List},
            {"arg": "families", "key": "families", "type": List},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "parent_families", "key": "parent_families", "type": List},
            {"arg": "person_ref_list", "key": "people", "type": List},
            {
                "arg": "primary_parent_family",
                "key": "primary_parent_family",
                "type": Dict,
            },
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/people/0PWJQCZYFXOS0HGREE", driver)

    def test_people_handle_endpoint_schema(self):
        """Test the people schema with extensions."""
        # check person record conforms to expected schema
        result = self.client.get(
            "/api/people/0PWJQCZYFXOS0HGREE?extend=all&profile=all"
        )
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Person"],
            resolver=resolver,
        )

    def test_people_handle_endpoint_backlinks(self):
        """Test the people handle endpoint with backlinks."""
        # check person record conforms to expected schema
        rv = self.client.get("/api/people/SOTJQCKJPETYI38BRM")
        assert "backlinks" not in rv.json
        rv = self.client.get("/api/people/SOTJQCKJPETYI38BRM?backlinks=1")
        assert "backlinks" in rv.json
        assert rv.json["backlinks"] == {
            "family": ["LOTJQC78O5B4WQGJRP", "UPTJQC4VPCABZUDB75"]
        }

    def test_people_handle_endpoint_backlinks_extended(self):
        """Test the people handle endpoint with extended backlinks."""
        # check person record conforms to expected schema
        rv = self.client.get(
            "/api/people/SOTJQCKJPETYI38BRM?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv.json
        assert "extended" in rv.json
        assert "backlinks" in rv.json["extended"]
        backlinks = rv.json["extended"]["backlinks"]
        assert backlinks["family"][0]["handle"] == "LOTJQC78O5B4WQGJRP"
        assert backlinks["family"][1]["handle"] == "UPTJQC4VPCABZUDB75"

    def test_people_endpoint_backlinks(self):
        """Test the people endpoint with backlinks."""
        rv = self.client.get("/api/people/?gramps_id=I0021")
        assert "backlinks" not in rv.json
        rv = self.client.get("/api/people/?gramps_id=I0021&backlinks=1")
        assert "backlinks" in rv.json[0]
        assert rv.json[0]["backlinks"] == {
            "family": ["LOTJQC78O5B4WQGJRP", "UPTJQC4VPCABZUDB75"]
        }
