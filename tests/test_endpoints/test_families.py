#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Tests for the /api/families endpoints using example_gramps."""

import unittest

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

TEST_URL = BASE_URL + "/families/"


class TestFamilies(unittest.TestCase):
    """Test cases for the /api/families endpoint for a list of families."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def test_get_families_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_families_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "?extend=all&profile=all&backlinks=1", "Family"
        )

    def test_get_families_expected_results_total(self):
        """Test expected number of results returned."""
        check_totals(self, TEST_URL + "?keys=handle", get_object_count("families"))

    def test_get_families_expected_results(self):
        """Test some expected results returned."""
        rv = check_success(self, TEST_URL)
        # check first expected record
        self.assertEqual(rv[0]["handle"], "cc82060505948b9e57f")
        self.assertEqual(rv[0]["father_handle"], "cc82060504445ab6deb")
        self.assertEqual(rv[0]["mother_handle"], "cc8206050980ea622d0")
        # check last expected record
        self.assertEqual(rv[-1]["handle"], "WYAKQC3ELT2539P9W2")
        self.assertEqual(rv[-1]["father_handle"], "B5QKQCZM5CDWEV4SP4")
        self.assertEqual(rv[-1]["mother_handle"], "LYAKQCT2QKFQUVU4AF")

    def test_get_families_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk_parm=1")

    def test_get_families_parameter_gramps_id_validate_semantics(self):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?gramps_id", check="base")

    def test_get_families_parameter_gramps_id_missing_content(self):
        """Test response for missing gramps_id object."""
        check_resource_missing(self, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_families_parameter_gramps_id_expected_result(self):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(self, TEST_URL + "?gramps_id=F0045")
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "3HUJQCK4DH582YUTZG")

    def test_get_families_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?strip", check="boolean")

    def test_get_families_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL)

    def test_get_families_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?keys", check="base")

    def test_get_families_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(self, TEST_URL, ["attribute_list", "handle", "type"])

    def test_get_families_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL, [",".join(["attribute_list", "handle", "type"])]
        )

    def test_get_families_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?skipkeys", check="base")

    def test_get_families_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(self, TEST_URL, ["attribute_list", "handle", "type"])

    def test_get_families_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, [",".join(["attribute_list", "handle", "type"])]
        )

    def test_get_families_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?page", check="number")

    def test_get_families_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?pagesize", check="number")

    def test_get_families_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(self, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_families_parameter_soundex_validate_semantics(self):
        """Test invalid soundex parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?soundex", check="boolean")

    def test_get_families_parameter_soundex_expected_result(self):
        """Test soundex parameter produces expected result."""
        rv = check_boolean_parameter(
            self, TEST_URL + "?keys=handle,soundex", "soundex", join="&"
        )
        self.assertEqual(rv[0]["soundex"], "Z000")
        self.assertEqual(rv[244]["soundex"], "G656")

    def test_get_families_parameter_sort_validate_semantics(self):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?sort", check="list")

    def test_get_families_parameter_sort_change_ascending_expected_result(self):
        """Test sort parameter change ascending result."""
        check_sort_parameter(self, TEST_URL, "change")

    def test_get_families_parameter_sort_change_descending_expected_result(self):
        """Test sort parameter change descending result."""
        check_sort_parameter(self, TEST_URL, "change", direction="-")

    def test_get_families_parameter_sort_gramps_id_ascending_expected_result(self):
        """Test sort parameter gramps_id ascending result."""
        check_sort_parameter(self, TEST_URL, "gramps_id")

    def test_get_families_parameter_sort_gramps_id_descending_expected_result(self):
        """Test sort parameter gramps_id descending result."""
        check_sort_parameter(self, TEST_URL, "gramps_id", direction="-")

    def test_get_families_parameter_sort_private_ascending_expected_result(self):
        """Test sort parameter private ascending result."""
        check_sort_parameter(self, TEST_URL, "private")

    def test_get_families_parameter_sort_private_descending_expected_result(self):
        """Test sort parameter private descending result."""
        check_sort_parameter(self, TEST_URL, "private", direction="-")

    def test_get_families_parameter_sort_soundex_ascending_expected_result(self):
        """Test sort parameter soundex ascending result."""
        check_sort_parameter(self, TEST_URL + "?soundex=1", "soundex", join="&")

    def test_get_families_parameter_sort_soundex_descending_expected_result(self):
        """Test sort parameter soundex descending result."""
        check_sort_parameter(
            self, TEST_URL + "?soundex=1", "soundex", direction="-", join="&"
        )

    def test_get_families_parameter_sort_surname_ascending_expected_result(self):
        """Test sort parameter surname ascending result."""
        rv = check_success(self, TEST_URL + "?keys=profile&profile=self&sort=+surname")
        self.assertEqual(rv[0]["profile"]["family_surname"], "Adams")
        self.assertEqual(rv[-1]["profile"]["family_surname"], "鈴木")

    def test_get_families_parameter_sort_surname_descending_expected_result(self):
        """Test sort parameter surname descending result."""
        rv = check_success(self, TEST_URL + "?keys=profile&profile=self&sort=-surname")
        self.assertEqual(rv[0]["profile"]["family_surname"], "鈴木")
        self.assertEqual(rv[-1]["profile"]["family_surname"], "Adams")

    def test_get_families_parameter_sort_type_ascending_expected_result(self):
        """Test sort parameter type ascending result."""
        check_sort_parameter(self, TEST_URL, "type")

    def test_get_families_parameter_sort_type_descending_expected_result(self):
        """Test sort parameter type descending result."""
        check_sort_parameter(self, TEST_URL, "type", direction="-")

    def test_get_families_parameter_sort_surname_ascending_expected_result_with_locale(
        self,
    ):
        """Test sort parameter surname ascending result using different locale."""
        rv = check_success(
            self, TEST_URL + "?keys=profile&profile=self&sort=+surname&locale=zh_CN"
        )
        self.assertEqual(rv[0]["profile"]["family_surname"], "賈")
        self.assertEqual(rv[-1]["profile"]["family_surname"], "")

    def test_get_families_parameter_sort_surname_descending_expected_result_with_locale(
        self,
    ):
        """Test sort parameter surname descending result using different locale."""
        rv = check_success(
            self, TEST_URL + "?keys=profile&profile=self&sort=-surname&locale=zh_CN"
        )
        self.assertEqual(rv[0]["profile"]["family_surname"], "")
        self.assertEqual(rv[-1]["profile"]["family_surname"], "賈")

    def test_get_families_parameter_filter_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?filter", check="base")

    def test_get_families_parameter_filter_missing_content(self):
        """Test response when missing the filter."""
        check_resource_missing(self, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_families_parameter_rules_validate_syntax(self):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            self, TEST_URL + '?rules={"rules"[{"name":"IsBookmarked"}]}'
        )

    def test_get_families_parameter_rules_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            self, TEST_URL + '?rules={"some":"where","rules":[{"name":"IsBookmarked"}]}'
        )
        check_invalid_semantics(
            self,
            TEST_URL + '?rules={"function":"none","rules":[{"name":"IsBookmarked"}]}',
        )

    def test_get_families_parameter_rules_missing_content(self):
        """Test rules parameter missing request content."""
        check_resource_missing(
            self, TEST_URL + '?rules={"rules":[{"name":"Lothlorian"}]}'
        )

    def test_get_families_parameter_rules_expected_response_single_rule(self):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            self, TEST_URL + '?keys=handle&rules={"rules":[{"name":"IsBookmarked"}]}'
        )
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "9OUJQCBOHW9UEK9CNV")

    def test_get_families_parameter_rules_expected_response_multiple_rules(self):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"rules":[{"name":"IsBookmarked"},{"name":"HasRelType","values":["Married"]}]}',
        )
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "9OUJQCBOHW9UEK9CNV")

    def test_get_families_parameter_rules_expected_response_or_function(self):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"IsBookmarked"},{"name":"HasRelType","values":["Unknown"]}]}',
        )
        self.assertEqual(len(rv), 6)

    def test_get_families_parameter_rules_expected_response_one_function(self):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"IsBookmarked"},{"name":"HasRelType","values":["Unknown"]}]}',
        )
        self.assertEqual(len(rv), 6)

    def test_get_families_parameter_rules_expected_response_invert(self):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasRelType","values":["Married"]}]}',
        )
        self.assertEqual(len(rv), 5)

    def test_get_families_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?extend", check="list")

    def test_get_families_parameter_extend_expected_result_child_ref_list(self):
        """Test extend child_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=F0045",
            "child_ref_list",
            "children",
            join="&",
            reference=True,
        )

    def test_get_families_parameter_extend_expected_result_citation_list(self):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=F0045", "citation_list", "citations", join="&"
        )

    def test_get_families_parameter_extend_expected_result_event_ref_list(self):
        """Test extend event_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=F0045",
            "event_ref_list",
            "events",
            join="&",
            reference=True,
        )

    def test_get_families_parameter_extend_expected_result_father(self):
        """Test extend father result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=F0045", "father_handle", "father", join="&"
        )

    def test_get_families_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=F0045",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_families_parameter_extend_expected_result_mother(self):
        """Test extend mother result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=F0045", "mother_handle", "mother", join="&"
        )

    def test_get_families_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=F0045", "note_list", "notes", join="&"
        )

    def test_get_families_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=F0045", "tag_list", "tags", join="&"
        )

    def test_get_families_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "?gramps_id=F0045&extend=all&keys=extended")
        self.assertEqual(len(rv[0]["extended"]), 8)
        for key in [
            "children",
            "citations",
            "events",
            "father",
            "media",
            "mother",
            "notes",
            "tags",
        ]:
            self.assertIn(key, rv[0]["extended"])

    def test_get_families_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=F0045&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 2)
        self.assertIn("notes", rv[0]["extended"])
        self.assertIn("tags", rv[0]["extended"])

    def test_get_families_parameter_profile_validate_semantics(self):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?profile", check="list")

    def test_get_families_parameter_profile_expected_result(self):
        """Test expected response."""
        rv = check_success(
            self, TEST_URL + "?page=1&pagesize=1&keys=profile&profile=all"
        )
        self.assertEqual(
            rv[0]["profile"],
            {
                "children": [
                    {
                        "birth": {
                            "age": "0 days",
                            "citations": 0,
                            "confidence": 0,
                            "date": "203 (Islamic)",
                            "place": "",
                            "place_name": "",
                            "type": "Birth",
                            "summary": "Birth - , صالح",
                        },
                        "death": {},
                        "gramps_id": "I2115",
                        "handle": "cc82060516c6c141500",
                        "name_display": ", صالح",
                        "name_given": "صالح",
                        "name_surname": "",
                        "name_suffix": "",
                        "sex": "M",
                    }
                ],
                "divorce": {},
                "events": [],
                "family_surname": "",
                "father": {
                    "birth": {
                        "age": "0 days",
                        "citations": 0,
                        "confidence": 0,
                        "date": "164-03 (Islamic)",
                        "place": "",
                        "place_name": "",
                        "type": "Birth",
                        "summary": "Birth - , أحمد",
                    },
                    "death": {
                        "age": "74 years, 8 months, 26 days",
                        "citations": 0,
                        "confidence": 0,
                        "date": "241-03-12 (Islamic)",
                        "place": "",
                        "place_name": "",
                        "type": "Death",
                        "summary": "Death - , أحمد",
                    },
                    "gramps_id": "I2111",
                    "handle": "cc82060504445ab6deb",
                    "name_display": ", أحمد",
                    "name_given": "أحمد",
                    "name_surname": "",
                    "name_suffix": "",
                    "sex": "M",
                },
                "gramps_id": "F0745",
                "handle": "cc82060505948b9e57f",
                "marriage": {},
                "mother": {
                    "birth": {},
                    "death": {
                        "citations": 0,
                        "confidence": 0,
                        "date": "234 (Islamic)",
                        "place": "",
                        "place_name": "",
                        "type": "Death",
                        "summary": "Death - الفضل, العباسة",
                    },
                    "gramps_id": "I2112",
                    "handle": "cc8206050980ea622d0",
                    "name_display": "الفضل, العباسة",
                    "name_given": "العباسة",
                    "name_surname": "الفضل",
                    "name_suffix": "",
                    "sex": "F",
                },
                "references": {
                    "person": [
                        {
                            "birth": {
                                "date": "164-03 (Islamic)",
                                "place": "",
                                "place_name": "",
                                "type": "Birth",
                                "summary": "Birth - , أحمد",
                            },
                            "death": {
                                "date": "241-03-12 (Islamic)",
                                "place": "",
                                "place_name": "",
                                "type": "Death",
                                "summary": "Death - , أحمد",
                            },
                            "gramps_id": "I2111",
                            "handle": "cc82060504445ab6deb",
                            "name_display": ", أحمد",
                            "name_given": "أحمد",
                            "name_surname": "",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        {
                            "birth": {},
                            "death": {
                                "date": "234 (Islamic)",
                                "place": "",
                                "place_name": "",
                                "type": "Death",
                                "summary": "Death - الفضل, العباسة",
                            },
                            "gramps_id": "I2112",
                            "handle": "cc8206050980ea622d0",
                            "name_display": "الفضل, العباسة",
                            "name_given": "العباسة",
                            "name_surname": "الفضل",
                            "name_suffix": "",
                            "sex": "F",
                        },
                        {
                            "birth": {
                                "date": "203 (Islamic)",
                                "place": "",
                                "place_name": "",
                                "type": "Birth",
                                "summary": "Birth - , صالح",
                            },
                            "death": {},
                            "gramps_id": "I2115",
                            "handle": "cc82060516c6c141500",
                            "name_display": ", صالح",
                            "name_given": "صالح",
                            "name_surname": "",
                            "name_suffix": "",
                            "sex": "M",
                        },
                    ]
                },
                "relationship": "Married",
            },
        )

    def test_get_families_parameter_profile_expected_result_with_locale(self):
        """Test expected profile response for a locale."""
        rv = check_success(
            self, TEST_URL + "?page=1&keys=profile&profile=all&locale=it"
        )
        self.assertEqual(rv[0]["profile"]["father"]["birth"]["age"], "0 giorni")
        self.assertEqual(rv[0]["profile"]["father"]["birth"]["type"], "Nascita")
        self.assertEqual(rv[0]["profile"]["relationship"], "Sposati")

    def test_get_families_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?backlinks", check="boolean")

    def test_get_families_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_success(self, TEST_URL + "?page=1&keys=backlinks&backlinks=1")
        for key in [
            "cc82060504445ab6deb",
            "cc8206050980ea622d0",
            "cc82060516c6c141500",
        ]:
            self.assertIn(key, rv[0]["backlinks"]["person"])


class TestFamiliesHandle(unittest.TestCase):
    """Test cases for the /api/families/{handle} endpoint for a specific family."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def test_get_families_handle_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "7MTJQCHRUUYSUA8ABB")

    def test_get_families_handle_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB?extend=all&profile=all&backlinks=1",
            "Family",
        )

    def test_get_families_handle_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist")

    def test_get_families_handle_expected_result(self):
        """Test response for a specific family."""
        rv = check_success(self, TEST_URL + "7MTJQCHRUUYSUA8ABB")
        self.assertEqual(rv["gramps_id"], "F0033")
        self.assertEqual(rv["father_handle"], "KLTJQC70XVZJSPQ43U")
        self.assertEqual(rv["mother_handle"], "JFWJQCRREDFKZLDKVD")

    def test_get_families_handle_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "7MTJQCHRUUYSUA8ABB?junk_parm=1")

    def test_get_families_handle_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?strip", check="boolean"
        )

    def test_get_families_handle_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "7MTJQCHRUUYSUA8ABB")

    def test_get_families_handle_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?keys", check="base"
        )

    def test_get_families_handle_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", ["attribute_list", "handle", "type"]
        )

    def test_get_families_handle_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB",
            [",".join(["attribute_list", "handle", "type"])],
        )

    def test_get_families_handle_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?skipkeys", check="base"
        )

    def test_get_families_handle_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", ["attribute_list", "handle", "type"]
        )

    def test_get_families_handle_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB",
            [",".join(["attribute_list", "handle", "type"])],
        )

    def test_get_families_handle_parameter_soundex_validate_semantics(self):
        """Test invalid soundex parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?soundex", check="boolean"
        )

    def test_get_families_handle_parameter_soundex_expected_result(self):
        """Test soundex parameter produces expected result."""
        rv = check_boolean_parameter(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB?keys=handle,soundex",
            "soundex",
            join="&",
        )
        self.assertEqual(rv["soundex"], "G656")

    def test_get_families_handle_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?extend", check="list"
        )

    def test_get_families_handle_parameter_extend_expected_result_child_ref_list(self):
        """Test extend child_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB",
            "child_ref_list",
            "children",
            reference=True,
        )

    def test_get_families_handle_parameter_extend_expected_result_citation_list(self):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "citation_list", "citations"
        )

    def test_get_families_handle_parameter_extend_expected_result_event_ref_list(self):
        """Test extend event_ref_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "7MTJQCHRUUYSUA8ABB",
            "event_ref_list",
            "events",
            reference=True,
        )

    def test_get_families_handle_parameter_extend_expected_result_father(self):
        """Test extend father result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "father_handle", "father"
        )

    def test_get_families_handle_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "media_list", "media", reference=True
        )

    def test_get_families_handle_parameter_extend_expected_result_mother(self):
        """Test extend mother result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "mother_handle", "mother"
        )

    def test_get_families_handle_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "note_list", "notes"
        )

    def test_get_families_handle_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "tag_list", "tags"
        )

    def test_get_families_handle_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?extend=all&keys=extended"
        )
        self.assertEqual(len(rv["extended"]), 8)
        for key in [
            "children",
            "citations",
            "events",
            "father",
            "media",
            "mother",
            "notes",
            "tags",
        ]:
            self.assertIn(key, rv["extended"])

    def test_get_families_handle_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "7MTJQCHRUUYSUA8ABB?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv["extended"]), 2)
        self.assertIn("notes", rv["extended"])
        self.assertIn("tags", rv["extended"])

    def test_get_families_handle_parameter_profile_validate_semantics(self):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?profile", check="list"
        )

    def test_get_families_handle_parameter_profile_expected_result(self):
        """Test response as expected."""
        rv = check_success(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?keys=profile&profile=all"
        )
        self.assertEqual(
            rv["profile"],
            {
                "children": [
                    {
                        "birth": {
                            "age": "0 days",
                            "citations": 0,
                            "confidence": 0,
                            "date": "1983-10-05",
                            "place": "Ottawa, La Salle, IL, USA",
                            "place_name": "Ottawa",
                            "type": "Birth",
                            "summary": "Birth - Garner, Stephen Gerard",
                        },
                        "death": {},
                        "gramps_id": "I0124",
                        "handle": "1GWJQCGOOZ8FJW3YK9",
                        "name_display": "Garner, Stephen Gerard",
                        "name_given": "Stephen Gerard",
                        "name_surname": "Garner",
                        "name_suffix": "",
                        "sex": "M",
                    },
                    {
                        "birth": {
                            "age": "0 days",
                            "citations": 0,
                            "confidence": 0,
                            "date": "1985-02-11",
                            "place": "Ottawa, La Salle, IL, USA",
                            "place_name": "Ottawa",
                            "type": "Birth",
                            "summary": "Birth - Garner, Daniel Patrick",
                        },
                        "death": {},
                        "gramps_id": "I0125",
                        "handle": "IGWJQCSVT8NXTFXOFJ",
                        "name_display": "Garner, Daniel Patrick",
                        "name_given": "Daniel Patrick",
                        "name_surname": "Garner",
                        "name_suffix": "",
                        "sex": "M",
                    },
                ],
                "divorce": {},
                "events": [
                    {
                        "citations": 0,
                        "confidence": 0,
                        "date": "1979-01-06",
                        "place": "Farmington, MO, USA",
                        "place_name": "Farmington",
                        "span": "0 days",
                        "type": "Marriage",
                        "summary": "Marriage - Garner, Gerard Stephen and George, Elizabeth",
                    }
                ],
                "family_surname": "Garner",
                "father": {
                    "birth": {
                        "age": "0 days",
                        "citations": 0,
                        "confidence": 0,
                        "date": "1955-07-31",
                        "place": "Ottawa, La Salle, IL, USA",
                        "place_name": "Ottawa",
                        "type": "Birth",
                        "summary": "Birth - Garner, Gerard Stephen",
                    },
                    "death": {},
                    "gramps_id": "I0017",
                    "handle": "KLTJQC70XVZJSPQ43U",
                    "name_display": "Garner, Gerard Stephen",
                    "name_given": "Gerard Stephen",
                    "name_surname": "Garner",
                    "name_suffix": "",
                    "sex": "M",
                },
                "gramps_id": "F0033",
                "handle": "7MTJQCHRUUYSUA8ABB",
                "marriage": {
                    "citations": 0,
                    "confidence": 0,
                    "date": "1979-01-06",
                    "place": "Farmington, MO, USA",
                    "place_name": "Farmington",
                    "span": "0 days",
                    "type": "Marriage",
                    "summary": "Marriage - Garner, Gerard Stephen and George, Elizabeth",
                },
                "mother": {
                    "birth": {
                        "age": "0 days",
                        "citations": 0,
                        "confidence": 0,
                        "date": "1957-01-31",
                        "place": "",
                        "place_name": "",
                        "type": "Birth",
                        "summary": "Birth - George, Elizabeth",
                    },
                    "death": {},
                    "gramps_id": "I0123",
                    "handle": "JFWJQCRREDFKZLDKVD",
                    "name_display": "George, Elizabeth",
                    "name_given": "Elizabeth",
                    "name_surname": "George",
                    "name_suffix": "",
                    "sex": "F",
                },
                "references": {
                    "person": [
                        {
                            "birth": {
                                "date": "1983-10-05",
                                "place": "Ottawa, La Salle, IL, USA",
                                "place_name": "Ottawa",
                                "type": "Birth",
                                "summary": "Birth - Garner, Stephen Gerard",
                            },
                            "death": {},
                            "gramps_id": "I0124",
                            "handle": "1GWJQCGOOZ8FJW3YK9",
                            "name_display": "Garner, Stephen Gerard",
                            "name_given": "Stephen Gerard",
                            "name_surname": "Garner",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        {
                            "birth": {
                                "date": "1985-02-11",
                                "place": "Ottawa, La Salle, IL, USA",
                                "place_name": "Ottawa",
                                "type": "Birth",
                                "summary": "Birth - Garner, Daniel Patrick",
                            },
                            "death": {},
                            "gramps_id": "I0125",
                            "handle": "IGWJQCSVT8NXTFXOFJ",
                            "name_display": "Garner, Daniel Patrick",
                            "name_given": "Daniel Patrick",
                            "name_surname": "Garner",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        {
                            "birth": {
                                "date": "1957-01-31",
                                "place": "",
                                "place_name": "",
                                "type": "Birth",
                                "summary": "Birth - George, Elizabeth",
                            },
                            "death": {},
                            "gramps_id": "I0123",
                            "handle": "JFWJQCRREDFKZLDKVD",
                            "name_display": "George, Elizabeth",
                            "name_given": "Elizabeth",
                            "name_surname": "George",
                            "name_suffix": "",
                            "sex": "F",
                        },
                        {
                            "birth": {
                                "date": "1955-07-31",
                                "place": "Ottawa, La Salle, IL, USA",
                                "place_name": "Ottawa",
                                "type": "Birth",
                                "summary": "Birth - Garner, Gerard Stephen",
                            },
                            "death": {},
                            "gramps_id": "I0017",
                            "handle": "KLTJQC70XVZJSPQ43U",
                            "name_display": "Garner, Gerard Stephen",
                            "name_given": "Gerard Stephen",
                            "name_surname": "Garner",
                            "name_suffix": "",
                            "sex": "M",
                        },
                    ]
                },
                "relationship": "Married",
            },
        )

    def test_get_families_handle_parameter_profile_expected_result_with_locale(self):
        """Test response as expected."""
        rv = check_success(self, TEST_URL + "7MTJQCHRUUYSUA8ABB?profile=all&locale=de")
        self.assertEqual(rv["profile"]["father"]["birth"]["age"], "0 Tage")
        self.assertEqual(rv["profile"]["father"]["birth"]["type"], "Geburt")

    def test_get_families_handle_parameter_profile_expected_result_with_name_format(
        self,
    ):
        """Test response as expected."""
        rv = check_success(
            self,
            TEST_URL
            + "7MTJQCHRUUYSUA8ABB?profile=all&name_format=%25f%20%28%25c%29%20%25L",
        )
        self.assertEqual(
            rv["profile"]["children"][0]["name_display"], "Stephen Gerard GARNER"
        )
        self.assertEqual(
            rv["profile"]["father"]["name_display"], "Gerard Stephen GARNER"
        )
        self.assertEqual(
            rv["profile"]["references"]["person"][1]["name_display"],
            "Daniel Patrick GARNER",
        )

    def test_get_families_handle_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?backlinks", check="boolean"
        )

    def test_get_families_handle_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(self, TEST_URL + "7MTJQCHRUUYSUA8ABB", "backlinks")
        self.assertIn("backlinks", rv)
        for key in [
            "1GWJQCGOOZ8FJW3YK9",
            "IGWJQCSVT8NXTFXOFJ",
            "JFWJQCRREDFKZLDKVD",
            "KLTJQC70XVZJSPQ43U",
        ]:
            self.assertIn(key, rv["backlinks"]["person"])

    def test_get_families_handle_parameter_backlinks_expected_results_extended(self):
        """Test backlinks extended result."""
        rv = check_success(
            self, TEST_URL + "7MTJQCHRUUYSUA8ABB?backlinks=1&extend=backlinks"
        )
        self.assertIn("backlinks", rv)
        self.assertIn("extended", rv)
        self.assertIn("backlinks", rv["extended"])
        for obj in rv["extended"]["backlinks"]["person"]:
            self.assertIn(
                obj["handle"],
                [
                    "1GWJQCGOOZ8FJW3YK9",
                    "IGWJQCSVT8NXTFXOFJ",
                    "JFWJQCRREDFKZLDKVD",
                    "KLTJQC70XVZJSPQ43U",
                ],
            )


class TestFamiliesHandleTimeline(unittest.TestCase):
    """Test cases for the /api/families/{handle}/timeline endpoint for a specific family."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def test_get_families_handle_timeline_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline")

    def test_get_families_handle_timeline_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?ratings=1",
            "TimelineEventProfile",
        )

    def test_get_families_handle_timeline_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist/timeline")

    def test_get_families_handle_timeline_expected_result(self):
        """Test response for specific person."""
        rv = check_success(self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline")
        self.assertEqual(rv[0]["gramps_id"], "E1679")
        self.assertEqual(rv[0]["label"], "Birth")
        self.assertEqual(rv[1]["gramps_id"], "E1656")
        self.assertEqual(rv[1]["label"], "Birth")
        self.assertEqual(rv[13]["gramps_id"], "E1657")
        self.assertEqual(rv[13]["label"], "Death")
        self.assertEqual(rv[32]["gramps_id"], "E1704")
        self.assertEqual(rv[32]["label"], "Burial")

    def test_get_families_handle_timeline_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?junk_parm=1"
        )

    def test_get_families_handle_timeline_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?strip", check="boolean"
        )

    def test_get_families_handle_timeline_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline")

    def test_get_families_handle_timeline_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?keys", check="base"
        )

    def test_get_families_handle_timeline_parameter_keys_expected_result_single_key(
        self,
    ):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline", ["date", "handle", "type"]
        )

    def test_get_families_handle_timeline_parameter_keys_expected_result_multiple_keys(
        self,
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline",
            [",".join(["date", "handle", "type"])],
        )

    def test_get_families_handle_timeline_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?skipkeys", check="base"
        )

    def test_get_families_handle_timeline_parameter_skipkeys_expected_result_single_key(
        self,
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline", ["date", "handle", "type"]
        )

    def test_get_families_handle_timeline_parameter_skipkeys_expected_result_multiple_keys(
        self,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline",
            [",".join(["date", "handle", "type"])],
        )

    def test_get_families_handle_timeline_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?page", check="number"
        )

    def test_get_families_handle_timeline_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?pagesize", check="number"
        )

    def test_get_families_handle_timeline_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?keys=handle", 2, join="&"
        )

    def test_get_families_handle_timeline_parameter_events_validate_semantics(self):
        """Test invalid events parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?events", check="list"
        )

    def test_get_families_handle_timeline_parameter_events_expected_result(self):
        """Test events parameter for expected results."""
        rv = check_success(self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?events=Birth")
        count = 0
        for event in rv:
            if event["type"] == "Burial":
                count = count + 1
        self.assertEqual(count, 0)
        rv = check_success(self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?events=Burial")
        count = 0
        for event in rv:
            if event["type"] == "Burial":
                count = count + 1
        self.assertEqual(count, 8)

    def test_get_families_handle_timeline_parameter_event_class_validate_semantics(
        self,
    ):
        """Test invalid event_class parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?event_class", check="list"
        )

    def test_get_families_handle_timeline_parameter_event_class_expected_result(self):
        """Test event_class parameter for expected results."""
        rv = check_success(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?event_classes=other"
        )
        count = 0
        for event in rv:
            if event["type"] == "Burial":
                count = count + 1
        self.assertEqual(count, 0)
        rv = check_success(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?event_classes=vital"
        )
        count = 0
        for event in rv:
            if event["type"] == "Burial":
                count = count + 1

    def test_get_families_handle_timeline_parameter_ratings_validate_semantics(self):
        """Test invalid ratings parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "9OUJQCBOHW9UEK9CNV/timeline?ratings", check="boolean"
        )
