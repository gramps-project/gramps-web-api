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


class TestCitations:
    """Test cases for the /api/citations endpoint for a list of citations."""

    @classmethod
    def test_get_citations_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_citations_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Citation"
        )

    def test_get_citations_expected_results_total(self, test_adapter):
        """Test expected number of results returned."""
        check_totals(test_adapter, TEST_URL + "?keys=handle", get_object_count("citations"))

    def test_get_citations_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "C0000"
        assert rv[0]["handle"] == "c140d2362f25a92643b"
        assert rv[0]["source_handle"] == "b39fe3f390e30bd2b99"
        # check last expected record
        assert rv[-1]["gramps_id"] == "C2324"
        assert rv[-1]["handle"] == "c140d28761775ca12ba"
        assert rv[-1]["source_handle"] == "VUBKMQTA2XZG1V6QP8"

    def test_get_citations_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_citations_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_citations_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_citations_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=C2849")
        assert len(rv) == 1
        assert rv[0]["handle"] == "c140dde678c5c4f4537"
        assert rv[0]["source_handle"] == "c140d4ef77841431905"

    def test_get_citations_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_citations_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_citations_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_citations_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["attribute_list", "handle", "tag_list"])

    def test_get_citations_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_citations_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_citations_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, ["attribute_list", "handle", "tag_list"]
        )

    def test_get_citations_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_citations_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_citations_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_citations_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_citations_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_citations_parameter_sort_change_ascending_expected_result(self, test_adapter):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_citations_parameter_sort_change_descending_expected_result(self, test_adapter):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_citations_parameter_sort_confidence_ascending_expected_result(self, test_adapter):
        """Test sort parameter confidence ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "confidence")

    def test_get_citations_parameter_sort_confidence_descending_expected_result(self, test_adapter):
        """Test sort parameter confidence descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "confidence", direction="-")

    def test_get_citations_parameter_sort_date_ascending_expected_result(self, test_adapter):
        """Test sort parameter date ascending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=date&sort=+date")
        assert rv[0]["date"]["sortval"] == 0
        assert rv[-1]["date"]["sortval"] == 2447956

    def test_get_citations_parameter_sort_date_descending_expected_result(self, test_adapter):
        """Test sort parameter date descending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=date&profile=self&sort=-date")
        assert rv[0]["date"]["sortval"] == 2447956
        assert rv[-1]["date"]["sortval"] == 0

    def test_get_citations_parameter_sort_gramps_id_ascending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "C0000"
        assert rv[-1]["gramps_id"] == "C2853"

    def test_get_citations_parameter_sort_gramps_id_descending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "C2853"
        assert rv[-1]["gramps_id"] == "C0000"

    def test_get_citations_parameter_sort_private_ascending_expected_result(self, test_adapter):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_citations_parameter_sort_private_descending_expected_result(self, test_adapter):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_citations_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_citations_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_citations_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(test_adapter, TEST_URL + '?rules={"rules"[{"name":"HasNote"}]}')

    def test_get_citations_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            test_adapter, TEST_URL + '?rules={"some":"where","rules":[{"name":"HasNote"}]}'
        )
        check_invalid_semantics(
            test_adapter, TEST_URL + '?rules={"function":"none","rules":[{"name":"HasNote"}]}'
        )

    def test_get_citations_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(test_adapter, TEST_URL + '?rules={"rules":[{"name":"Gondor"}]}')

    def test_get_citations_parameter_rules_expected_response_single_rule(self, test_adapter):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(test_adapter, TEST_URL + '?rules={"rules":[{"name":"HasNote"}]}')
        for key in ["ac380498bc46102e1e8", "ae13613d581506d040892f88a21"]:
            assert key in rv[0]["note_list"]

    def test_get_citations_parameter_rules_expected_response_multiple_rules(self, test_adapter):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        for key in ["ac380498bc46102e1e8", "ae13613d581506d040892f88a21"]:
            assert key in rv[0]["note_list"]

    def test_get_citations_parameter_rules_expected_response_or_function(self, test_adapter):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        assert len(rv) == 2854

    def test_get_citations_parameter_rules_expected_response_one_function(self, test_adapter):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasNote"},{"name":"HasCitation","values":["", "", 2]}]}',
        )
        assert len(rv) == 2853

    def test_get_citations_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasCitation","values":["", "", 3]}]}',
        )
        assert len(rv) == 2851

    def test_get_citations_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_citations_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "?gramps_id=C2849",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_citations_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=C2849", "note_list", "notes", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_source_handle(self, test_adapter):
        """Test extend source_handle result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=C2849", "source_handle", "source", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=C2849", "tag_list", "tags", join="&"
        )

    def test_get_citations_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=C2849&extend=all&keys=extended")
        assert len(rv[0]["extended"]) == 4
        for key in ["media", "notes", "source", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_citations_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "?gramps_id=C2849&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_citations_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_citations_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_success(test_adapter, TEST_URL + "?page=1&keys=backlinks&backlinks=1")
        assert "a5af0ecb107303354a0" in rv[0]["backlinks"]["event"]

    def test_get_citations_parameter_dates_validate_semantics(self, test_adapter):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?dates", check="list")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=/1/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900//1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/1/")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=-1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1-")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1855/1/1-1900/*/1")

    def test_get_citations_parameter_dates_expected_result(self, test_adapter):
        """Test dates parameter expected results."""
        rv = check_success(test_adapter, TEST_URL + "?dates=1855/*/*")
        assert len(rv) == 2
        rv = check_success(test_adapter, TEST_URL + "?dates=-1900/1/1")
        assert len(rv) == 2
        rv = check_success(test_adapter, TEST_URL + "?dates=1900/1/1-")
        assert len(rv) == 1
        rv = check_success(test_adapter, TEST_URL + "?dates=1855/1/1-1900/12/31")
        assert len(rv) == 2


class TestCitationsHandle:
    """Test cases for the /api/citations/{handle} endpoint for a specific citation."""

    @classmethod
    def test_get_citations_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "c140db880395cadf318")

    def test_get_citations_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter,
            TEST_URL + "c140db880395cadf318?extend=all&profile=all&backlinks=1",
            "Citation",
        )

    def test_get_citations_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_citations_handle_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(test_adapter, TEST_URL + "c140db880395cadf318")
        assert rv["gramps_id"] == "C2844"
        assert rv["source_handle"] == "c140d4ef77841431905"

    def test_get_citations_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "c140db880395cadf318?junk_parm=1")

    def test_get_citations_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "c140db880395cadf318?strip", check="boolean"
        )

    def test_get_citations_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "c140db880395cadf318", paginate=False)

    def test_get_citations_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "c140db880395cadf318?keys", check="base"
        )

    def test_get_citations_handle_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "c140db880395cadf318",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_citations_handle_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "c140db880395cadf318",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_citations_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "c140db880395cadf318?skipkeys", check="base"
        )

    def test_get_citations_handle_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "c140db880395cadf318",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_citations_handle_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "c140db880395cadf318",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_citations_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "c140db880395cadf318?extend", check="list"
        )

    def test_get_citations_handle_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "c140db880395cadf318",
            "media_list",
            "media",
            reference=True,
        )

    def test_get_citations_handle_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "c140db880395cadf318", "note_list", "notes"
        )

    def test_get_citations_handle_parameter_extend_expected_result_source_handle(self, test_adapter):
        """Test extend source_handle result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "c140db880395cadf318", "source_handle", "source"
        )

    def test_get_citations_handle_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "c140db880395cadf318", "tag_list", "tags"
        )

    def test_get_citations_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "c140db880395cadf318?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 4
        for key in ["media", "notes", "source", "tags"]:
            assert key in rv["extended"]

    def test_get_citations_handle_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "c140db880395cadf318?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_citations_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "c140db880395cadf318?backlinks", check="boolean"
        )

    def test_get_citations_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            test_adapter, TEST_URL + "c140db880395cadf318", "backlinks"
        )
        for key in ["a5af0ecb107303354a0"]:
            assert key in rv["backlinks"]["event"]

    def test_get_citations_handle_parameter_backlinks_expected_results_extended(self, test_adapter):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "c140db880395cadf318?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["event"]:
            assert obj["handle"] in ["a5af0ecb107303354a0"]
