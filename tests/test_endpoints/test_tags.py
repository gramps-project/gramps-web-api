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

"""Tests for the /api/tags endpoints using example_gramps."""


from . import BASE_URL
from .checks import (
    check_boolean_parameter,
    check_conforms_to_schema,
    check_invalid_semantics,
    check_keys_parameter,
    check_paging_parameters,
    check_requires_token,
    check_resource_missing,
    check_skipkeys_parameter,
    check_sort_parameter,
    check_strip_parameter,
    check_success,
    check_totals,
)

TEST_URL = BASE_URL + "/tags/"


class TestTags:
    """Test cases for the /api/tags endpoint for a list of tags."""

    @classmethod
    def test_get_tags_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_tags_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL, "Tag")

    def test_get_tags_expected_results_total(self, test_adapter, example_object_counts):
        """Test expected number of results returned."""
        check_totals(test_adapter, TEST_URL, example_object_counts["tags"])

    def test_get_tags_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["handle"] == "bb80c229eef1ee1a3ec"
        # check last expected record
        assert rv[-1]["handle"] == "bb80c2b235b0a1b3f49"

    def test_get_tags_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_tags_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_tags_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_tags_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_tags_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["change", "handle", "priority"])

    def test_get_tags_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, [",".join(["change", "handle", "priority"])]
        )

    def test_get_tags_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_tags_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, ["change", "handle", "priority"]
        )

    def test_get_tags_parameter_skipkeys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["change", "handle", "priority"])]
        )

    def test_get_tags_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_tags_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_tags_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 1, join="&")

    def test_get_tags_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_tags_parameter_sort_change_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_tags_parameter_sort_change_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_tags_parameter_sort_name_ascending_expected_result(self, test_adapter):
        """Test sort parameter name ascending result."""
        rv = check_success(test_adapter, TEST_URL + "?sort=name&keys=name")
        assert rv[0]["name"] == "complete"
        assert rv[-1]["name"] == "ToDo"

    def test_get_tags_parameter_sort_name_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter name descending result."""
        rv = check_success(test_adapter, TEST_URL + "?sort=-name&keys=name")
        assert rv[0]["name"] == "ToDo"
        assert rv[-1]["name"] == "complete"

    def test_get_tags_parameter_sort_color_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter color ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "color")

    def test_get_tags_parameter_sort_color_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter color descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "color", direction="-")

    def test_get_tags_parameter_sort_priority_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter priority ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "priority")

    def test_get_tags_parameter_sort_priority_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter priority descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "priority", direction="-")

    def test_get_tags_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_tags_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_success(
            test_adapter, TEST_URL + "?page=1&keys=backlinks&backlinks=1"
        )
        assert "JF5KQC2L6ABI0MVD3E" in rv[0]["backlinks"]["person"]


class TestTagsHandle:
    """Test cases for the /api/tags/{handle} endpoint for a tag."""

    @classmethod
    def test_get_tags_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "bb80c2b235b0a1b3f49")

    def test_get_tags_handle_conforms_to_schema(self, test_adapter):
        """Test confors to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL + "bb80c2b235b0a1b3f49", "Tag")

    def test_get_tags_handle_missing_content(self, test_adapter):
        """Test response for missing handle."""
        check_resource_missing(test_adapter, TEST_URL + "missing")

    def test_get_tags_handle_expected_result(self, test_adapter):
        """Test expected result returned."""
        rv = check_success(test_adapter, TEST_URL + "bb80c2b235b0a1b3f49")
        assert rv["name"] == "ToDo"

    def test_get_tags_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?junk=1")

    def test_get_tags_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?strip", check="boolean"
        )

    def test_get_tags_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49", paginate=False
        )

    def test_get_tags_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?keys", check="base"
        )

    def test_get_tags_handle_parameter_keys_expected_result_single_key(
        self, test_adapter
    ):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "bb80c2b235b0a1b3f49",
            ["change", "handle", "priority"],
        )

    def test_get_tags_handle_parameter_keys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "bb80c2b235b0a1b3f49",
            [",".join(["change", "handle", "priority"])],
        )

    def test_get_tags_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?skipkeys", check="base"
        )

    def test_get_tags_handle_parameter_skipkeys_expected_result_single_key(
        self, test_adapter
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "bb80c2b235b0a1b3f49",
            ["change", "handle", "priority"],
        )

    def test_get_tags_handle_parameter_skipkeys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "bb80c2b235b0a1b3f49",
            [",".join(["change", "handle", "priority"])],
        )

    def test_get_tags_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?backlinks", check="boolean"
        )

    def test_get_tags_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49", "backlinks"
        )
        for key in ["b39ff01f75c1f76859a", "b39fe2e143d1e599450"]:
            assert key in rv["backlinks"]["note"]

    def test_get_tags_handle_parameter_backlinks_expected_results_extended(
        self, test_adapter
    ):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "bb80c2b235b0a1b3f49?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["person"]:
            assert obj["handle"] in ["GNUJQCL9MD64AM56OH"]
