"""Tests for the /api/people endpoints using example_gramps."""

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


class TestPeople(unittest.TestCase):
    """Test cases for the /api/people endpoint for a list of people."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_people_endpoint(self):
        """Test reponse for people."""
        # check expected number of people found
        rv = self.client.get("/api/people/")
        assert len(rv.json) == get_object_count("people")
        # check first record is expected person
        assert rv.json[0]["gramps_id"] == "I0552"
        assert rv.json[0]["primary_name"]["first_name"] == "Martha"
        assert rv.json[0]["primary_name"]["surname_list"][0]["surname"] == "Nielsen"
        # check last record is expected person
        last = len(rv.json) - 1
        assert rv.json[last]["gramps_id"] == "I2156"
        assert rv.json[last]["primary_name"]["first_name"] == "蘭"
        assert rv.json[last]["primary_name"]["surname_list"][0]["surname"] == "賈"

    def test_people_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/people/?junk_parm=1")
        assert rv.status_code == 422

    def test_people_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {"gramps_id": "I0044", "handle": "GNUJQCL9MD64AM56OH"}
        run_test_endpoint_gramps_id(self.client, "/api/people/", driver)

    def test_people_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/people/")

    def test_people_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client, "/api/people/", ["handle", "primary_name", "event_ref_list"]
        )

    def test_people_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client, "/api/people/", ["handle", "lds_ord_list", "person_ref_list"]
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
                '{"function":"or","rules":[{"name":"HasTag","values":["complete"]},{"name":"HasTag","values":["ToDo"]}]}',
                '{"function":"xor","rules":[{"name":"IsFemale"},{"name":"MultipleMarriages"}]}',
                '{"function":"one","rules":[{"name":"IsFemale"},{"name":"MultipleMarriages"}]}',
                '{"invert":true,"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}',
            ],
        }
        run_test_endpoint_rules(self.client, "/api/people/", driver)

    def test_people_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed argument
        rv = self.client.get("/api/people/?profile=1")
        assert rv.status_code == 422
        # check expected number of people found
        rv = self.client.get("/api/people/?profile")
        assert len(rv.json) == get_object_count("people")
        # check all expected profile attributes present for first person
        assert rv.json[0]["profile"] == {
            "birth": {},
            "death": {},
            "events": [],
            "families": [
                {
                    "children": [
                        {
                            "birth": {
                                "date": "after 1737-10-01",
                                "place": "Maryville, MO, USA",
                                "type": "Birth",
                            },
                            "death": {
                                "date": "1787-05-20",
                                "place": "Wooster, OH, USA",
                                "type": "Death",
                            },
                            "handle": "E04KQC637O9JLP5PNM",
                            "name_given": "John",
                            "name_surname": "Adkins",
                            "sex": "M",
                        }
                    ],
                    "divorce": {},
                    "events": [{"date": "", "place": "", "type": "Marriage"}],
                    "father": {
                        "birth": {
                            "date": "",
                            "place": "Ketchikan, AK, USA",
                            "type": "Birth",
                        },
                        "death": {},
                        "handle": "JZ3KQCSRW7R368NLSH",
                        "name_given": "Robert Sr.",
                        "name_surname": "Adkins",
                        "sex": "M",
                    },
                    "handle": "TZ3KQCJ3PNQHI6S8VO",
                    "marriage": {"date": "", "place": "", "type": "Marriage"},
                    "mother": {
                        "birth": {},
                        "death": {},
                        "handle": "004KQCGYT27EEPQHK",
                        "name_given": "Martha",
                        "name_surname": "Nielsen",
                        "sex": "F",
                    },
                    "relationship": "Married",
                }
            ],
            "handle": "004KQCGYT27EEPQHK",
            "name_given": "Martha",
            "name_surname": "Nielsen",
            "other_parent_families": [],
            "primary_parent_family": {},
            "sex": "F",
        }

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
        run_test_endpoint_extend(self.client, "/api/people/", driver, ["I0044"])

    def test_people_endpoint_schema(self):
        """Test all people against the people schema."""
        # check expected number of people found
        rv = self.client.get("/api/people/?extend=all&profile")
        assert len(rv.json) == get_object_count("people")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for person in rv.json:
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
        rv = self.client.get("/api/people/does_not_exist")
        assert rv.status_code == 404

    def test_people_handle_endpoint(self):
        """Test response for specific person."""
        # check expected person returned
        rv = self.client.get("/api/people/GNUJQCL9MD64AM56OH")
        assert rv.json["gramps_id"] == "I0044"
        assert rv.json["primary_name"]["first_name"] == "Lewis Anderson"
        assert rv.json["primary_name"]["surname_list"][1]["surname"] == "Zieliński"

    def test_people_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        rv = self.client.get("/api/people/GNUJQCL9MD64AM56OH?junk_parm=1")
        assert rv.status_code == 422

    def test_people_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self.client, "/api/people/1QTJQCP5QMT2X7YJDK")

    def test_people_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self.client,
            "/api/people/1QTJQCP5QMT2X7YJDK",
            ["handle", "primary_name", "event_ref_list"],
        )

    def test_people_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self.client,
            "/api/people/1QTJQCP5QMT2X7YJDK",
            ["handle", "lds_ord_list", "person_ref_list"],
        )

    def test_people_handle_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed argument
        rv = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile=1")
        assert rv.status_code == 422
        # check some key expected profile attributes present
        rv = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?profile")
        assert rv.json["profile"] == {
            "birth": {
                "date": "1906-09-05",
                "place": "Central City, Muhlenberg, KY, USA",
                "type": "Birth",
            },
            "death": {
                "date": "1993-06-06",
                "place": "Sevierville, TN, USA",
                "type": "Death",
            },
            "events": [
                {
                    "date": "1906-09-05",
                    "place": "Central City, Muhlenberg, KY, USA",
                    "type": "Birth",
                },
                {
                    "date": "1993-06-06",
                    "place": "Sevierville, TN, USA",
                    "type": "Death",
                },
                {"date": "1993-06-08", "place": "Wenatchee, WA, USA", "type": "Burial"},
            ],
            "families": [],
            "handle": "0PWJQCZYFXOS0HGREE",
            "name_given": "Mary Grace Elizabeth",
            "name_surname": "Warner",
            "other_parent_families": [],
            "primary_parent_family": {
                "children": [
                    {
                        "birth": {
                            "date": "1889-08-11",
                            "place": "Panama City, Bay, FL, USA",
                            "type": "Birth",
                        },
                        "death": {
                            "date": "1961-08-12",
                            "place": "Butte, MT, USA",
                            "type": "Death",
                        },
                        "handle": "ENTJQCZXQV1IRKJXUL",
                        "name_given": "Martin Bogarte",
                        "name_surname": "Warner",
                        "sex": "M",
                    },
                    {
                        "birth": {
                            "date": "1892-09-25",
                            "place": "New Castle, Henry, IN, USA",
                            "type": "Birth",
                        },
                        "death": {"date": "1970-12-17", "place": "", "type": "Death"},
                        "handle": "4OWJQC0KHBI9AR3QX3",
                        "name_given": "Julia Angeline",
                        "name_surname": "Warner",
                        "sex": "F",
                    },
                    {
                        "birth": {
                            "date": "1906-09-05",
                            "place": "Central City, Muhlenberg, KY, USA",
                            "type": "Birth",
                        },
                        "death": {
                            "date": "1993-06-06",
                            "place": "Sevierville, TN, USA",
                            "type": "Death",
                        },
                        "handle": "0PWJQCZYFXOS0HGREE",
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
                        "type": "Marriage",
                    }
                ],
                "father": {
                    "birth": {
                        "date": "1867-01-23",
                        "place": "Durango, La Plata, CO, USA",
                        "type": "Birth",
                    },
                    "death": {
                        "date": "1919-03-10",
                        "place": "Kokomo, Howard, IN, USA",
                        "type": "Death",
                    },
                    "handle": "SOTJQCKJPETYI38BRM",
                    "name_given": "Warren W.",
                    "name_surname": "Warner",
                    "sex": "M",
                },
                "handle": "LOTJQC78O5B4WQGJRP",
                "marriage": {
                    "date": "1888-08-09",
                    "place": "Springfield, Sangamon, IL, USA",
                    "type": "Marriage",
                },
                "mother": {
                    "birth": {
                        "date": "1869-07-08",
                        "place": "Oxnard, Ventura, CA, USA",
                        "type": "Birth",
                    },
                    "death": {
                        "date": "1942-04-21",
                        "place": "Kokomo, Howard, IN, USA",
                        "type": "Death",
                    },
                    "handle": "1QTJQCP5QMT2X7YJDK",
                    "name_given": "Abigail",
                    "name_surname": "Ball",
                    "sex": "F",
                },
                "relationship": "Married",
            },
            "sex": "F",
        }

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
        run_test_endpoint_extend(self.client, "/api/people/0PWJQCZYFXOS0HGREE", driver)

    def test_people_handle_endpoint_schema(self):
        """Test the people schema with extensions."""
        # check person record conforms to expected schema
        rv = self.client.get("/api/people/0PWJQCZYFXOS0HGREE?extend=all&profile")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"]["Person"],
            resolver=resolver,
        )
