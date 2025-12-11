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


from . import BASE_URL
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


class TestSources:
    """Test cases for the /api/sources endpoint for a list of sources."""

    @classmethod
    def test_get_sources_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_sources_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Source"
        )



    def test_get_sources_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "S0001"
        assert rv[0]["handle"] == "c140d4ef77841431905"
        assert rv[0]["title"] == "All possible citations"
        # check last expected record
        assert rv[-1]["gramps_id"] == "S0002"
        assert rv[-1]["handle"] == "VUBKMQTA2XZG1V6QP8"
        assert rv[-1]["title"] == "World of the Wierd"

    def test_get_sources_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_sources_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_sources_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_sources_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=S0000")
        assert len(rv) == 1
        assert rv[0]["handle"] == "b39fe3f390e30bd2b99"
        assert rv[0]["title"] == "Baptize registry 1850 - 1867 Great Falls Church"

    def test_get_sources_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_sources_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_sources_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_sources_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["abbrev", "handle", "title"])

    def test_get_sources_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, [",".join(["abbrev", "handle", "title"])])

    def test_get_sources_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_sources_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(test_adapter, TEST_URL, ["abbrev", "handle", "title"])

    def test_get_sources_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["abbrev", "handle", "title"])]
        )

    def test_get_sources_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_sources_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_sources_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 2, join="&")

    def test_get_sources_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_sources_parameter_sort_abbrev_ascending_expected_result(self, test_adapter):
        """Test sort parameter abbrev ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "abbrev")
        assert rv[0]["abbrev"] == ""
        assert rv[-1]["abbrev"] == "WOTW"

    def test_get_sources_parameter_sort_abbrev_descending_expected_result(self, test_adapter):
        """Test sort parameter abbrev descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "abbrev", direction="-")
        assert rv[0]["abbrev"] == "WOTW"
        assert rv[-1]["abbrev"] == ""

    def test_get_sources_parameter_sort_author_ascending_expected_result(self, test_adapter):
        """Test sort parameter author ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "author")
        assert rv[0]["author"] == ""
        assert rv[-1]["author"] == "Priests of Great Falls Church 1850 - 1867"

    def test_get_sources_parameter_sort_author_descending_expected_result(self, test_adapter):
        """Test sort parameter author descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "author", direction="-")
        assert rv[0]["author"] == "Priests of Great Falls Church 1850 - 1867"
        assert rv[-1]["author"] == ""

    def test_get_sources_parameter_sort_change_ascending_expected_result(self, test_adapter):
        """Test sort parameter change ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_sources_parameter_sort_change_descending_expected_result(self, test_adapter):
        """Test sort parameter change descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_sources_parameter_sort_gramps_id_ascending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "S0000"
        assert rv[-1]["gramps_id"] == "S0003"

    def test_get_sources_parameter_sort_gramps_id_descending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "S0003"
        assert rv[-1]["gramps_id"] == "S0000"

    def test_get_sources_parameter_sort_private_ascending_expected_result(self, test_adapter):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_sources_parameter_sort_private_descending_expected_result(self, test_adapter):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_sources_parameter_sort_pubinfo_ascending_expected_result(self, test_adapter):
        """Test sort parameter pubinfo ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "pubinfo")
        assert rv[0]["pubinfo"] == ""
        assert rv[-1]["pubinfo"] == "Microfilm Public Library Great Falls"

    def test_get_sources_parameter_sort_pubinfo_descending_expected_result(self, test_adapter):
        """Test sort parameter pubinfo descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "pubinfo", direction="-")
        assert rv[0]["pubinfo"] == "Microfilm Public Library Great Falls"
        assert rv[-1]["pubinfo"] == ""

    def test_get_sources_parameter_sort_title_ascending_expected_result(self, test_adapter):
        """Test sort parameter title ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "title")
        assert rv[0]["title"] == "All possible citations"
        assert rv[-1]["title"] == "World of the Wierd"

    def test_get_sources_parameter_sort_title_descending_expected_result(self, test_adapter):
        """Test sort parameter title descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "title", direction="-")
        assert rv[0]["title"] == "World of the Wierd"
        assert rv[-1]["title"] == "All possible citations"

    def test_get_sources_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_sources_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_sources_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(test_adapter, TEST_URL + '?rules={"rules"[{"name":"HasNote"}]}')

    def test_get_sources_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            test_adapter, TEST_URL + '?rules={"some":"where","rules":[{"name":"HasNote"}]}'
        )
        check_invalid_semantics(
            test_adapter, TEST_URL + '?rules={"function":"none","rules":[{"name":"HasNote"}]}'
        )

    def test_get_sources_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(test_adapter, TEST_URL + '?rules={"rules":[{"name":"Bree"}]}')

    def test_get_sources_parameter_rules_expected_response_single_rule(self, test_adapter):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]}]}',
        )
        assert rv[0]["title"] == "Baptize registry 1850 - 1867 Great Falls Church"

    def test_get_sources_parameter_rules_expected_response_multiple_rules(self, test_adapter):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        assert len(rv) == 0

    def test_get_sources_parameter_rules_expected_response_or_function(self, test_adapter):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"function":"or","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        assert len(rv) == 2

    def test_get_sources_parameter_rules_expected_response_one_function(self, test_adapter):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"function":"one","rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]},{"name":"MatchesTitleSubstringOf","values":["World"]}]}',
        )
        assert len(rv) == 2

    def test_get_sources_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"invert":true,"rules":[{"name":"MatchesTitleSubstringOf","values":["Church"]}]}',
        )
        assert len(rv) == 3

    def test_get_sources_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_sources_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "?gramps_id=S0000",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_sources_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=S0000", "note_list", "notes", join="&"
        )

    def test_get_sources_parameter_extend_expected_result_reporef_list(self, test_adapter):
        """Test extend reporef_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "?gramps_id=S0000",
            "reporef_list",
            "repositories",
            join="&",
            reference=True,
        )

    def test_get_sources_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=S0000", "tag_list", "tags", join="&"
        )

    def test_get_sources_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=S0000&extend=all&keys=extended")
        assert len(rv[0]["extended"]) == 4
        for key in ["media", "notes", "repositories", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_sources_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "?gramps_id=S0000&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_sources_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_sources_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_success(
            test_adapter, TEST_URL + "?gramps_id=S0000&keys=backlinks&backlinks=1"
        )
        assert "c140d2362f25a92643b" in rv[0]["backlinks"]["citation"]


class TestSourcesHandle:
    """Test cases for the /api/sources/{handle} endpoint for a specific source."""

    @classmethod
    def test_get_sources_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX")

    def test_get_sources_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter,
            TEST_URL + "X5TJQC9JXU4RKT6VAX?extend=all&profile=all&backlinks=1",
            "Source",
        )

    def test_get_sources_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_sources_handle_expected_result(self, test_adapter):
        """Test response for specific source."""
        rv = check_success(test_adapter, "/api/sources/X5TJQC9JXU4RKT6VAX")
        assert rv["gramps_id"] == "S0003"
        assert rv["title"] == "Import from test2.ged"

    def test_get_sources_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?junk_parm=1")

    def test_get_sources_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?strip", check="boolean"
        )

    def test_get_sources_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", paginate=False)

    def test_get_sources_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?keys", check="base"
        )

    def test_get_sources_handle_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", ["abbrev", "handle", "title"]
        )

    def test_get_sources_handle_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            [",".join(["abbrev", "handle", "title"])],
        )

    def test_get_sources_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?skipkeys", check="base"
        )

    def test_get_sources_handle_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", ["abbrev", "handle", "title"]
        )

    def test_get_sources_handle_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            [",".join(["abbrev", "handle", "title"])],
        )

    def test_get_sources_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?extend", check="list"
        )

    def test_get_sources_handle_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", "media_list", "media", reference=True
        )

    def test_get_sources_handle_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", "note_list", "notes"
        )

    def test_get_sources_handle_parameter_extend_expected_result_reporef_list(self, test_adapter):
        """Test extend reporef_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "X5TJQC9JXU4RKT6VAX",
            "reporef_list",
            "repositories",
            reference=True,
        )

    def test_get_sources_handle_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", "tag_list", "tags"
        )

    def test_get_sources_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 4
        for key in ["media", "notes", "repositories", "tags"]:
            assert key in rv["extended"]

    def test_get_sources_handle_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "X5TJQC9JXU4RKT6VAX?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_sources_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?backlinks", check="boolean"
        )

    def test_get_sources_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX", "backlinks")
        for key in ["c140d245c0670fd78f6", "c140d2461ca544883b5"]:
            assert key in rv["backlinks"]["citation"]

    def test_get_sources_handle_parameter_backlinks_expected_results_extended(self, test_adapter):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "X5TJQC9JXU4RKT6VAX?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        assert "c140d245c0670fd78f6" == rv["extended"]["backlinks"]["citation"][0]["handle"]
