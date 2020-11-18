#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Tests for the /api/families endpoints using example_gramps."""

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


class TestFamilies(unittest.TestCase):
    """Test cases for the /api/families endpoint for a list of families."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_families_endpoint(self):
        """Test reponse for families."""
        # check expected number of families found
        result = self.client.get("/api/families/")
        self.assertEqual(len(result.json), get_object_count("families"))
        # check first record is expected family
        self.assertEqual(result.json[0]["handle"], "03GKQCH37C1SL9C5B3")
        self.assertEqual(result.json[0]["father_handle"], "B2GKQCPG5WOVS9B4UL")
        self.assertEqual(result.json[0]["mother_handle"], "83GKQCS0LVSVRX99KO")
        # check last record is expected family
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["handle"], "d64cc45259c01f324b4")
        self.assertEqual(result.json[last]["father_handle"], "d64cc45258f454e7dac")
        self.assertEqual(result.json[last]["mother_handle"], "d64cc452655308a46f8")

    def test_families_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/families/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_families_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "F0045",
            "handle": "3HUJQCK4DH582YUTZG",
            "father_handle": "9HUJQC6ONNW8SMSKGQ",
            "mother_handle": "EIUJQCVLRWQ1G8CS4",
        }
        run_test_endpoint_gramps_id(self, "/api/families/", driver)

    def test_families_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/families/")

    def test_families_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self, "/api/families/", ["handle", "child_ref_list", "media_list"]
        )

    def test_families_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/families/", ["gramps_id", "lds_ord_list", "note_list"]
        )

    def test_families_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"IsBookmarked"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"IsBookmarked"}]}',
                '{"function":"none","rules":[{"name":"IsBookmarked"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"IsBookmarked"}]}',
                '{"rules":[{"name":"HasRelType","values":["Married"]},'
                + '{"name":"IsBookmarked"}]}',
                '{"function":"or","rules":[{"name":"HasRelType",'
                + '"values":["Unknown"]},{"name":"IsBookmarked"}]}',
                '{"function":"xor","rules":[{"name":"HasRelType",'
                + '"values":["Unknown"]},{"name":"IsBookmarked"}]}',
                '{"function":"one","rules":[{"name":"HasRelType",'
                + '"values":["Unknown"]},{"name":"IsBookmarked"}]}',
                '{"invert":true,"rules":[{"name":"HasRelType","values":["Married"]}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/families/", driver)

    def test_families_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed missing or bad argument
        result = self.client.get("/api/families/?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/families/?profile=3")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/families/?profile=alpha")
        self.assertEqual(result.status_code, 422)
        # check expected number of families found
        result = self.client.get("/api/families/?profile=all")
        self.assertEqual(len(result.json), get_object_count("families"))
        # check all expected profile attributes present for first family
        self.assertEqual(
            result.json[0]["profile"],
            {
                "children": [
                    {
                        "birth": {
                            "date": "",
                            "place": "Gadsden, Etowah, AL, USA",
                            "type": "Birth",
                        },
                        "death": {},
                        "handle": "S3GKQCSAUG5LKNW2AK",
                        "name_given": "Sarah",
                        "name_surname": "Reed",
                        "sex": "F",
                    }
                ],
                "divorce": {},
                "events": [
                    {
                        "date": "1879-07-25",
                        "place": "Greensboro, NC, USA",
                        "type": "Marriage",
                    }
                ],
                "father": {
                    "birth": {
                        "date": "1847-06-28",
                        "place": "El Campo, Wharton, TX, USA",
                        "type": "Birth",
                    },
                    "death": {
                        "date": "1892-03-05",
                        "place": "Plymouth, Marshall, IN, USA",
                        "type": "Death",
                    },
                    "handle": "B2GKQCPG5WOVS9B4UL",
                    "name_given": "Edward",
                    "name_surname": "Reed",
                    "sex": "M",
                },
                "handle": "03GKQCH37C1SL9C5B3",
                "marriage": {
                    "date": "1879-07-25",
                    "place": "Greensboro, NC, USA",
                    "type": "Marriage",
                },
                "mother": {
                    "birth": {
                        "date": "",
                        "place": "Jacksonville, NC, USA",
                        "type": "Birth",
                    },
                    "death": {},
                    "handle": "83GKQCS0LVSVRX99KO",
                    "name_given": "Ellen",
                    "name_surname": "Reed",
                    "sex": "F",
                },
                "relationship": "Married",
            },
        )

    def test_families_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "child_ref_list", "key": "children", "type": List},
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "event_ref_list", "key": "events", "type": List},
            {"arg": "father_handle", "key": "father", "type": Dict},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "mother_handle", "key": "mother", "type": Dict},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/families/", driver, ["F0045"])

    def test_families_endpoint_schema(self):
        """Test all families against the family schema."""
        # check expected number of families found
        result = self.client.get("/api/families/?extend=all&profile=all")
        self.assertEqual(len(result.json), get_object_count("families"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for family in result.json:
            validate(
                instance=family,
                schema=API_SCHEMA["definitions"]["Family"],
                resolver=resolver,
            )


class TestFamiliesHandle(unittest.TestCase):
    """Test cases for the /api/families/{handle} endpoint for a specific family."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_families_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent family
        result = self.client.get("/api/families/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_families_handle_endpoint(self):
        """Test response for a specific family."""
        # check expected family returned
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB")
        self.assertEqual(result.json["gramps_id"], "F0033")
        self.assertEqual(result.json["father_handle"], "KLTJQC70XVZJSPQ43U")
        self.assertEqual(result.json["mother_handle"], "JFWJQCRREDFKZLDKVD")

    def test_families_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_families_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/families/7MTJQCHRUUYSUA8ABB")

    def test_families_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/families/7MTJQCHRUUYSUA8ABB",
            ["gramps_id", "event_ref_list", "type"],
        )

    def test_families_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/families/7MTJQCHRUUYSUA8ABB",
            ["handle", "lds_ord_list", "child_ref_list"],
        )

    def test_families_handle_endpoint_profile(self):
        """Test response for profile parm."""
        # check 422 returned if passed missing or bad argument
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile=3")
        self.assertEqual(result.status_code, 422)
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile=alpha")
        self.assertEqual(result.status_code, 422)
        # check events works as expected
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile=self")
        self.assertNotIn("events", result.json["profile"])
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile=events")
        self.assertIn("events", result.json["profile"])
        # check all expected profile attributes present
        result = self.client.get("/api/families/7MTJQCHRUUYSUA8ABB?profile=all")
        self.assertEqual(
            result.json["profile"],
            {
                "children": [
                    {
                        "birth": {
                            "date": "1983-10-05",
                            "place": "Ottawa, La Salle, IL, USA",
                            "type": "Birth",
                        },
                        "death": {},
                        "handle": "1GWJQCGOOZ8FJW3YK9",
                        "name_given": "Stephen Gerard",
                        "name_surname": "Garner",
                        "sex": "M",
                    },
                    {
                        "birth": {
                            "date": "1985-02-11",
                            "place": "Ottawa, La Salle, IL, USA",
                            "type": "Birth",
                        },
                        "death": {},
                        "handle": "IGWJQCSVT8NXTFXOFJ",
                        "name_given": "Daniel Patrick",
                        "name_surname": "Garner",
                        "sex": "M",
                    },
                ],
                "divorce": {},
                "events": [
                    {
                        "date": "1979-01-06",
                        "place": "Farmington, MO, USA",
                        "type": "Marriage",
                    }
                ],
                "father": {
                    "birth": {
                        "date": "1955-07-31",
                        "place": "Ottawa, La Salle, IL, USA",
                        "type": "Birth",
                    },
                    "death": {},
                    "handle": "KLTJQC70XVZJSPQ43U",
                    "name_given": "Gerard Stephen",
                    "name_surname": "Garner",
                    "sex": "M",
                },
                "handle": "7MTJQCHRUUYSUA8ABB",
                "marriage": {
                    "date": "1979-01-06",
                    "place": "Farmington, MO, USA",
                    "type": "Marriage",
                },
                "mother": {
                    "birth": {"date": "1957-01-31", "place": "", "type": "Birth"},
                    "death": {},
                    "handle": "JFWJQCRREDFKZLDKVD",
                    "name_given": "Elizabeth",
                    "name_surname": "George",
                    "sex": "F",
                },
                "relationship": "Married",
            },
        )

    def test_families_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "child_ref_list", "key": "children", "type": List},
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "event_ref_list", "key": "events", "type": List},
            {"arg": "father_handle", "key": "father", "type": Dict},
            {"arg": "media_list", "key": "media", "type": List},
            {"arg": "mother_handle", "key": "mother", "type": Dict},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/families/7MTJQCHRUUYSUA8ABB", driver)

    def test_families_handle_endpoint_schema(self):
        """Test the family schema with extensions."""
        # check family record conforms to expected schema
        result = self.client.get(
            "/api/families/1J4KQCRKU4410338P7?extend=all&profile=all"
        )
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Family"],
            resolver=resolver,
        )
