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

"""Tests for the /api/media endpoints using example_gramps."""


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

TEST_URL = BASE_URL + "/media/"


class TestMedia:
    """Test cases for the /api/media endpoint for a list of media."""

    @classmethod
    def test_get_media_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_media_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Media"
        )



    def test_get_media_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "O0000"
        assert rv[0]["handle"] == "b39fe1cfc1305ac4a21"
        # check last expected record
        assert rv[-1]["gramps_id"] == "O0009"
        assert rv[-1]["handle"] == "78V2GQX2FKNSYQ3OHE"

    def test_get_media_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_media_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_media_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_media_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=O0006")
        assert len(rv) == 1
        assert rv[0]["handle"] == "F0QIGQFT275JFJ75E8"
        assert rv[0]["path"] == "Alimehemet.jpg"

    def test_get_media_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_media_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_media_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_media_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["attribute_list", "handle", "tag_list"])

    def test_get_media_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_media_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_media_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, ["attribute_list", "handle", "tag_list"]
        )

    def test_get_media_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "tag_list"])]
        )

    def test_get_media_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_media_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_media_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 3, join="&")

    def test_get_media_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_media_parameter_sort_change_ascending_expected_result(self, test_adapter):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_media_parameter_sort_change_descending_expected_result(self, test_adapter):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_media_parameter_sort_date_ascending_expected_result(self, test_adapter):
        """Test sort parameter date ascending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=handle&sort=+date")
        assert rv[0]["handle"] == "b39fe1cfc1305ac4a21"
        assert rv[-1]["handle"] == "238CGQ939HG18SS5MG"

    def test_get_media_parameter_sort_date_descending_expected_result(self, test_adapter):
        """Test sort parameter date descending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=handle&sort=-date")
        assert rv[0]["handle"] == "238CGQ939HG18SS5MG"
        assert rv[-1]["handle"] == "78V2GQX2FKNSYQ3OHE"

    def test_get_media_parameter_sort_gramps_id_ascending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "O0000"
        assert rv[-1]["gramps_id"] == "O0011"

    def test_get_media_parameter_sort_gramps_id_descending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "O0011"
        assert rv[-1]["gramps_id"] == "O0000"

    def test_get_media_parameter_sort_mime_ascending_expected_result(self, test_adapter):
        """Test sort parameter mime ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "mime")

    def test_get_media_parameter_sort_mime_descending_expected_result(self, test_adapter):
        """Test sort parameter mime descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "mime", direction="-")

    def test_get_media_parameter_sort_path_ascending_expected_result(self, test_adapter):
        """Test sort parameter path ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "path")

    def test_get_media_parameter_sort_path_descending_expected_result(self, test_adapter):
        """Test sort parameter path descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "path", direction="-")

    def test_get_media_parameter_sort_private_ascending_expected_result(self, test_adapter):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_media_parameter_sort_private_descending_expected_result(self, test_adapter):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_media_parameter_sort_title_ascending_expected_result(self, test_adapter):
        """Test sort parameter title ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "title", value_key="desc")

    def test_get_media_parameter_sort_title_descending_expected_result(self, test_adapter):
        """Test sort parameter title descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "title", value_key="desc", direction="-")

    def test_get_media_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_media_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_media_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            test_adapter, TEST_URL + '?rules={"rules"[{"name":"MediaPrivate"}]}'
        )

    def test_get_media_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            test_adapter, TEST_URL + '?rules={"some":"where","rules":[{"name":"MediaPrivate"}]}'
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL + '?rules={"function":"none","rules":[{"name":"MediaPrivate"}]}',
        )

    def test_get_media_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(
            test_adapter, TEST_URL + '?rules={"rules":[{"name":"Rivendell"}]}'
        )

    def test_get_media_parameter_rules_expected_response_single_rule(self, test_adapter):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=tag_list&rules={"rules":[{"name":"HasTag","values":["ToDo"]}]}',
        )
        assert "bb80c2b235b0a1b3f49" in rv[0]["tag_list"]

    def test_get_media_parameter_rules_expected_response_multiple_rules(self, test_adapter):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"rules":[{"name":"HasTag","values":["ToDo"]},{"name":"MediaPrivate"}]}',
        )
        assert len(rv) == 0

    def test_get_media_parameter_rules_expected_response_or_function(self, test_adapter):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasTag","values":["ToDo"]},{"name":"HasIdOf","values":["O0007"]}]}',
        )
        assert rv[0]["handle"] == "238CGQ939HG18SS5MG"
        assert rv[1]["handle"] == "F8JYGQFL2PKLSYH79X"

    def test_get_media_parameter_rules_expected_response_one_function(self, test_adapter):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasTag","values":["ToDo"]},{"name":"HasIdOf","values":["O0007"]}]}',
        )
        assert len(rv) == 2

    def test_get_media_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"MediaPrivate"}]}',
        )
        assert len(rv) == 7

    def test_get_media_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_media_parameter_extend_expected_result_citation_list(self, test_adapter):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=O0006", "citation_list", "citations", join="&"
        )

    def test_get_media_parameter_extend_expected_result_note_list(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=O0006", "note_list", "notes", join="&"
        )

    def test_get_media_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=O0006", "tag_list", "tags", join="&"
        )

    def test_get_media_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=O0006&extend=all&keys=extended")
        assert len(rv[0]["extended"]) == 3
        for key in ["citations", "notes", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_media_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "?gramps_id=O0006&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_media_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_media_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_success(
            test_adapter, TEST_URL + "?gramps_id=O0006&keys=backlinks&backlinks=1"
        )
        assert "9OUJQCBOHW9UEK9CNV" in rv[0]["backlinks"]["family"]

    def test_get_media_parameter_dates_validate_semantics(self, test_adapter):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?dates", check="list")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=/1/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900//1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/1/")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=-1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1-")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1855/1/1-1900/*/1")

    def test_get_media_parameter_dates_expected_result(self, test_adapter):
        """Test dates parameter expected results."""
        rv = check_success(test_adapter, TEST_URL + "?dates=1897/*/*")
        assert len(rv) == 1
        rv = check_success(test_adapter, TEST_URL + "?dates=-1900/1/1")
        assert len(rv) == 1
        rv = check_success(test_adapter, TEST_URL + "?dates=1900/1/1-")
        assert len(rv) == 0
        rv = check_success(test_adapter, TEST_URL + "?dates=1855/1/1-1900/12/31")
        assert len(rv) == 1


class TestMediaHandle:
    """Test cases for the /api/media/{handle} endpoint for specific media."""

    @classmethod
    def test_get_media_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM")

    def test_get_media_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter,
            TEST_URL + "B1AUFQV7H8R9NR4SZM?extend=all&profile=all&backlinks=1",
            "Media",
        )

    def test_get_media_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_media_handle_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM")
        assert rv["gramps_id"] == "O0008"

    def test_get_media_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?junk_parm=1")

    def test_get_media_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?strip", check="boolean"
        )

    def test_get_media_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM", paginate=False)

    def test_get_media_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?keys", check="base"
        )

    def test_get_media_handle_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "B1AUFQV7H8R9NR4SZM",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_media_handle_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "B1AUFQV7H8R9NR4SZM",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_media_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?skipkeys", check="base"
        )

    def test_get_media_handle_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "B1AUFQV7H8R9NR4SZM",
            ["attribute_list", "handle", "tag_list"],
        )

    def test_get_media_handle_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "B1AUFQV7H8R9NR4SZM",
            [",".join(["attribute_list", "handle", "tag_list"])],
        )

    def test_get_media_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?extend", check="list"
        )

    def test_get_media_handle_parameter_extend_expected_result_citation_list(self, test_adapter):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM", "citation_list", "citations"
        )

    def test_get_media_handle_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM", "note_list", "notes"
        )

    def test_get_media_handle_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM", "tag_list", "tags"
        )

    def test_get_media_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 3
        for key in ["citations", "notes", "tags"]:
            assert key in rv["extended"]

    def test_get_media_handle_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "B1AUFQV7H8R9NR4SZM?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_media_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?backlinks", check="boolean"
        )

    def test_get_media_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM", "backlinks")
        assert "GNUJQCL9MD64AM56OH" in rv["backlinks"]["person"]

    def test_get_media_handle_parameter_backlinks_expected_results_extended(self, test_adapter):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "B1AUFQV7H8R9NR4SZM?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["person"]:
            assert obj["handle"] in ["GNUJQCL9MD64AM56OH"]
