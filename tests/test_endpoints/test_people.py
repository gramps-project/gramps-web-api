#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the /api/people endpoints using example_gramps."""

import unittest
from urllib.parse import quote

from . import BASE_URL, get_object_count, get_test_client
from .checks import (
    check_boolean_parameter,
    check_conforms_to_schema,
    check_invalid_semantics,
    check_invalid_syntax,
    check_keys_parameter,
    check_paging_parameters,
    check_requires_token,
    check_resource_missing,
    check_single_extend_parameter,
    check_skipkeys_parameter,
    check_sort_parameter,
    check_strip_parameter,
    check_success,
    check_totals,
)

TEST_URL = BASE_URL + "/people/"


class TestPeople(unittest.TestCase):
    """Test cases for the /api/people endpoint for a list of people."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def test_get_people_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_people_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "?extend=all&profile=all&backlinks=1", "Person"
        )

    def test_get_people_expected_results_total(self):
        """Test expected number of objects returned."""
        check_totals(self, TEST_URL + "?keys=handle", get_object_count("people"))

    def test_get_people_expected_results(self):
        """Test some expected results returned."""
        rv = check_success(self, TEST_URL)
        # check first expected record
        self.assertEqual(rv[0]["gramps_id"], "I2110")
        self.assertEqual(rv[0]["primary_name"]["first_name"], "محمد")
        self.assertEqual(rv[0]["primary_name"]["surname_list"][0]["surname"], "")
        # check last expected record
        self.assertEqual(rv[-1]["gramps_id"], "I0247")
        self.assertEqual(rv[-1]["primary_name"]["first_name"], "Allen")
        self.assertEqual(rv[-1]["primary_name"]["surname_list"][0]["surname"], "鈴木")

    def test_get_people_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk_parm=1")

    def test_get_people_parameter_gramps_id_validate_semantics(self):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?gramps_id", check="base")

    def test_get_people_parameter_gramps_id_missing_content(self):
        """Test response for missing gramps_id object."""
        check_resource_missing(self, TEST_URL + "?gramps_id=doesnot")

    def test_get_people_parameter_gramps_id_expected_result(self):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(self, TEST_URL + "?gramps_id=I0044")
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "GNUJQCL9MD64AM56OH")

    def test_get_people_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?strip", check="boolean")

    def test_get_people_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL)

    def test_get_people_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?keys", check="base")

    def test_get_people_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(self, TEST_URL, ["address_list", "handle", "urls"])

    def test_get_people_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL, [",".join(["address_list", "handle", "urls"])]
        )

    def test_get_people_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?skipkeys", check="base")

    def test_get_people_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(self, TEST_URL, ["address_list", "handle", "urls"])

    def test_get_people_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, [",".join(["address_list", "handle", "urls"])]
        )

    def test_get_people_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?page", check="number")

    def test_get_people_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?pagesize", check="number")

    def test_get_people_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(self, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_people_parameter_soundex_validate_semantics(self):
        """Test invalid soundex parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?soundex", check="boolean")

    def test_get_people_parameter_soundex_expected_result(self):
        """Test soundex parameter produces expected result."""
        rv = check_boolean_parameter(
            self, TEST_URL + "?keys=handle,soundex", "soundex", join="&"
        )
        self.assertEqual(rv[0]["soundex"], "Z000")
        self.assertEqual(rv[244]["soundex"], "B260")

    def test_get_people_parameter_sort_validate_semantics(self):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?sort", check="list")

    def test_get_people_parameter_sort_birth_ascending_expected_result(self):
        """Test sort parameter birth ascending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=+birth")
        self.assertEqual(rv[0]["handle"], "NRLKQCM1UUI9O8AMGQ")
        self.assertEqual(rv[-1]["handle"], "9BXKQC1PVLPYFMD6IX")

    def test_get_people_parameter_sort_birth_descending_expected_result(self):
        """Test sort parameter birth descending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=-birth")
        self.assertEqual(rv[0]["handle"], "9BXKQC1PVLPYFMD6IX")
        self.assertEqual(rv[-1]["handle"], "NRLKQCM1UUI9O8AMGQ")

    def test_get_people_parameter_sort_change_ascending_expected_result(self):
        """Test sort parameter change ascending result."""
        check_sort_parameter(self, TEST_URL, "change")

    def test_get_people_parameter_sort_change_descending_expected_result(self):
        """Test sort parameter change descending result."""
        check_sort_parameter(self, TEST_URL, "change", direction="-")

    def test_get_people_parameter_sort_death_ascending_expected_result(self):
        """Test sort parameter death ascending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=+death")
        self.assertEqual(rv[0]["handle"], "NRLKQCM1UUI9O8AMGQ")
        self.assertEqual(rv[-1]["handle"], "d583a5ba4be3acdd312")

    def test_get_people_parameter_sort_death_descending_expected_result(self):
        """Test sort parameter death descending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=-death")
        self.assertEqual(rv[0]["handle"], "d583a5ba4be3acdd312")
        self.assertEqual(rv[-1]["handle"], "NRLKQCM1UUI9O8AMGQ")

    def test_get_people_parameter_sort_gender_ascending_expected_result(self):
        """Test sort parameter gender ascending result."""
        check_sort_parameter(self, TEST_URL, "gender")

    def test_get_people_parameter_sort_gender_descending_expected_result(self):
        """Test sort parameter gender descending result."""
        check_sort_parameter(self, TEST_URL, "gender", direction="-")

    def test_get_people_parameter_sort_gramps_id_ascending_expected_result(self):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id")
        self.assertEqual(rv[0]["gramps_id"], "I0000")
        self.assertEqual(rv[-1]["gramps_id"], "I2156")

    def test_get_people_parameter_sort_gramps_id_descending_expected_result(self):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id", direction="-")
        self.assertEqual(rv[0]["gramps_id"], "I2156")
        self.assertEqual(rv[-1]["gramps_id"], "I0000")

    def test_get_people_parameter_sort_name_ascending_expected_result(self):
        """Test sort parameter name ascending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=+name")
        self.assertEqual(rv[0]["handle"], "cc82060504445ab6deb")
        self.assertEqual(rv[-1]["handle"], "B5QKQCZM5CDWEV4SP4")

    def test_get_people_parameter_sort_name_descending_expected_result(self):
        """Test sort parameter name descending result."""
        rv = check_success(self, TEST_URL + "?keys=handle&sort=-name")
        self.assertEqual(rv[0]["handle"], "B5QKQCZM5CDWEV4SP4")
        self.assertEqual(rv[-1]["handle"], "cc82060504445ab6deb")

    def test_get_people_parameter_sort_private_ascending_expected_result(self):
        """Test sort parameter private ascending result."""
        check_sort_parameter(self, TEST_URL, "private")

    def test_get_people_parameter_sort_private_descending_expected_result(self):
        """Test sort parameter private descending result."""
        check_sort_parameter(self, TEST_URL, "private", direction="-")

    def test_get_people_parameter_sort_soundex_ascending_expected_result(self):
        """Test sort parameter soundex ascending result."""
        check_sort_parameter(self, TEST_URL + "?soundex=1", "soundex", join="&")

    def test_get_people_parameter_sort_soundex_descending_expected_result(self):
        """Test sort parameter soundex descending result."""
        rv = check_sort_parameter(
            self, TEST_URL + "?soundex=1", "soundex", join="&", direction="-"
        )
        self.assertEqual(rv[0]["soundex"], "Z565")
        self.assertEqual(rv[-1]["soundex"], "A130")

    def test_get_people_parameter_sort_surname_ascending_expected_result(self):
        """Test sort parameter surname ascending result."""
        rv = check_success(self, TEST_URL + "?keys=primary_name&sort=+surname")
        self.assertEqual(rv[0]["primary_name"]["surname_list"][0]["surname"], "Abbott")
        self.assertEqual(rv[-1]["primary_name"]["surname_list"][0]["surname"], "鈴木")

    def test_get_people_parameter_sort_surname_descending_expected_result(self):
        """Test sort parameter surname descending result."""
        rv = check_success(self, TEST_URL + "?keys=primary_name&sort=-surname")
        self.assertEqual(rv[0]["primary_name"]["surname_list"][0]["surname"], "鈴木")
        self.assertEqual(rv[-1]["primary_name"]["surname_list"][0]["surname"], "Abbott")

    def test_get_people_parameter_sort_surname_ascending_expected_result_with_locale(
        self,
    ):
        """Test sort parameter surname ascending result using different locale."""
        rv = check_success(
            self, TEST_URL + "?keys=primary_name&sort=+surname&locale=zh_CN"
        )
        self.assertEqual(rv[0]["primary_name"]["surname_list"][0]["surname"], "渡辺")
        self.assertEqual(rv[-1]["primary_name"]["surname_list"][0]["surname"], "บุญ")

    def test_get_people_parameter_sort_surname_descending_expected_result_with_locale(
        self,
    ):
        """Test sort parameter surname descending result using different locale."""
        rv = check_success(
            self, TEST_URL + "?keys=primary_name&sort=-surname&locale=zh_CN"
        )
        self.assertEqual(rv[0]["primary_name"]["surname_list"][0]["surname"], "บุญ")
        self.assertEqual(rv[-1]["primary_name"]["surname_list"][0]["surname"], "渡辺")

    def test_get_people_parameter_filter_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?filter", check="base")

    def test_get_people_parameter_filter_missing_content(self):
        """Test response when missing the filter."""
        check_resource_missing(self, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_people_parameter_rules_validate_syntax(self):
        """Test invalid rules syntax."""
        check_invalid_syntax(self, TEST_URL + '?rules={"rules"[{"name":"IsMale"}]}')

    def test_get_people_parameter_rules_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            self, TEST_URL + '?rules={"some":"where","rules":[{"name":"IsMale"}]}'
        )
        check_invalid_semantics(
            self, TEST_URL + '?rules={"function":"none","rules":[{"name":"IsMale"}]}'
        )

    def test_get_people_parameter_rules_missing_content(self):
        """Test rules parameter missing request content."""
        check_resource_missing(
            self, TEST_URL + '?rules={"rules":[{"name":"Mirkwood"}]}'
        )

    def test_get_people_parameter_rules_expected_response_single_rule(self):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            self,
            TEST_URL + '?keys=gender&rules={"rules":[{"name":"HasUnknownGender"}]}',
        )
        for item in rv:
            self.assertEqual(item["gender"], 2)

    def test_get_people_parameter_rules_expected_response_multiple_rules(self):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=gender,family_list&rules={"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}',
        )
        for item in rv:
            self.assertEqual(item["gender"], 1)
            self.assertGreater(len(item["family_list"]), 1)

    def test_get_people_parameter_rules_expected_response_or_function(self):
        """Test rules parameter expected response for or function."""
        rv = check_success(self, BASE_URL + "/tags/")
        tag_handles = []
        for item in rv:
            if item["name"] in ["complete", "ToDo"]:
                tag_handles.append(item["handle"])
        rv = check_success(
            self,
            TEST_URL
            + '?keys=tag_list&rules={"function":"or","rules":[{"name":"HasTag","values":["complete"]},{"name":"HasTag","values":["ToDo"]}]}',
        )
        for item in rv:
            for tag in item["tag_list"]:
                self.assertIn(tag, tag_handles)

    def test_get_people_parameter_rules_expected_response_one_function(self):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=gender,family_list&rules={"function":"one","rules":[{"name":"IsFemale"},{"name":"MultipleMarriages"}]}',
        )
        for item in rv:
            if item["gender"] == 0:
                self.assertLess(len(item["family_list"]), 2)
            if len(item["family_list"]) > 1:
                self.assertNotEqual(item["gender"], 0)

    def test_get_people_parameter_rules_expected_response_invert(self):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=gender,family_list&rules={"invert":true,"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}',
        )
        for item in rv:
            if item["gender"] == 1:
                self.assertLess(len(item["family_list"]), 2)

    def test_get_people_parameter_gql_validate_semantics(self):
        """Test invalid rules syntax."""
        check_invalid_semantics(self, TEST_URL + "?gql=()")

    def test_get_people_parameter_gql_handle(self):
        """Test invalid rules syntax."""
        rv = check_success(
            self,
            TEST_URL + "?gql=" + quote("gramps_id=I0044"),
        )
        assert len(rv) == 1
        assert rv[0]["gramps_id"] == "I0044"

    def test_get_people_parameter_gql_like(self):
        """Test invalid rules syntax."""
        rv = check_success(
            self,
            TEST_URL + "?gql=" + quote("gramps_id ~ I004"),
        )
        assert len(rv) == 10

    def test_get_people_parameter_gql_or(self):
        """Test invalid rules syntax."""
        rv = check_success(
            self,
            TEST_URL + "?gql=" + quote("(gramps_id ~ I004 or gramps_id ~ I003)"),
        )
        assert len(rv) == 20

    def test_get_people_parameter_oql_validate_semantics(self):
        """Test invalid rules syntax."""
        check_invalid_semantics(self, TEST_URL + "?oql=(")

    def test_get_people_parameter_oql_handle(self):
        """Test equal field."""
        rv = check_success(
            self,
            TEST_URL + "?oql=" + quote("person.gramps_id == 'I0044'"),
        )
        assert len(rv) == 1
        assert rv[0]["gramps_id"] == "I0044"

    def test_get_people_parameter_oql_like(self):
        """Test string in field."""
        rv = check_success(
            self,
            TEST_URL + "?oql=" + quote("'I004' in person.gramps_id"),
        )
        assert len(rv) == 10

    def test_get_people_parameter_oql_or(self):
        """Test two expr combined with or."""
        rv = check_success(
            self,
            TEST_URL
            + "?oql="
            + quote(
                "(person.gramps_id.startswith('I004') or person.gramps_id.startswith('I003'))"
            ),
        )
        assert len(rv) == 20

    def test_get_people_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?extend", check="list")

    def test_get_people_parameter_extend_expected_result_citation_list(self):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=I0044", "citation_list", "citations", join="&"
        )

    def test_get_people_parameter_extend_expected_result_event_ref_list(self):
        """Test extend event_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=I0044",
            "event_ref_list",
            "events",
            join="&",
            reference=True,
        )

    def test_get_people_parameter_extend_expected_result_family_list(self):
        """Test extend family_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=I0044", "family_list", "families", join="&"
        )

    def test_get_people_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=I0044",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_people_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=I0044", "note_list", "notes", join="&"
        )

    def test_get_people_parameter_extend_expected_result_parent_family_list(self):
        """Test extend parent_family_list result."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=I0044&extend=parent_family_list&keys=parent_family_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 1)
        if len(rv[0]["parent_family_list"]) > 1:
            self.assertEqual(
                len(rv[0]["parent_family_list"]) - 1,
                len(rv[0]["extended"]["parent_families"]),
            )
        for item in rv[0]["extended"]["parent_families"]:
            self.assertIn(item["handle"], rv[0]["parent_family_list"])

    def test_get_people_parameter_extend_expected_result_person_ref_list(self):
        """Test extend person_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=I0044",
            "person_ref_list",
            "people",
            join="&",
            reference=True,
        )

    def test_get_people_parameter_extend_expected_result_primary_parent_family(self):
        """Test extend primary_parent_family result."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=I0044&extend=primary_parent_family&keys=parent_family_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 1)
        self.assertIn(
            rv[0]["extended"]["primary_parent_family"]["handle"],
            rv[0]["parent_family_list"],
        )

    def test_get_people_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=I0044", "tag_list", "tags", join="&"
        )

    def test_get_people_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "?gramps_id=I0044&extend=all&keys=extended")
        self.assertEqual(len(rv[0]["extended"]), 9)
        for key in [
            "citations",
            "events",
            "families",
            "media",
            "notes",
            "parent_families",
            "people",
            "primary_parent_family",
            "tags",
        ]:
            self.assertIn(key, rv[0]["extended"])

    def test_get_people_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=I0044&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 2)
        self.assertIn("notes", rv[0]["extended"])
        self.assertIn("tags", rv[0]["extended"])

    def test_get_people_parameter_profile_validate_semantics(self):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?profile", check="list")

    def test_get_people_parameter_profile_expected_result(self):
        """Test expected response."""
        rv = check_success(
            self, TEST_URL + "OS6KQCDBW36VIRF98Z?keys=profile&strip=1&profile=all"
        )
        self.assertEqual(
            rv["profile"],
            {
                "birth": {
                    "age": "0 days",
                    "citations": 0,
                    "confidence": 0,
                    "date": "after 1717",
                    "place": "Hickory-Morganton-Lenoir, NC, USA",
                    "place_name": "Hickory-Morganton-Lenoir",
                    "summary": "Birth - Aguilar, Eleanor",
                    "type": "Birth",
                },
                "death": {
                    "age": "unknown",
                    "citations": 0,
                    "confidence": 0,
                    "date": "after 1760-02",
                    "place": "Plattsburgh, Clinton, NY, USA",
                    "place_name": "Plattsburgh",
                    "summary": "Death - Aguilar, Eleanor",
                    "type": "Death",
                },
                "events": [
                    {
                        "age": "unknown",
                        "citations": 0,
                        "confidence": 0,
                        "date": "after 1717",
                        "place": "Hickory-Morganton-Lenoir, NC, USA",
                        "place_name": "Hickory-Morganton-Lenoir",
                        "role": "Primary",
                        "summary": "Birth - Aguilar, Eleanor",
                        "type": "Birth",
                    },
                    {
                        "age": "unknown",
                        "citations": 0,
                        "confidence": 0,
                        "date": "after 1760-02",
                        "place": "Plattsburgh, Clinton, NY, USA",
                        "place_name": "Plattsburgh",
                        "role": "Primary",
                        "summary": "Death - Aguilar, Eleanor",
                        "type": "Death",
                    },
                ],
                "families": [
                    {
                        "children": [
                            {
                                "birth": {
                                    "age": "0 days",
                                    "citations": 0,
                                    "confidence": 0,
                                    "date": "between 1746 and 1755",
                                    "place": "Plattsburgh, Clinton, NY, USA",
                                    "place_name": "Plattsburgh",
                                    "summary": "Birth - Adams, Jane",
                                    "type": "Birth",
                                },
                                "death": {
                                    "age": "between 6 years, 1 days and 109 years, 11 months, 30 days",
                                    "citations": 0,
                                    "confidence": 0,
                                    "date": "estimated from 1800 to 1805",
                                    "place": "Jefferson City, MO, USA",
                                    "place_name": "Jefferson City",
                                    "summary": "Death - Adams, Jane",
                                    "type": "Death",
                                },
                                "gramps_id": "I0554",
                                "handle": "914KQCNJ9TMDQMDL81",
                                "name_display": "Adams, Jane",
                                "name_given": "Jane",
                                "name_surname": "Adams",
                                "sex": "F",
                            }
                        ],
                        "events": [
                            {
                                "citations": 0,
                                "confidence": 0,
                                "place": "Loveland, Larimer, CO, USA",
                                "place_name": "Loveland",
                                "span": "unknown",
                                "summary": "Marriage - Adams, William and Aguilar, Eleanor",
                                "type": "Marriage",
                            }
                        ],
                        "family_surname": "Adams",
                        "father": {
                            "birth": {
                                "age": "0 days",
                                "citations": 0,
                                "confidence": 0,
                                "date": "about 1700-10-26",
                                "place": "Dyersburg, TN, USA",
                                "place_name": "Dyersburg",
                                "summary": "Birth - Adams, William",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "about 86 years, 4 months, 15 days",
                                "citations": 0,
                                "confidence": 0,
                                "date": "1787-03-10",
                                "place": "Hattiesburg, MS, USA",
                                "place_name": "Hattiesburg",
                                "summary": "Death - Adams, William",
                                "type": "Death",
                            },
                            "gramps_id": "I0701",
                            "handle": "FR6KQCRONQWR69LFUI",
                            "name_display": "Adams, William",
                            "name_given": "William",
                            "name_surname": "Adams",
                            "sex": "M",
                        },
                        "gramps_id": "F0204",
                        "handle": "R14KQCXMSQYXI2CS6W",
                        "marriage": {
                            "citations": 0,
                            "confidence": 0,
                            "place": "Loveland, Larimer, CO, USA",
                            "place_name": "Loveland",
                            "span": "0 days",
                            "summary": "Marriage - Adams, William and Aguilar, Eleanor",
                            "type": "Marriage",
                        },
                        "mother": {
                            "birth": {
                                "age": "0 days",
                                "citations": 0,
                                "confidence": 0,
                                "date": "after 1717",
                                "place": "Hickory-Morganton-Lenoir, NC, USA",
                                "place_name": "Hickory-Morganton-Lenoir",
                                "summary": "Birth - Aguilar, Eleanor",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "unknown",
                                "citations": 0,
                                "confidence": 0,
                                "date": "after 1760-02",
                                "place": "Plattsburgh, Clinton, NY, USA",
                                "place_name": "Plattsburgh",
                                "summary": "Death - Aguilar, Eleanor",
                                "type": "Death",
                            },
                            "gramps_id": "I0702",
                            "handle": "OS6KQCDBW36VIRF98Z",
                            "name_display": "Aguilar, Eleanor",
                            "name_given": "Eleanor",
                            "name_surname": "Aguilar",
                            "sex": "F",
                        },
                        "relationship": "Married",
                    }
                ],
                "gramps_id": "I0702",
                "handle": "OS6KQCDBW36VIRF98Z",
                "name_display": "Aguilar, Eleanor",
                "name_given": "Eleanor",
                "name_surname": "Aguilar",
                "primary_parent_family": {
                    "children": [
                        {
                            "birth": {
                                "age": "0 days",
                                "citations": 0,
                                "confidence": 0,
                                "date": "after 1717",
                                "place": "Hickory-Morganton-Lenoir, NC, USA",
                                "place_name": "Hickory-Morganton-Lenoir",
                                "summary": "Birth - Aguilar, Eleanor",
                                "type": "Birth",
                            },
                            "death": {
                                "age": "unknown",
                                "citations": 0,
                                "confidence": 0,
                                "date": "after 1760-02",
                                "place": "Plattsburgh, Clinton, NY, USA",
                                "place_name": "Plattsburgh",
                                "summary": "Death - Aguilar, Eleanor",
                                "type": "Death",
                            },
                            "gramps_id": "I0702",
                            "handle": "OS6KQCDBW36VIRF98Z",
                            "name_display": "Aguilar, Eleanor",
                            "name_given": "Eleanor",
                            "name_surname": "Aguilar",
                            "sex": "F",
                        }
                    ],
                    "family_surname": "Aguilar",
                    "father": {
                        "birth": {
                            "age": "0 days",
                            "citations": 0,
                            "confidence": 0,
                            "date": "before 1665",
                            "place": "Ketchikan, AK, USA",
                            "place_name": "Ketchikan",
                            "summary": "Birth - Aguilar, John",
                            "type": "Birth",
                        },
                        "death": {
                            "age": "unknown",
                            "citations": 0,
                            "confidence": 0,
                            "date": "before 1745-02",
                            "place": "Wooster, OH, USA",
                            "place_name": "Wooster",
                            "summary": "Death - Aguilar, John",
                            "type": "Death",
                        },
                        "gramps_id": "I0953",
                        "handle": "4GCKQC20GMQLO6N77C",
                        "name_display": "Aguilar, John",
                        "name_given": "John",
                        "name_surname": "Aguilar",
                        "sex": "M",
                    },
                    "gramps_id": "F0704",
                    "handle": "DT6KQCOCKIUH1J4OSV",
                    "relationship": "Married",
                },
                "references": {
                    "family": [
                        {
                            "children": [
                                {
                                    "birth": {
                                        "date": "after 1717",
                                        "place": "Hickory-Morganton-Lenoir, NC, USA",
                                        "place_name": "Hickory-Morganton-Lenoir",
                                        "summary": "Birth - Aguilar, Eleanor",
                                        "type": "Birth",
                                    },
                                    "death": {
                                        "date": "after 1760-02",
                                        "place": "Plattsburgh, Clinton, NY, USA",
                                        "place_name": "Plattsburgh",
                                        "summary": "Death - Aguilar, Eleanor",
                                        "type": "Death",
                                    },
                                    "gramps_id": "I0702",
                                    "handle": "OS6KQCDBW36VIRF98Z",
                                    "name_display": "Aguilar, Eleanor",
                                    "name_given": "Eleanor",
                                    "name_surname": "Aguilar",
                                    "sex": "F",
                                }
                            ],
                            "family_surname": "Aguilar",
                            "father": {
                                "birth": {
                                    "date": "before 1665",
                                    "place": "Ketchikan, AK, USA",
                                    "place_name": "Ketchikan",
                                    "summary": "Birth - Aguilar, John",
                                    "type": "Birth",
                                },
                                "death": {
                                    "date": "before 1745-02",
                                    "place": "Wooster, OH, USA",
                                    "place_name": "Wooster",
                                    "summary": "Death - Aguilar, John",
                                    "type": "Death",
                                },
                                "gramps_id": "I0953",
                                "handle": "4GCKQC20GMQLO6N77C",
                                "name_display": "Aguilar, John",
                                "name_given": "John",
                                "name_surname": "Aguilar",
                                "sex": "M",
                            },
                            "gramps_id": "F0704",
                            "handle": "DT6KQCOCKIUH1J4OSV",
                            "relationship": "Married",
                        },
                        {
                            "children": [
                                {
                                    "birth": {
                                        "date": "between 1746 and 1755",
                                        "place": "Plattsburgh, Clinton, NY, USA",
                                        "place_name": "Plattsburgh",
                                        "summary": "Birth - Adams, Jane",
                                        "type": "Birth",
                                    },
                                    "death": {
                                        "date": "estimated from 1800 to 1805",
                                        "place": "Jefferson City, MO, USA",
                                        "place_name": "Jefferson City",
                                        "summary": "Death - Adams, Jane",
                                        "type": "Death",
                                    },
                                    "gramps_id": "I0554",
                                    "handle": "914KQCNJ9TMDQMDL81",
                                    "name_display": "Adams, Jane",
                                    "name_given": "Jane",
                                    "name_surname": "Adams",
                                    "sex": "F",
                                }
                            ],
                            "family_surname": "Adams",
                            "father": {
                                "birth": {
                                    "date": "about 1700-10-26",
                                    "place": "Dyersburg, TN, USA",
                                    "place_name": "Dyersburg",
                                    "summary": "Birth - Adams, William",
                                    "type": "Birth",
                                },
                                "death": {
                                    "date": "1787-03-10",
                                    "place": "Hattiesburg, MS, USA",
                                    "place_name": "Hattiesburg",
                                    "summary": "Death - Adams, William",
                                    "type": "Death",
                                },
                                "gramps_id": "I0701",
                                "handle": "FR6KQCRONQWR69LFUI",
                                "name_display": "Adams, William",
                                "name_given": "William",
                                "name_surname": "Adams",
                                "sex": "M",
                            },
                            "gramps_id": "F0204",
                            "handle": "R14KQCXMSQYXI2CS6W",
                            "marriage": {
                                "place": "Loveland, Larimer, CO, USA",
                                "place_name": "Loveland",
                                "summary": "Marriage - Adams, William and Aguilar, Eleanor",
                                "type": "Marriage",
                            },
                            "mother": {
                                "birth": {
                                    "date": "after 1717",
                                    "place": "Hickory-Morganton-Lenoir, NC, USA",
                                    "place_name": "Hickory-Morganton-Lenoir",
                                    "summary": "Birth - Aguilar, Eleanor",
                                    "type": "Birth",
                                },
                                "death": {
                                    "date": "after 1760-02",
                                    "place": "Plattsburgh, Clinton, NY, USA",
                                    "place_name": "Plattsburgh",
                                    "summary": "Death - Aguilar, Eleanor",
                                    "type": "Death",
                                },
                                "gramps_id": "I0702",
                                "handle": "OS6KQCDBW36VIRF98Z",
                                "name_display": "Aguilar, Eleanor",
                                "name_given": "Eleanor",
                                "name_surname": "Aguilar",
                                "sex": "F",
                            },
                            "relationship": "Married",
                        },
                    ]
                },
                "sex": "F",
            },
        )

    def test_get_people_parameter_profile_expected_result_with_locale(self):
        """Test expected profile response for a locale."""
        rv = check_success(self, TEST_URL + "?page=1&profile=all&locale=de")
        self.assertEqual(rv[0]["profile"]["birth"]["age"], "0 Tage")
        self.assertEqual(rv[0]["profile"]["birth"]["type"], "Geburt")
        self.assertEqual(rv[0]["profile"]["families"][0]["relationship"], "Verheiratet")
        self.assertEqual(rv[0]["profile"]["events"][2]["type"], "Heirat")

    def test_get_people_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?backlinks", check="boolean")

    def test_get_people_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(self, TEST_URL + "?page=1", "backlinks", join="&")
        self.assertIn("cc8205d874433c12fd8", rv[0]["backlinks"]["family"])
        self.assertIn("cc8205d87492b90b437", rv[0]["backlinks"]["family"])


class TestPeopleHandle(unittest.TestCase):
    """Test cases for the /api/people/{handle} endpoint for a specific person."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_people_handle_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "GNUJQCL9MD64AM56OH")

    def test_get_people_handle_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "0PWJQCZYFXOS0HGREE?extend=all&profile=all&backlinks=1",
            "Person",
        )

    def test_get_people_handle_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist")

    def test_get_people_handle_expected_result(self):
        """Test response for specific person."""
        rv = check_success(self, TEST_URL + "GNUJQCL9MD64AM56OH")
        self.assertEqual(rv["gramps_id"], "I0044")
        self.assertEqual(rv["primary_name"]["first_name"], "Lewis Anderson")
        self.assertEqual(rv["primary_name"]["surname_list"][1]["surname"], "Zieliński")

    def test_get_people_handle_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "GNUJQCL9MD64AM56OH?junk_parm=1")

    def test_get_people_handle_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK?strip", check="boolean"
        )

    def test_get_people_handle_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "1QTJQCP5QMT2X7YJDK")

    def test_get_people_handle_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK?keys", check="base"
        )

    def test_get_people_handle_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK", ["address_list", "handle", "urls"]
        )

    def test_get_people_handle_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK",
            [",".join(["address_list", "handle", "urls"])],
        )

    def test_get_people_handle_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK?skipkeys", check="base"
        )

    def test_get_people_handle_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK", ["address_list", "handle", "urls"]
        )

    def test_get_people_handle_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK",
            [",".join(["address_list", "handle", "urls"])],
        )

    def test_get_people_handle_parameter_soundex_validate_semantics(self):
        """Test invalid soundex parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK?soundex", check="boolean"
        )

    def test_get_people_handle_parameter_soundex_expected_result(self):
        """Test soundex parameter produces expected result."""
        rv = check_boolean_parameter(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK?keys=handle,soundex",
            "soundex",
            join="&",
        )
        self.assertEqual(rv["soundex"], "B400")

    def test_get_people_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?extend", check="list"
        )

    def test_get_people_parameter_extend_expected_result_citation_list(self):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE", "citation_list", "citations"
        )

    def test_get_people_parameter_extend_expected_result_event_ref_list(self):
        """Test extend event_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "0PWJQCZYFXOS0HGREE",
            "event_ref_list",
            "events",
            reference=True,
        )

    def test_get_people_parameter_extend_expected_result_family_list(self):
        """Test extend family_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE", "family_list", "families"
        )

    def test_get_people_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE", "media_list", "media", reference=True
        )

    def test_get_people_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE", "note_list", "notes"
        )

    def test_get_people_parameter_extend_expected_result_parent_family_list(self):
        """Test extend parent_family_list result."""
        rv = check_success(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?extend=parent_family_list"
        )
        self.assertEqual(len(rv["extended"]), 1)
        if len(rv["parent_family_list"]) > 1:
            self.assertEqual(
                len(rv["parent_family_list"]) - 1,
                len(rv["extended"]["parent_families"]),
            )
        for item in rv["extended"]["parent_families"]:
            self.assertIn(item["handle"], rv["parent_family_list"])

    def test_get_people_parameter_extend_expected_result_person_ref_list(self):
        """Test extend person_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "0PWJQCZYFXOS0HGREE",
            "person_ref_list",
            "people",
            reference=True,
        )

    def test_get_people_parameter_extend_expected_result_primary_parent_family(self):
        """Test extend primary_parent_family result."""
        rv = check_success(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?extend=primary_parent_family"
        )
        self.assertEqual(len(rv["extended"]), 1)
        self.assertIn(
            rv["extended"]["primary_parent_family"]["handle"], rv["parent_family_list"]
        )

    def test_get_people_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE", "tag_list", "tags"
        )

    def test_get_people_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?extend=all")
        self.assertEqual(len(rv["extended"]), 9)
        for key in [
            "citations",
            "events",
            "families",
            "media",
            "notes",
            "parent_families",
            "people",
            "primary_parent_family",
            "tags",
        ]:
            self.assertIn(key, rv["extended"])

    def test_get_people_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?extend=note_list,tag_list"
        )
        self.assertEqual(len(rv["extended"]), 2)
        self.assertIn("notes", rv["extended"])
        self.assertIn("tags", rv["extended"])

    def test_get_people_handle_parameter_profile_validate_semantics(self):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile", check="list"
        )

    def test_get_people_handle_parameter_profile_expected_result_self(self):
        """Test profile parameter self option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=self")
        self.assertNotIn("events", rv["profile"])
        self.assertNotIn("families", rv["profile"])
        self.assertNotIn("age", rv["profile"]["birth"])
        self.assertEqual(
            rv["profile"],
            {
                "birth": {
                    "date": "1906-09-05",
                    "place": "Central City, Muhlenberg, KY, USA",
                    "place_name": "Central City",
                    "type": "Birth",
                    "summary": "Birth - Warner, Mary Grace Elizabeth",
                },
                "death": {
                    "date": "1993-06-06",
                    "place": "Sevierville, TN, USA",
                    "place_name": "Sevierville",
                    "type": "Death",
                    "summary": "Death - Warner, Mary Grace Elizabeth",
                },
                "gramps_id": "I0138",
                "handle": "0PWJQCZYFXOS0HGREE",
                "name_display": "Warner, Mary Grace Elizabeth",
                "name_given": "Mary Grace Elizabeth",
                "name_suffix": "",
                "name_surname": "Warner",
                "sex": "F",
            },
        )

    def test_get_people_handle_parameter_profile_expected_result_age(self):
        """Test profile parameter age option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=age")
        self.assertNotIn("events", rv["profile"])
        self.assertNotIn("families", rv["profile"])
        self.assertIn("age", rv["profile"]["birth"])
        self.assertEqual(rv["profile"]["birth"]["age"], "0 days")

    def test_get_people_handle_parameter_profile_expected_result_families(self):
        """Test profile parameter families option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=families")
        self.assertNotIn("events", rv["profile"])
        self.assertIn("families", rv["profile"])
        self.assertNotIn("age", rv["profile"]["birth"])
        self.assertEqual(
            rv["profile"]["primary_parent_family"]["handle"], "LOTJQC78O5B4WQGJRP"
        )
        self.assertNotIn("span", rv["profile"]["primary_parent_family"]["marriage"])

    def test_get_people_handle_parameter_profile_expected_result_span(self):
        """Test profile parameter families with span option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=families,span")
        self.assertNotIn("events", rv["profile"])
        self.assertIn("families", rv["profile"])
        self.assertNotIn("age", rv["profile"]["birth"])
        self.assertEqual(
            rv["profile"]["primary_parent_family"]["handle"], "LOTJQC78O5B4WQGJRP"
        )
        self.assertIn("span", rv["profile"]["primary_parent_family"]["marriage"])
        self.assertEqual(
            rv["profile"]["primary_parent_family"]["marriage"]["span"], "0 days"
        )

    def test_get_people_handle_parameter_profile_expected_result_events(self):
        """Test profile parameter events option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=events")
        self.assertIn("events", rv["profile"])
        self.assertNotIn("families", rv["profile"])
        self.assertNotIn("age", rv["profile"]["birth"])
        self.assertEqual(
            rv["profile"]["events"][0]["place"], "Central City, Muhlenberg, KY, USA"
        )

    def test_get_people_handle_parameter_profile_expected_result_all(self):
        """Test profile parameter all option."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=all")
        for key in [
            "birth",
            "death",
            "events",
            "families",
            "handle",
            "name_display",
            "name_given",
            "name_surname",
            "other_parent_families",
            "primary_parent_family",
            "sex",
        ]:
            self.assertIn(key, rv["profile"])

    def test_get_people_handle_parameter_profile_expected_result_with_locale(self):
        """Test expected profile response for a locale."""
        rv = check_success(self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile=all&locale=de")
        self.assertEqual(rv["profile"]["birth"]["age"], "0 Tage")
        self.assertEqual(rv["profile"]["birth"]["type"], "Geburt")
        self.assertEqual(
            rv["profile"]["primary_parent_family"]["relationship"], "Verheiratet"
        )
        self.assertEqual(rv["profile"]["events"][2]["type"], "Beerdigung")

    def test_get_people_handle_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "0PWJQCZYFXOS0HGREE?profile", check="list"
        )

    def test_get_people_handle_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(self, TEST_URL + "SOTJQCKJPETYI38BRM", "backlinks")
        self.assertEqual(
            rv["backlinks"], {"family": ["LOTJQC78O5B4WQGJRP", "UPTJQC4VPCABZUDB75"]}
        )

    def test_get_people_handle_parameter_backlinks_expected_results_extended(self):
        """Test the people handle endpoint with extended backlinks."""
        rv = check_success(
            self, TEST_URL + "SOTJQCKJPETYI38BRM?backlinks=1&extend=backlinks"
        )
        self.assertIn("backlinks", rv)
        self.assertIn("extended", rv)
        self.assertIn("backlinks", rv["extended"])
        backlinks = rv["extended"]["backlinks"]
        self.assertEqual(backlinks["family"][0]["handle"], "LOTJQC78O5B4WQGJRP")
        self.assertEqual(backlinks["family"][1]["handle"], "UPTJQC4VPCABZUDB75")

    def test_get_people_handle_parameter_name_format_expected_result_name_display(self):
        """Test the people handle endpoint with profile and name_format parameters"""
        rv = check_success(
            self,
            TEST_URL
            + "0PWJQCZYFXOS0HGREE?profile=all&name_format=%25f%20%28%25x%29%20%25M",
        )
        self.assertEqual(
            rv["profile"]["name_display"], "Mary Grace Elizabeth (Mary) WARNER"
        )


class TestPeopleHandleTimeline(unittest.TestCase):
    """Test cases for the /api/people/{handle}/timeline endpoint for a specific person."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_people_handle_timeline_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline")

    def test_get_people_handle_timeline_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "GNUJQCL9MD64AM56OH/timeline?ratings=1",
            "TimelineEventProfile",
        )

    def test_get_people_handle_timeline_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist/timeline")

    def test_get_people_handle_timeline_expected_result(self):
        """Test response for specific person."""
        rv = check_success(self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline")
        self.assertEqual(rv[0]["gramps_id"], "E1656")
        self.assertEqual(rv[0]["label"], "Birth")
        self.assertEqual(rv[1]["gramps_id"], "E0200")
        self.assertEqual(rv[1]["label"], "Birth (Stepsister)")
        self.assertEqual(rv[5]["gramps_id"], "E0211")
        self.assertEqual(rv[5]["label"], "Birth (Stepbrother)")
        self.assertEqual(rv[11]["gramps_id"], "E2815")
        self.assertEqual(rv[11]["label"], "Marriage")
        self.assertEqual(rv[13]["gramps_id"], "E2037")
        self.assertEqual(rv[13]["label"], "Birth (Son)")
        self.assertEqual(rv[22]["gramps_id"], "E2051")
        self.assertEqual(rv[22]["label"], "Birth (Daughter)")
        self.assertEqual(rv[29]["gramps_id"], "E1657")
        self.assertEqual(rv[29]["label"], "Death")
        self.assertEqual(rv[30]["gramps_id"], "E1658")
        self.assertEqual(rv[30]["label"], "Burial")

    def test_get_people_handle_timeline_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?junk_parm=1"
        )

    def test_get_people_handle_timeline_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?strip", check="boolean"
        )

    def test_get_people_handle_timeline_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline")

    def test_get_people_handle_timeline_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?keys", check="base"
        )

    def test_get_people_handle_timeline_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline", ["date", "handle", "type"]
        )

    def test_get_people_handle_timeline_parameter_keys_expected_result_multiple_keys(
        self,
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline",
            [",".join(["date", "handle", "type"])],
        )

    def test_get_people_handle_timeline_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?skipkeys", check="base"
        )

    def test_get_people_handle_timeline_parameter_skipkeys_expected_result_single_key(
        self,
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline", ["date", "handle", "type"]
        )

    def test_get_people_handle_timeline_parameter_skipkeys_expected_result_multiple_keys(
        self,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline",
            [",".join(["date", "handle", "type"])],
        )

    def test_get_people_handle_timeline_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?page", check="number"
        )

    def test_get_people_handle_timeline_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?pagesize", check="number"
        )

    def test_get_people_handle_timeline_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?keys=handle", 2, join="&"
        )

    def test_get_people_handle_timeline_parameter_ancestors_validate_semantics(self):
        """Test invalid ancestors parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?ancestors", check="number"
        )

    def test_get_people_handle_timeline_parameter_ancestors_expected_result(self):
        """Test ancestors parameter for expected results."""
        rv = check_success(self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?ancestors=3")
        self.assertEqual(rv[6]["label"], "Death (Stepgrandfather)")
        self.assertEqual(rv[16]["label"], "Death (Stepgrandmother)")

    def test_get_people_handle_timeline_parameter_offspring_validate_semantics(self):
        """Test invalid offspring parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?offspring", check="number"
        )

    def test_get_people_handle_timeline_parameter_offspring_expected_result(self):
        """Test offspring parameter for expected results."""
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?offspring=3")
        self.assertEqual(rv[13]["label"], "Birth (Grandson)")
        self.assertEqual(rv[23]["label"], "Birth (Great Grandson)")
        self.assertEqual(rv[24]["label"], "Birth (Great Granddaughter)")

    def test_get_people_handle_timeline_parameter_precision_validate_semantics(self):
        """Test invalid precision parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?precision", check="number"
        )

    def test_get_people_handle_timeline_parameter_precision_expected_result(self):
        """Test precision parameter for expected results."""
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?precision=3")
        self.assertEqual(rv[8]["label"], "Death (Mother)")
        self.assertEqual(rv[8]["age"], "22 years, 3 months, 23 days")

    def test_get_people_handle_timeline_parameter_first_validate_semantics(self):
        """Test invalid first parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?first", check="boolean"
        )

    def test_get_people_handle_timeline_parameter_first_expected_result(self):
        """Test first parameter for expected results."""
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?first=1")
        self.assertEqual(rv[0]["date"], "1869-07-08")
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?first=0")
        self.assertEqual(rv[0]["date"], "1846-08-17")

    def test_get_people_handle_timeline_parameter_last_validate_semantics(self):
        """Test invalid last parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?last", check="boolean"
        )

    def test_get_people_handle_timeline_parameter_last_expected_result(self):
        """Test last parameter for expected results."""
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?last=1")
        self.assertEqual(rv[16]["date"], "1942-04-23")
        rv = check_success(self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?last=0")
        self.assertEqual(rv[19]["date"], "1993-06-06")

    def test_get_people_handle_timeline_parameter_events_validate_semantics(self):
        """Test invalid events parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?events", check="list"
        )

    def test_get_people_handle_timeline_parameter_events_expected_result(self):
        """Test events parameter for expected results."""
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?events=Birth,Marriage"
        )
        self.assertEqual(len(rv), 30)
        rv = check_success(self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?events=Burial")
        self.assertEqual(rv[30]["type"], "Burial")

    def test_get_people_handle_timeline_parameter_event_class_validate_semantics(self):
        """Test invalid event_class parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?event_class", check="list"
        )

    def test_get_people_handle_timeline_parameter_event_class_expected_result(self):
        """Test event_class parameter for expected results."""
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?event_classes=other"
        )
        self.assertEqual(len(rv), 30)
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?event_classes=vital"
        )
        self.assertEqual(rv[30]["type"], "Burial")

    def test_get_people_handle_timeline_parameter_relatives_validate_semantics(self):
        """Test invalid relatives parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?relatives", check="list"
        )

    def test_get_people_handle_timeline_parameter_relatives_expected_result(self):
        """Test relatives parameter for expected results."""
        for relation in ["sister", "brother", "son", "daughter", "mother"]:
            rv = check_success(
                self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?relatives=" + relation
            )
            for event in rv:
                if "(" in event["label"]:
                    self.assertIn(relation, event["label"].lower())

    def test_get_people_handle_timeline_parameter_relative_events_validate_semantics(
        self,
    ):
        """Test invalid relative_events parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?relative_events", check="list"
        )

    def test_get_people_handle_timeline_parameter_relative_events_expected_result(self):
        """Test relative_events parameter for expected results."""
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?relative_events=Birth"
        )
        for event in rv:
            if "(" in event["label"]:
                self.assertIn(event["type"], ["Birth", "Death"])
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?relative_events=Marriage"
        )
        for event in rv:
            if "(" in event["label"]:
                self.assertIn(event["type"], ["Birth", "Marriage", "Death"])

    def test_get_people_handle_timeline_parameter_relative_event_class_validate_semantics(
        self,
    ):
        """Test invalid relative_event_class parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?relative_event_class",
            check="list",
        )

    def test_get_people_handle_timeline_parameter_relative_event_class_expected_result(
        self,
    ):
        """Test relative_event_class parameter for expected results."""
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?relative_event_classes=other"
        )
        for event in rv:
            self.assertNotEqual(event["label"], "Marriage (Stepsister)")
        rv = check_success(
            self, TEST_URL + "GNUJQCL9MD64AM56OH/timeline?relative_event_classes=family"
        )
        count = 0
        for event in rv:
            if event["label"] == "Marriage (Stepsister)":
                count = count + 1
        self.assertEqual(count, 4)

    def test_get_people_handle_timeline_parameter_ratings_validate_semantics(self):
        """Test invalid ratings parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "1QTJQCP5QMT2X7YJDK/timeline?ratings", check="boolean"
        )
