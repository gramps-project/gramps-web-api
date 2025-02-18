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

"""Tests for the /api/citations endpoints using example_gramps."""

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

TEST_URL = BASE_URL + "/citations/"


class TestCitations(unittest.TestCase):
    """Test cases for the /api/citations endpoint for a list of citations."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_citations_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_citations_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "?extend=all&profile=all&backlinks=1", "Citation"
        )

    def test_get_citations_expected_results_total(self):
        """Test expected number of results returned."""
        check_totals(self, TEST_URL + "?keys=handle", get_object_count("citations"))

    def test_get_citations_expected_results(self):
        """Test some expected results returned."""
        rv = check_success(self, TEST_URL)
        # check first expected record
        self.assertEqual(rv[0]["gramps_id"], "C0000")
        self.assertEqual(rv[0]["handle"], "c140d2362f25a92643b")
        self.assertEqual(rv[0]["source_handle"], "b39fe3f390e30bd2b99")
        # check last expected record
        self.assertEqual(rv[-1]["gramps_id"], "C2324")
        self.assertEqual(rv[-1]["handle"], "c140d28761775ca12ba")
        self.assertEqual(rv[-1]["source_handle"], "VUBKMQTA2XZG1V6QP8")

    def test_get_citations_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk_parm=1")

    def test_get_citations_parameter_gramps_id_validate_semantics(self):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?gramps_id", check="base")

    def test_get_citations_parameter_gramps_id_missing_content(self):
        """Test response for missing gramps_id object."""
        check_resource_missing(self, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_citations_parameter_gramps_id_expected_result(self):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(self, TEST_URL + "?gramps_id=C2849")
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "c140dde678c5c4f4537")
        self.assertEqual(rv[0]["source_handle"], "c140d4ef77841431905")

    def test_get_citations_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?strip", check="boolean")

    def test_get_citations_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL)

    def test_get_citations_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?keys", check="base")

    def test_get_citations_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(self, TEST_URL, ["attribute_list", "handle", "tag_list"])

    def test_get_citations_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_citations_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?skipkeys", check="base")

    def test_get_citations_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, ["attribute_list", "handle", "tag_list"]
        )

    def test_get_citations_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_citations_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?page", check="number")

    def test_get_citations_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?pagesize", check="number")

    def test_get_citations_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(self, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_citations_parameter_sort_validate_semantics(self):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?sort", check="list")

    def test_get_citations_parameter_sort_change_ascending_expected_result(self):
        """Test sort parameter change ascending result."""
        check_sort_parameter(self, TEST_URL, "change")

    def test_get_citations_parameter_sort_change_descending_expected_result(self):
        """Test sort parameter change descending result."""
        check_sort_parameter(self, TEST_URL, "change", direction="-")

    def test_get_citations_parameter_sort_confidence_ascending_expected_result(self):
        """Test sort parameter confidence ascending result."""
        check_sort_parameter(self, TEST_URL, "confidence")

    def test_get_citations_parameter_sort_confidence_descending_expected_result(self):
        """Test sort parameter confidence descending result."""
        check_sort_parameter(self, TEST_URL, "confidence", direction="-")

    def test_get_citations_parameter_sort_date_ascending_expected_result(self):
        """Test sort parameter date ascending result."""
        rv = check_success(self, TEST_URL + "?keys=date&sort=+date")
        self.assertEqual(rv[0]["date"]["sortval"], 0)
        self.assertEqual(rv[-1]["date"]["sortval"], 2447956)

    def test_get_citations_parameter_sort_date_descending_expected_result(self):
        """Test sort parameter date descending result."""
        rv = check_success(self, TEST_URL + "?keys=date&profile=self&sort=-date")
        self.assertEqual(rv[0]["date"]["sortval"], 2447956)
        self.assertEqual(rv[-1]["date"]["sortval"], 0)

    def test_get_citations_parameter_sort_gramps_id_ascending_expected_result(self):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id")
        self.assertEqual(rv[0]["gramps_id"], "C0000")
        self.assertEqual(rv[-1]["gramps_id"], "C2853")

    def test_get_citations_parameter_sort_gramps_id_descending_expected_result(self):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id", direction="-")
        self.assertEqual(rv[0]["gramps_id"], "C2853")
        self.assertEqual(rv[-1]["gramps_id"], "C0000")

    def test_get_citations_parameter_sort_private_ascending_expected_result(self):
        """Test sort parameter private ascending result."""
        check_sort_parameter(self, TEST_URL, "private")

    def test_get_citations_parameter_sort_private_descending_expected_result(self):
        """Test sort parameter private descending result."""
        check_sort_parameter(self, TEST_URL, "private", direction="-")

    def test_get_citations_parameter_filter_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?filter", check="base")

    def test_get_citations_parameter_filter_missing_content(self):
        """Test response when missing the filter."""
        check_resource_missing(self, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_citations_parameter_rules_validate_syntax(self):
        """Test invalid rules syntax."""
        check_invalid_syntax(self, TEST_URL + '?rules={"rules"[{"name":"HasNote"}]}')

    def test_get_citations_parameter_rules_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            self, TEST_URL + '?rules={"some":"where","rules":[{"name":"HasNote"}]}'
        )
        check_invalid_semantics(
            self, TEST_URL + '?rules={"function":"none","rules":[{"name":"HasNote"}]}'
        )

    def test_get_citations_parameter_rules_missing_content(self):
        """Test rules parameter missing request content."""
        check_resource_missing(self, TEST_URL + '?rules={"rules":[{"name":"Gondor"}]}')

    def test_get_citations_parameter_rules_expected_response_single_rule(self):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(self, TEST_URL + '?rules={"rules":[{"name":"HasNote"}]}')
        for key in ["ac380498bc46102e1e8", "ae13613d581506d040892f88a21"]:
            self.assertIn(key, rv[0]["note_list"])

    def test_get_citations_parameter_rules_expected_response_multiple_rules(self):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        for key in ["ac380498bc46102e1e8", "ae13613d581506d040892f88a21"]:
            self.assertIn(key, rv[0]["note_list"])

    def test_get_citations_parameter_rules_expected_response_or_function(self):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        self.assertEqual(len(rv), 2854)

    def test_get_citations_parameter_rules_expected_response_one_function(self):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        self.assertEqual(len(rv), 2853)

    def test_get_citations_parameter_rules_expected_response_invert(self):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasCitation","values":["", "", 3]}]}',
        )
        self.assertEqual(len(rv), 2851)

    def test_get_citations_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?extend", check="list")

    def test_get_citations_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=C2849",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_citations_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=C2849", "note_list", "notes", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_source_handle(self):
        """Test extend source_handle result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=C2849", "source_handle", "source", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=C2849", "tag_list", "tags", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "?gramps_id=C2849&extend=all&keys=extended")
        self.assertEqual(len(rv[0]["extended"]), 4)
        for key in ["media", "notes", "source", "tags"]:
            self.assertIn(key, rv[0]["extended"])

    def test_get_citations_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=C2849&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 2)
        self.assertIn("notes", rv[0]["extended"])
        self.assertIn("tags", rv[0]["extended"])

    def test_get_citations_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?backlinks", check="boolean")

    def test_get_citations_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_success(self, TEST_URL + "?page=1&keys=backlinks&backlinks=1")
        self.assertIn("a5af0ecb107303354a0", rv[0]["backlinks"]["event"])

    def test_get_citations_parameter_dates_validate_semantics(self):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?dates", check="list")
        check_invalid_semantics(self, TEST_URL + "?dates=/1/1")
        check_invalid_semantics(self, TEST_URL + "?dates=1900//1")
        check_invalid_semantics(self, TEST_URL + "?dates=1900/1/")
        check_invalid_semantics(self, TEST_URL + "?dates=1900/a/1")
        check_invalid_semantics(self, TEST_URL + "?dates=-1900/a/1")
        check_invalid_semantics(self, TEST_URL + "?dates=1900/a/1-")
        check_invalid_semantics(self, TEST_URL + "?dates=1855/1/1-1900/*/1")

    def test_get_citations_parameter_dates_expected_result(self):
        """Test dates parameter expected results."""
        rv = check_success(self, TEST_URL + "?dates=1855/*/*")
        self.assertEqual(len(rv), 2)
        rv = check_success(self, TEST_URL + "?dates=-1900/1/1")
        self.assertEqual(len(rv), 2)
        rv = check_success(self, TEST_URL + "?dates=1900/1/1-")
        self.assertEqual(len(rv), 1)
        rv = check_success(self, TEST_URL + "?dates=1855/1/1-1900/12/31")
        self.assertEqual(len(rv), 2)


class TestCitationsHandle(unittest.TestCase):
    """Test cases for the /api/citations/{handle} endpoint for a specific citation."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_citations_handle_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "c140db880395cadf318")

    def test_get_citations_handle_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "c140db880395cadf318?extend=all&profile=all&backlinks=1",
            "Citation",
        )

    def test_get_citations_handle_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist")

    def test_get_citations_handle_expected_result(self):
        """Test response for a specific event."""
        rv = check_success(self, TEST_URL + "c140db880395cadf318")
        self.assertEqual(rv["gramps_id"], "C2844")
        self.assertEqual(rv["source_handle"], "c140d4ef77841431905")

    def test_get_citations_handle_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "c140db880395cadf318?junk_parm=1")

    def test_get_citations_handle_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "c140db880395cadf318?strip", check="boolean"
        )

    def test_get_citations_handle_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "c140db880395cadf318")

    def test_get_citations_handle_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "c140db880395cadf318?keys", check="base"
        )

    def test_get_citations_handle_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "c140db880395cadf318",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_citations_handle_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "c140db880395cadf318",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_citations_handle_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "c140db880395cadf318?skipkeys", check="base"
        )

    def test_get_citations_handle_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "c140db880395cadf318",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_citations_handle_parameter_skipkeys_expected_result_multiple_keys(
        self,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "c140db880395cadf318",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_citations_handle_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "c140db880395cadf318?extend", check="list"
        )

    def test_get_citations_handle_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "c140db880395cadf318",
            "media_list",
            "media",
            reference=True,
        )

    def test_get_citations_handle_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "c140db880395cadf318", "note_list", "notes"
        )

    def test_get_citations_handle_parameter_extend_expected_result_source_handle(self):
        """Test extend source_handle result."""
        check_single_extend_parameter(
            self, TEST_URL + "c140db880395cadf318", "source_handle", "source"
        )

    def test_get_citations_handle_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "c140db880395cadf318", "tag_list", "tags"
        )

    def test_get_citations_handle_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(
            self, TEST_URL + "c140db880395cadf318?extend=all&keys=extended"
        )
        self.assertEqual(len(rv["extended"]), 4)
        for key in ["media", "notes", "source", "tags"]:
            self.assertIn(key, rv["extended"])

    def test_get_citations_handle_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "c140db880395cadf318?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv["extended"]), 2)
        self.assertIn("notes", rv["extended"])
        self.assertIn("tags", rv["extended"])

    def test_get_citations_handle_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "c140db880395cadf318?backlinks", check="boolean"
        )

    def test_get_citations_handle_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            self, TEST_URL + "c140db880395cadf318", "backlinks"
        )
        for key in ["a5af0ecb107303354a0"]:
            self.assertIn(key, rv["backlinks"]["event"])

    def test_get_citations_handle_parameter_backlinks_expected_results_extended(self):
        """Test backlinks extended result."""
        rv = check_success(
            self, TEST_URL + "c140db880395cadf318?backlinks=1&extend=backlinks"
        )
        self.assertIn("backlinks", rv)
        self.assertIn("extended", rv)
        self.assertIn("backlinks", rv["extended"])
        for obj in rv["extended"]["backlinks"]["event"]:
            self.assertIn(obj["handle"], ["a5af0ecb107303354a0"])
