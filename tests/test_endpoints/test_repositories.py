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

"""Tests for the /api/repositories endpoints using example_gramps."""


from tests.test_endpoints import BASE_URL, get_object_count, get_test_client

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

TEST_URL = BASE_URL + "/repositories/"


class TestRepositories:
    """Test cases for the /api/repositories endpoint for a list of repositories."""

    @classmethod
    def test_get_repositories_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_repositories_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Repository"
        )

    def test_get_repositories_expected_results_total(self, test_adapter):
        """Test expected number of results returned."""
        check_totals(test_adapter, TEST_URL + "?keys=handle", get_object_count("repositories"))

    def test_get_repositories_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "R0002"
        assert rv[0]["handle"] == "a701e99f93e5434f6f3"
        assert rv[0]["type"] == "Library"
        # check last expected record
        assert rv[-1]["gramps_id"] == "R0000"
        assert rv[-1]["handle"] == "b39fe38593f3f8c4f12"
        assert rv[-1]["type"] == "Library"

    def test_get_repositories_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_repositories_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_repositories_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_repositories_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=R0003")
        assert len(rv) == 1
        assert rv[0]["handle"] == "a701ead12841521cd4d"

    def test_get_repositories_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_repositories_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_repositories_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_repositories_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["address_list", "handle", "urls"])

    def test_get_repositories_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, [",".join(["address_list", "handle", "urls"])]
        )

    def test_get_repositories_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_repositories_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(test_adapter, TEST_URL, ["address_list", "handle", "urls"])

    def test_get_repositories_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["address_list", "handle", "urls"])]
        )

    def test_get_repositories_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_repositories_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_repositories_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 1, join="&")

    def test_get_repositories_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_repositories_parameter_sort_change_ascending_expected_result(self, test_adapter):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_repositories_parameter_sort_change_descending_expected_result(self, test_adapter):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_repositories_parameter_sort_gramps_id_ascending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "R0000"
        assert rv[-1]["gramps_id"] == "R0003"

    def test_get_repositories_parameter_sort_gramps_id_descending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "R0003"
        assert rv[-1]["gramps_id"] == "R0000"

    def test_get_repositories_parameter_sort_name_ascending_expected_result(self, test_adapter):
        """Test sort parameter name ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "name")
        assert rv[0]["name"] == "Aunt Martha's Attic"
        assert rv[-1]["name"] == "Public Library Great Falls"

    def test_get_repositories_parameter_sort_name_descending_expected_result(self, test_adapter):
        """Test sort parameter name descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "name", direction="-")
        assert rv[0]["name"] == "Public Library Great Falls"
        assert rv[-1]["name"] == "Aunt Martha's Attic"

    def test_get_repositories_parameter_sort_private_ascending_expected_result(self, test_adapter):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_repositories_parameter_sort_private_descending_expected_result(self, test_adapter):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_repositories_parameter_sort_type_ascending_expected_result(self, test_adapter):
        """Test sort parameter type ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type")

    def test_get_repositories_parameter_sort_type_descending_expected_result(self, test_adapter):
        """Test sort parameter type descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type", direction="-")

    def test_get_repositories_parameter_sort_type_ascending_expected_result_with_locale(self, test_adapter,
    ):
        """Test sort parameter type ascending result using different locale."""
        rv = check_success(test_adapter, TEST_URL + "?keys=type&sort=+type&locale=de")
        assert rv[0]["type"] == "Library"
        assert rv[-1]["type"] == "Collection"

    def test_get_repositories_parameter_sort_type_descending_expected_result_with_locale(self, test_adapter,
    ):
        """Test sort parameter type descending result using different locale."""
        rv = check_success(test_adapter, TEST_URL + "?keys=type&sort=-type&locale=de")
        assert rv[0]["type"] == "Collection"
        assert rv[-1]["type"] == "Library"

    def test_get_repositories_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_repositories_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_repositories_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            test_adapter, TEST_URL + '?rules={"rules"[{"name":"HasTag","values":["None"]}]}'
        )

    def test_get_repositories_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + '?rules={"some":"where","rules":[{"name":"HasTag","values":["None"]}]}',
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + '?rules={"function":"none","rules":[{"name":"HasTag","values":["None"]}]}',
        )

    def test_get_repositories_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(test_adapter, TEST_URL + '?rules={"rules":[{"name":"Bag End"}]}')

    def test_get_repositories_parameter_rules_expected_response_single_rule(self, test_adapter):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=type&rules={"rules":[{"name":"MatchesNameSubstringOf","values":["Library"]}]}',
        )
        for item in rv:
            assert item["type"] == "Library"

    def test_get_repositories_parameter_rules_expected_response_multiple_rules(self, test_adapter):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"rules":[{"name":"MatchesNameSubstringOf","values":["Library"]},{"name":"MatchesNameSubstringOf","values":["Attic"]}]}',
        )
        assert len(rv) == 0

    def test_get_repositories_parameter_rules_expected_response_or_function(self, test_adapter):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"function":"or","rules":[{"name":"MatchesNameSubstringOf","values":["Library"]},{"name":"MatchesNameSubstringOf","values":["Attic"]}]}',
        )
        assert len(rv) == 3

    def test_get_repositories_parameter_rules_expected_response_one_function(self, test_adapter):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"function":"one","rules":[{"name":"MatchesNameSubstringOf","values":["Library"]},{"name":"MatchesNameSubstringOf","values":["Attic"]}]}',
        )
        assert len(rv) == 3

    def test_get_repositories_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"invert":true,"rules":[{"name":"MatchesNameSubstringOf","values":["Attic"]}]}',
        )
        assert len(rv) == 2

    def test_get_repositories_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_repositories_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=R0003", "note_list", "notes", join="&"
        )

    def test_get_repositories_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=R0003", "tag_list", "tags", join="&"
        )

    def test_get_repositories_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=R0003&extend=all&keys=extended")
        assert len(rv[0]["extended"]) == 2
        for key in ["notes", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_repositories_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "?gramps_id=R0003&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_repositories_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_repositories_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(test_adapter, TEST_URL + "?page=1", "backlinks", join="&")
        assert "X5TJQC9JXU4RKT6VAX" in rv[0]["backlinks"]["source"]


class TestRepositoriesHandle:
    """Test cases for the /api/repositories/{handle} endpoint for a repository."""

    @classmethod
    def test_get_repositories_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "b39fe38593f3f8c4f12")

    def test_get_repositories_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter,
            TEST_URL + "b39fe38593f3f8c4f12?extend=all&profile=all&backlinks=1",
            "Repository",
        )

    def test_get_repositories_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_repositories_handle_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(test_adapter, TEST_URL + "b39fe38593f3f8c4f12")
        assert rv["gramps_id"] == "R0000"
        assert rv["type"] == "Library"

    def test_get_repositories_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "b39fe38593f3f8c4f12?junk_parm=1")

    def test_get_repositories_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?strip", check="boolean"
        )

    def test_get_repositories_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "b39fe38593f3f8c4f12", paginate=False)

    def test_get_repositories_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?keys", check="base"
        )

    def test_get_repositories_handle_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12", ["address_list", "handle", "type"]
        )

    def test_get_repositories_handle_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "b39fe38593f3f8c4f12",
            [",".join(["address_list", "handle", "type"])],
        )

    def test_get_repositories_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?skipkeys", check="base"
        )

    def test_get_repositories_handle_parameter_skipkeys_expected_result_single_key(self, test_adapter,
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12", ["address_list", "handle", "type"]
        )

    def test_get_repositories_handle_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "b39fe38593f3f8c4f12",
            [",".join(["address_list", "handle", "type"])],
        )

    def test_get_repositories_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?extend", check="list"
        )

    def test_get_repositories_handle_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12", "note_list", "notes"
        )

    def test_get_repositories_handle_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12", "tag_list", "tags"
        )

    def test_get_repositories_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 2
        for key in ["notes", "tags"]:
            assert key in rv["extended"]

    def test_get_repositories_handle_parameter_extend_expected_result_multiple_keys(self, test_adapter,
    ):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "b39fe38593f3f8c4f12?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_repositories_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?backlinks", check="boolean"
        )

    def test_get_repositories_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12", "backlinks"
        )
        for key in ["b39fe3f390e30bd2b99"]:
            assert key in rv["backlinks"]["source"]

    def test_get_repositories_handle_parameter_backlinks_expected_results_extended(self, test_adapter,
    ):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "b39fe38593f3f8c4f12?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["source"]:
            assert obj["handle"] in ["b39fe3f390e30bd2b99"]
