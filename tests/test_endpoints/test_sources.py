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

"""Tests for the /api/sources endpoints using example_gramps."""

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

TEST_URL = BASE_URL + "/sources/"


class TestSources(unittest.TestCase):
    """Test cases for the /api/sources endpoint for a list of sources."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_sources_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_sources_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "?extend=all&profile=all&backlinks=1", "Source"
        )

    def test_get_sources_expected_results_total(self):
        """Test expected number of results returned."""
        check_totals(self, TEST_URL + "?keys=handle", get_object_count("sources"))

    def test_get_sources_expected_results(self):
        """Test some expected results returned."""
        rv = check_success(self, TEST_URL)
        # check first expected record
        self.assertEqual(rv[0]["gramps_id"], "S0001")
        self.assertEqual(rv[0]["handle"], "c140d4ef77841431905")
        self.assertEqual(rv[0]["title"], "All possible citations")
        # check last expected record
        self.assertEqual(rv[-1]["gramps_id"], "S0002")
        self.assertEqual(rv[-1]["handle"], "VUBKMQTA2XZG1V6QP8")
        self.assertEqual(rv[-1]["title"], "World of the Wierd")

    def test_get_sources_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk_parm=1")

    def test_get_sources_parameter_gramps_id_validate_semantics(self):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?gramps_id", check="base")

    def test_get_sources_parameter_gramps_id_missing_content(self):
        """Test response for missing gramps_id object."""
        check_resource_missing(self, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_sources_parameter_gramps_id_expected_result(self):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(self, TEST_URL + "?gramps_id=S0000")
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "b39fe3f390e30bd2b99")
        self.assertEqual(
            rv[0]["title"], "Baptize registry 1850 - 1867 Great Falls Church"
        )

    def test_get_sources_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?strip", check="boolean")

    def test_get_sources_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL)

    def test_get_sources_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?keys", check="base")

    def test_get_sources_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(self, TEST_URL, ["abbrev", "handle", "title"])

    def test_get_sources_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(self, TEST_URL, [",".join(["abbrev", "handle", "title"])])

    def test_get_sources_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?skipkeys", check="base")

    def test_get_sources_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(self, TEST_URL, ["abbrev", "handle", "title"])

    def test_get_sources_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, [",".join(["abbrev", "handle", "title"])]
        )

    def test_get_sources_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?page", check="number")

    def test_get_sources_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?pagesize", check="number")

    def test_get_sources_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(self, TEST_URL + "?keys=handle", 2, join="&")

    def test_get_sources_parameter_sort_validate_semantics(self):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?sort", check="list")

    def test_get_sources_parameter_sort_abbrev_ascending_expected_result(self):
        """Test sort parameter abbrev ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "abbrev")
        self.assertEqual(rv[0]["abbrev"], "")
        self.assertEqual(rv[-1]["abbrev"], "WOTW")

    def test_get_sources_parameter_sort_abbrev_descending_expected_result(self):
        """Test sort parameter abbrev descending result."""
        rv = check_sort_parameter(self, TEST_URL, "abbrev", direction="-")
        self.assertEqual(rv[0]["abbrev"], "WOTW")
        self.assertEqual(rv[-1]["abbrev"], "")

    def test_get_sources_parameter_sort_author_ascending_expected_result(self):
        """Test sort parameter author ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "author")
        self.assertEqual(rv[0]["author"], "")
        self.assertEqual(rv[-1]["author"], "Priests of Great Falls Church 1850 - 1867")

    def test_get_sources_parameter_sort_author_descending_expected_result(self):
        """Test sort parameter author descending result."""
        rv = check_sort_parameter(self, TEST_URL, "author", direction="-")
        self.assertEqual(rv[0]["author"], "Priests of Great Falls Church 1850 - 1867")
        self.assertEqual(rv[-1]["author"], "")

    def test_get_sources_parameter_sort_change_ascending_expected_result(self):
        """Test sort parameter change ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "change")

    def test_get_sources_parameter_sort_change_descending_expected_result(self):
        """Test sort parameter change descending result."""
        rv = check_sort_parameter(self, TEST_URL, "change", direction="-")

    def test_get_sources_parameter_sort_gramps_id_ascending_expected_result(self):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id")
        self.assertEqual(rv[0]["gramps_id"], "S0000")
        self.assertEqual(rv[-1]["gramps_id"], "S0003")

    def test_get_sources_parameter_sort_gramps_id_descending_expected_result(self):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(self, TEST_URL, "gramps_id", direction="-")
        self.assertEqual(rv[0]["gramps_id"], "S0003")
        self.assertEqual(rv[-1]["gramps_id"], "S0000")

    def test_get_sources_parameter_sort_private_ascending_expected_result(self):
        """Test sort parameter private ascending result."""
        check_sort_parameter(self, TEST_URL, "private")

    def test_get_sources_parameter_sort_private_descending_expected_result(self):
        """Test sort parameter private descending result."""
        check_sort_parameter(self, TEST_URL, "private", direction="-")

    def test_get_sources_parameter_sort_pubinfo_ascending_expected_result(self):
        """Test sort parameter pubinfo ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "pubinfo")
        self.assertEqual(rv[0]["pubinfo"], "")
        self.assertEqual(rv[-1]["pubinfo"], "Microfilm Public Library Great Falls")

    def test_get_sources_parameter_sort_pubinfo_descending_expected_result(self):
        """Test sort parameter pubinfo descending result."""
        rv = check_sort_parameter(self, TEST_URL, "pubinfo", direction="-")
        self.assertEqual(rv[0]["pubinfo"], "Microfilm Public Library Great Falls")
        self.assertEqual(rv[-1]["pubinfo"], "")

    def test_get_sources_parameter_sort_title_ascending_expected_result(self):
        """Test sort parameter title ascending result."""
        rv = check_sort_parameter(self, TEST_URL, "title")
        self.assertEqual(rv[0]["title"], "All possible citations")
        self.assertEqual(rv[-1]["title"], "World of the Wierd")

    def test_get_sources_parameter_sort_title_descending_expected_result(self):
        """Test sort parameter title descending result."""
        rv = check_sort_parameter(self, TEST_URL, "title", direction="-")
        self.assertEqual(rv[0]["title"], "World of the Wierd")
        self.assertEqual(rv[-1]["title"], "All possible citations")

    def test_get_sources_parameter_filter_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?filter", check="base")

    def test_get_sources_parameter_filter_missing_content(self):
        """Test response when missing the filter."""
        check_resource_missing(self, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_sources_parameter_rules_validate_syntax(self):
        """Test invalid rules syntax."""
        check_invalid_syntax(self, TEST_URL + '?rules={"rules"[{"name":"HasNote"}]}')

    def test_get_sources_parameter_rules_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            self, TEST_URL + '?rules={"some":"where","rules":[{"name":"HasNote"}]}'
        )
        check_invalid_semantics(
            self, TEST_URL + '?rules={"function":"none","rules":[{"name":"HasNote"}]}'
        )

    def test_get_sources_parameter_rules_missing_content(self):
        """Test rules parameter missing request content."""
        check_resource_missing(self, TEST_URL + '?rules={"rules":[{"name":"Bree"}]}')

    def test_get_sources_parameter_rules_expected_response_single_rule(self):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]}]}',
        )
        self.assertEqual(
            rv[0]["title"], "Baptize registry 1850 - 1867 Great Falls Church"
        )

    def test_get_sources_parameter_rules_expected_response_multiple_rules(self):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        self.assertEqual(len(rv), 0)

    def test_get_sources_parameter_rules_expected_response_or_function(self):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"function":"or","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        self.assertEqual(len(rv), 2)

    def test_get_sources_parameter_rules_expected_response_one_function(self):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"function":"one","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        self.assertEqual(len(rv), 2)

    def test_get_sources_parameter_rules_expected_response_invert(self):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            self,
            TEST_URL
            + '?rules={"invert":true,"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]}]}',
        )
        self.assertEqual(len(rv), 3)

    def test_get_sources_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?extend", check="list")

    def test_get_sources_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=S0000",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_sources_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=S0000", "note_list", "notes", join="&"
        )

    def test_get_sources_parameter_extend_expected_result_reporef_list(self):
        """Test extend reporef_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "?gramps_id=S0000",
            "reporef_list",
            "repositories",
            join="&",
            reference=True,
        )

    def test_get_sources_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=S0000", "tag_list", "tags", join="&"
        )

    def test_get_sources_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "?gramps_id=S0000&extend=all&keys=extended")
        self.assertEqual(len(rv[0]["extended"]), 4)
        for key in ["media", "notes", "repositories", "tags"]:
            self.assertIn(key, rv[0]["extended"])

    def test_get_sources_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "?gramps_id=S0000&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv[0]["extended"]), 2)
        self.assertIn("notes", rv[0]["extended"])
        self.assertIn("tags", rv[0]["extended"])

    def test_get_sources_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?backlinks", check="boolean")

    def test_get_sources_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_success(
            self, TEST_URL + "?gramps_id=S0000&keys=backlinks&backlinks=1"
        )
        self.assertIn("c140d2362f25a92643b", rv[0]["backlinks"]["citation"])


class TestSourcesHandle(unittest.TestCase):
    """Test cases for the /api/sources/{handle} endpoint for a specific source."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_sources_handle_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "X5TJQC9JXU4RKT6VAX")

    def test_get_sources_handle_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "X5TJQC9JXU4RKT6VAX?extend=all&profile=all&backlinks=1",
            "Source",
        )

    def test_get_sources_handle_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist")

    def test_get_sources_handle_expected_result(self):
        """Test response for specific source."""
        rv = check_success(self, "/api/sources/X5TJQC9JXU4RKT6VAX")
        self.assertEqual(rv["gramps_id"], "S0003")
        self.assertEqual(rv["title"], "Import from test2.ged")

    def test_get_sources_handle_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "X5TJQC9JXU4RKT6VAX?junk_parm=1")

    def test_get_sources_handle_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?strip", check="boolean"
        )

    def test_get_sources_handle_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "X5TJQC9JXU4RKT6VAX")

    def test_get_sources_handle_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?keys", check="base"
        )

    def test_get_sources_handle_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX", ["abbrev", "handle", "title"]
        )

    def test_get_sources_handle_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            [",".join(["abbrev", "handle", "title"])],
        )

    def test_get_sources_handle_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?skipkeys", check="base"
        )

    def test_get_sources_handle_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX", ["abbrev", "handle", "title"]
        )

    def test_get_sources_handle_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            [",".join(["abbrev", "handle", "title"])],
        )

    def test_get_sources_handle_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?extend", check="list"
        )

    def test_get_sources_handle_parameter_extend_expected_result_media_list(self):
        """Test extend media_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX", "media_list", "media", reference=True
        )

    def test_get_sources_handle_parameter_extend_expected_result_notes(self):
        """Test extend notes result."""
        check_single_extend_parameter(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX", "note_list", "notes"
        )

    def test_get_sources_handle_parameter_extend_expected_result_reporef_list(self):
        """Test extend reporef_list result."""
        check_single_extend_parameter(
            self,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            "reporef_list",
            "repositories",
            reference=True,
        )

    def test_get_sources_handle_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX", "tag_list", "tags"
        )

    def test_get_sources_handle_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?extend=all&keys=extended"
        )
        self.assertEqual(len(rv["extended"]), 4)
        for key in ["media", "notes", "repositories", "tags"]:
            self.assertIn(key, rv["extended"])

    def test_get_sources_handle_parameter_extend_expected_result_multiple_keys(self):
        """Test extend result for multiple keys."""
        rv = check_success(
            self,
            TEST_URL
            + "X5TJQC9JXU4RKT6VAX?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        self.assertEqual(len(rv["extended"]), 2)
        self.assertIn("notes", rv["extended"])
        self.assertIn("tags", rv["extended"])

    def test_get_sources_handle_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?backlinks", check="boolean"
        )

    def test_get_sources_handle_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(self, TEST_URL + "X5TJQC9JXU4RKT6VAX", "backlinks")
        for key in ["c140d245c0670fd78f6", "c140d2461ca544883b5"]:
            self.assertIn(key, rv["backlinks"]["citation"])

    def test_get_sources_handle_parameter_backlinks_expected_results_extended(self):
        """Test backlinks extended result."""
        rv = check_success(
            self, TEST_URL + "X5TJQC9JXU4RKT6VAX?backlinks=1&extend=backlinks"
        )
        self.assertIn("backlinks", rv)
        self.assertIn("extended", rv)
        self.assertIn("backlinks", rv["extended"])
        self.assertEqual(
            "c140d245c0670fd78f6", rv["extended"]["backlinks"]["citation"][0]["handle"]
        )
