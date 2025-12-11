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

"""Tests for the /api/events endpoints using example_gramps."""


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

TEST_URL = BASE_URL + "/events/"


class TestEvents:
    """Test cases for the /api/events endpoint for a list of events."""

    def test_get_events_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_events_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Event"
        )

    def test_get_events_expected_results_total(
        self, test_adapter, example_object_counts
    ):
        """Test expected number of results returned."""
        check_totals(
            test_adapter, TEST_URL + "?keys=handle", example_object_counts["events"]
        )

    def test_get_events_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "E0000"
        assert rv[0]["description"] == "Birth of Warner, Sarah Suzanne"
        assert rv[0]["place"] == "08TJQCCFIX31BXPNXN"
        # check last expected record
        assert rv[-1]["gramps_id"] == "E3431"
        assert rv[-1]["description"] == ""
        assert rv[-1]["place"] == ""

    def test_get_events_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_events_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_events_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_events_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=E0523")
        assert len(rv) == 1
        assert rv[0]["handle"] == "a5af0ebb51337f15e61"

    def test_get_events_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_events_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_events_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_events_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, ["attribute_list", "handle", "type"]
        )

    def test_get_events_parameter_keys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "type"])]
        )

    def test_get_events_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_events_parameter_skipkeys_expected_result_single_key(
        self, test_adapter
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, ["attribute_list", "handle", "type"]
        )

    def test_get_events_parameter_skipkeys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL, [",".join(["attribute_list", "handle", "type"])]
        )

    def test_get_events_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_events_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_events_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_events_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_events_parameter_sort_change_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_events_parameter_sort_change_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_events_parameter_sort_date_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter date ascending result."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=+date"
        )
        assert rv[0]["profile"]["date"] == ""
        assert rv[-1]["profile"]["date"] == "2006-01-11"

    def test_get_events_parameter_sort_date_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter date descending result."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=-date"
        )
        assert rv[0]["profile"]["date"] == "2006-01-11"
        assert rv[-1]["profile"]["date"] == ""

    def test_get_events_parameter_sort_gramps_id_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "E0000"
        assert rv[-1]["gramps_id"] == "E3431"

    def test_get_events_parameter_sort_gramps_id_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "E3431"
        assert rv[-1]["gramps_id"] == "E0000"

    def test_get_events_parameter_sort_place_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter place ascending result."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=+place"
        )
        assert rv[0]["profile"]["place"] == ""
        assert rv[-1]["profile"]["place"] == "Σιάτιστα, Greece"

    def test_get_events_parameter_sort_place_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter place descending result."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=-place"
        )
        assert rv[0]["profile"]["place"] == "Σιάτιστα, Greece"
        assert rv[-1]["profile"]["place"] == ""

    def test_get_events_parameter_sort_private_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_events_parameter_sort_private_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_events_parameter_sort_type_ascending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter type ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type")

    def test_get_events_parameter_sort_type_descending_expected_result(
        self, test_adapter
    ):
        """Test sort parameter type descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type", direction="-")

    def test_get_events_parameter_sort_type_ascending_expected_result_with_locale(
        self, test_adapter
    ):
        """Test sort parameter type ascending result using different locale."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=+type&locale=de"
        )
        assert rv[0]["profile"]["type"] == "Beerdigung"
        assert rv[-1]["profile"]["type"] == "Tod"

    def test_get_events_parameter_sort_type_descending_expected_result_with_locale(
        self, test_adapter
    ):
        """Test sort parameter type descending result using different locale."""
        rv = check_success(
            test_adapter, TEST_URL + "?keys=profile&profile=self&sort=-type&locale=de"
        )
        assert rv[0]["profile"]["type"] == "Tod"
        assert rv[-1]["profile"]["type"] == "Beerdigung"

    def test_get_events_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_events_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(
            test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee"
        )

    def test_get_events_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            test_adapter,
            TEST_URL + '?rules={"rules"[{"name":"HasType","values":["Marriage"]}]}',
        )

    def test_get_events_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + '?rules={"some":"where","rules":[{"name":"HasType","values":["Marriage"]}]}',
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + '?rules={"function":"none","rules":[{"name":"HasType","values":["Marriage"]}]}',
        )

    def test_get_events_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(
            test_adapter, TEST_URL + '?rules={"rules":[{"name":"Rohan"}]}'
        )

    def test_get_events_parameter_rules_expected_response_single_rule(
        self, test_adapter
    ):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=type&rules={"rules":[{"name":"HasType","values":["Marriage"]}]}',
        )
        for item in rv:
            assert item["type"] == "Marriage"

    def test_get_events_parameter_rules_expected_response_multiple_rules(
        self, test_adapter
    ):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?rules={"rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
        )
        assert len(rv) == 1
        assert rv[0]["type"] == "Death"
        assert rv[0]["note_list"][0] == "b39feeac1a202b44e76"

    def test_get_events_parameter_rules_expected_response_or_function(
        self, test_adapter
    ):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
        )
        assert len(rv) == 657

    def test_get_events_parameter_rules_expected_response_one_function(
        self, test_adapter
    ):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasType","values":["Death"]},{"name":"HasNote"}]}',
        )
        assert len(rv) == 656

    def test_get_events_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasType","values":["Married"]}]}',
        )
        assert len(rv) == 3432

    def test_get_events_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_events_parameter_extend_expected_result_citation_list(
        self, test_adapter
    ):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "?gramps_id=E0341",
            "citation_list",
            "citations",
            join="&",
        )

    def test_get_events_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "?gramps_id=E0341",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_events_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=E0341", "note_list", "notes", join="&"
        )

    def test_get_events_parameter_extend_expected_result_place(self, test_adapter):
        """Test extend place result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=E0341", "place", "place", join="&"
        )

    def test_get_events_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "?gramps_id=E0341", "tag_list", "tags", join="&"
        )

    def test_get_events_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "?gramps_id=E0341&extend=all&keys=extended"
        )
        assert len(rv[0]["extended"]) == 5
        for key in ["citations", "media", "notes", "place", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_events_parameter_extend_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "?gramps_id=E0341&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_events_parameter_profile_validate_semantics(self, test_adapter):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?profile", check="list")

    def test_get_events_parameter_profile_expected_result(self, test_adapter):
        """Test expected response."""
        rv = check_success(
            test_adapter, TEST_URL + "?page=1&pagesize=1&keys=profile&profile=all"
        )
        assert rv[0]["profile"] == {
            "citations": 0,
            "confidence": 0,
            "date": "1987-08-29",
            "place": "Gainesville, Llano, TX, USA",
            "place_name": "Gainesville",
            "type": "Birth",
            "summary": "Birth - Warner, Sarah Suzanne",
            "participants": {
                "families": [],
                "people": [
                    {
                        "person": {
                            "birth": {
                                "date": "1987-08-29",
                                "place": "Gainesville, Llano, TX, USA",
                                "place_name": "Gainesville",
                                "type": "Birth",
                                "summary": "Birth - Warner, Sarah Suzanne",
                            },
                            "death": {},
                            "gramps_id": "I0001",
                            "handle": "66TJQC6CC7ZWL9YZ64",
                            "name_display": "Warner, Sarah Suzanne",
                            "name_given": "Sarah Suzanne",
                            "name_surname": "Warner",
                            "name_suffix": "",
                            "sex": "F",
                        },
                        "role": "Primary",
                    }
                ],
            },
            "references": {
                "person": [
                    {
                        "birth": {
                            "date": "1987-08-29",
                            "place": "Gainesville, Llano, TX, USA",
                            "place_name": "Gainesville",
                            "type": "Birth",
                            "summary": "Birth - Warner, Sarah Suzanne",
                        },
                        "death": {},
                        "gramps_id": "I0001",
                        "handle": "66TJQC6CC7ZWL9YZ64",
                        "name_display": "Warner, Sarah Suzanne",
                        "name_given": "Sarah Suzanne",
                        "name_surname": "Warner",
                        "name_suffix": "",
                        "sex": "F",
                    }
                ],
            },
        }

    def test_get_events_parameter_profile_expected_result_with_locale(
        self, test_adapter
    ):
        """Test expected profile response for a locale."""
        rv = check_success(
            test_adapter, TEST_URL + "?page=1&keys=profile&profile=all&locale=de"
        )
        assert rv[0]["profile"]["type"] == "Geburt"

    def test_get_events_parameter_profile_summary_with_locale(self, test_adapter):
        """Test expected profile summary for a locale."""
        rv = check_success(
            test_adapter, TEST_URL + "?page=1&keys=profile&profile=all&locale=de"
        )
        assert rv[0]["profile"]["summary"] == "Geburt - Warner, Sarah Suzanne"

    def test_get_events_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_events_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            test_adapter, TEST_URL + "?page=1", "backlinks", join="&"
        )
        assert "66TJQC6CC7ZWL9YZ64" in rv[0]["backlinks"]["person"]

    def test_get_events_parameter_dates_validate_semantics(self, test_adapter):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?dates", check="list")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=/1/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900//1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/1/")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=-1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1900/a/1-")
        check_invalid_semantics(test_adapter, TEST_URL + "?dates=1855/1/1-1900/*/1")

    def test_get_events_parameter_dates_expected_result(self, test_adapter):
        """Test dates parameter expected results."""
        rv = check_success(test_adapter, TEST_URL + "?dates=*/1/1")
        assert len(rv) == 8
        rv = check_success(test_adapter, TEST_URL + "?dates=-1855/1/1")
        assert len(rv) == 933
        rv = check_success(test_adapter, TEST_URL + "?dates=1855/1/1-")
        assert len(rv) == 1203
        rv = check_success(test_adapter, TEST_URL + "?dates=1855/1/1-1900/12/31")
        assert len(rv) == 300


class TestEventsHandle:
    """Test cases for the /api/events/{handle} endpoint for a specific event."""

    def test_get_events_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "a5af0eb6dd140de132c")

    def test_get_events_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c?extend=all&profile=all&backlinks=1",
            "Event",
        )

    def test_get_events_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_events_handle_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(test_adapter, TEST_URL + "a5af0eb6dd140de132c")
        assert rv["gramps_id"] == "E0043"
        assert rv["place"] == "P4EKQC5TG9HPIOXHN2"

    def test_get_events_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?junk_parm=1"
        )

    def test_get_events_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?strip", check="boolean"
        )

    def test_get_events_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", paginate=False
        )

    def test_get_events_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?keys", check="base"
        )

    def test_get_events_handle_parameter_keys_expected_result_single_key(
        self, test_adapter
    ):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c",
            ["attribute_list", "handle", "type"],
        )

    def test_get_events_handle_parameter_keys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c",
            [",".join(["attribute_list", "handle", "type"])],
        )

    def test_get_events_handle_parameter_skipkeys_validate_semantics(
        self, test_adapter
    ):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?skipkeys", check="base"
        )

    def test_get_events_handle_parameter_skipkeys_expected_result_single_key(
        self, test_adapter
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c",
            ["attribute_list", "handle", "type"],
        )

    def test_get_events_handle_parameter_skipkeys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c",
            [",".join(["attribute_list", "handle", "type"])],
        )

    def test_get_events_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?extend", check="list"
        )

    def test_get_events_handle_parameter_extend_expected_result_citation_list(
        self, test_adapter
    ):
        """Test extend citation_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", "citation_list", "citations"
        )

    def test_get_events_handle_parameter_extend_expected_result_media_list(
        self, test_adapter
    ):
        """Test extend media_list result."""
        check_single_extend_parameter(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c",
            "media_list",
            "media",
            reference=True,
        )

    def test_get_events_handle_parameter_extend_expected_result_notes(
        self, test_adapter
    ):
        """Test extend notes result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", "note_list", "notes"
        )

    def test_get_events_handle_parameter_extend_expected_result_place(
        self, test_adapter
    ):
        """Test extend place result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", "place", "place"
        )

    def test_get_events_handle_parameter_extend_expected_result_tag_list(
        self, test_adapter
    ):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", "tag_list", "tags"
        )

    def test_get_events_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 5
        for key in ["citations", "media", "notes", "place", "tags"]:
            assert key in rv["extended"]

    def test_get_events_handle_parameter_extend_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test extend result for multiple keys."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + "a5af0eb6dd140de132c?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_events_handle_parameter_profile_validate_semantics(self, test_adapter):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?profile", check="list"
        )

    def test_get_events_handle_parameter_profile_expected_result(self, test_adapter):
        """Test response as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?keys=profile&profile=all"
        )
        assert rv["profile"] == {
            "citations": 0,
            "confidence": 0,
            "date": "1250",
            "place": "Atchison, Atchison, KS, USA",
            "place_name": "Atchison",
            "type": "Birth",
            "summary": "Birth - Knudsen, Ralph",
            "participants": {
                "families": [],
                "people": [
                    {
                        "person": {
                            "birth": {
                                "date": "1250",
                                "place": "Atchison, Atchison, KS, USA",
                                "place_name": "Atchison",
                                "type": "Birth",
                                "summary": "Birth - Knudsen, Ralph",
                            },
                            "death": {
                                "date": "1316",
                                "place": "",
                                "place_name": "",
                                "type": "Death",
                                "summary": "Death - Knudsen, Ralph",
                            },
                            "gramps_id": "I1020",
                            "handle": "H4EKQCFV3436HSKY2D",
                            "name_display": "Knudsen, Ralph",
                            "name_given": "Ralph",
                            "name_surname": "Knudsen",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        "role": "Primary",
                    }
                ],
            },
            "references": {
                "person": [
                    {
                        "birth": {
                            "date": "1250",
                            "place": "Atchison, Atchison, KS, USA",
                            "place_name": "Atchison",
                            "type": "Birth",
                            "summary": "Birth - Knudsen, Ralph",
                        },
                        "death": {
                            "date": "1316",
                            "place": "",
                            "place_name": "",
                            "type": "Death",
                            "summary": "Death - Knudsen, Ralph",
                        },
                        "gramps_id": "I1020",
                        "handle": "H4EKQCFV3436HSKY2D",
                        "name_display": "Knudsen, Ralph",
                        "name_given": "Ralph",
                        "name_surname": "Knudsen",
                        "name_suffix": "",
                        "sex": "M",
                    }
                ],
            },
        }

    def test_get_events_handle_parameter_profile_expected_result_with_locale(
        self, test_adapter
    ):
        """Test response as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?profile=all&locale=de"
        )
        assert rv["profile"] == {
            "citations": 0,
            "confidence": 0,
            "date": "1250",
            "place": "Atchison, Atchison, KS, USA",
            "place_name": "Atchison",
            "type": "Geburt",
            "summary": "Geburt - Knudsen, Ralph",
            "participants": {
                "families": [],
                "people": [
                    {
                        "person": {
                            "birth": {
                                "date": "1250",
                                "place": "Atchison, Atchison, KS, USA",
                                "place_name": "Atchison",
                                "type": "Geburt",
                                "summary": "Geburt - Knudsen, Ralph",
                            },
                            "death": {
                                "date": "1316",
                                "place": "",
                                "place_name": "",
                                "type": "Tod",
                                "summary": "Tod - Knudsen, Ralph",
                            },
                            "gramps_id": "I1020",
                            "handle": "H4EKQCFV3436HSKY2D",
                            "name_display": "Knudsen, Ralph",
                            "name_given": "Ralph",
                            "name_surname": "Knudsen",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        "role": "Primär",
                    }
                ],
            },
            "references": {
                "person": [
                    {
                        "birth": {
                            "date": "1250",
                            "place": "Atchison, Atchison, KS, USA",
                            "place_name": "Atchison",
                            "type": "Geburt",
                            "summary": "Geburt - Knudsen, Ralph",
                        },
                        "death": {
                            "date": "1316",
                            "place": "",
                            "place_name": "",
                            "type": "Tod",
                            "summary": "Tod - Knudsen, Ralph",
                        },
                        "gramps_id": "I1020",
                        "handle": "H4EKQCFV3436HSKY2D",
                        "name_display": "Knudsen, Ralph",
                        "name_given": "Ralph",
                        "name_surname": "Knudsen",
                        "name_suffix": "",
                        "sex": "M",
                    }
                ],
            },
        }

    def test_get_events_handle_parameter_profile_expected_result_with_name_format(
        self, test_adapter
    ):
        """Test response as expected."""
        rv = check_success(
            test_adapter,
            TEST_URL + "a5af0eb6dd140de132c?profile=all&name_format=%25f%20%25M",
        )
        assert rv["profile"] == {
            "citations": 0,
            "confidence": 0,
            "date": "1250",
            "place": "Atchison, Atchison, KS, USA",
            "place_name": "Atchison",
            "type": "Birth",
            "summary": "Birth - Knudsen, Ralph",
            "participants": {
                "families": [],
                "people": [
                    {
                        "person": {
                            "birth": {
                                "date": "1250",
                                "place": "Atchison, Atchison, KS, USA",
                                "place_name": "Atchison",
                                "type": "Birth",
                                "summary": "Birth - Knudsen, Ralph",
                            },
                            "death": {
                                "date": "1316",
                                "place": "",
                                "place_name": "",
                                "type": "Death",
                                "summary": "Death - Knudsen, Ralph",
                            },
                            "gramps_id": "I1020",
                            "handle": "H4EKQCFV3436HSKY2D",
                            "name_display": "Ralph KNUDSEN",
                            "name_given": "Ralph",
                            "name_surname": "Knudsen",
                            "name_suffix": "",
                            "sex": "M",
                        },
                        "role": "Primary",
                    }
                ],
            },
            "references": {
                "person": [
                    {
                        "birth": {
                            "date": "1250",
                            "place": "Atchison, Atchison, KS, USA",
                            "place_name": "Atchison",
                            "type": "Birth",
                            "summary": "Birth - Knudsen, Ralph",
                        },
                        "death": {
                            "date": "1316",
                            "place": "",
                            "place_name": "",
                            "type": "Death",
                            "summary": "Death - Knudsen, Ralph",
                        },
                        "gramps_id": "I1020",
                        "handle": "H4EKQCFV3436HSKY2D",
                        "name_display": "Ralph KNUDSEN",
                        "name_given": "Ralph",
                        "name_surname": "Knudsen",
                        "name_suffix": "",
                        "sex": "M",
                    }
                ],
            },
        }

    def test_get_events_handle_parameter_backlinks_validate_semantics(
        self, test_adapter
    ):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?backlinks", check="boolean"
        )

    def test_get_events_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c", "backlinks"
        )
        for key in ["H4EKQCFV3436HSKY2D"]:
            assert key in rv["backlinks"]["person"]

    def test_get_events_handle_parameter_backlinks_expected_results_extended(
        self, test_adapter
    ):
        """Test backlinks extended result."""
        rv = check_success(
            test_adapter, TEST_URL + "a5af0eb6dd140de132c?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["person"]:
            assert obj["handle"] in ["H4EKQCFV3436HSKY2D"]


class TestEventsHandleSpan:
    """Test cases for the /api/events/{handle1}/span/{handle2} endpoint for a specific event."""

    def test_get_events_handle_span_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(
            test_adapter, TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0"
        )

    def test_get_events_handle_span_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(
            test_adapter, TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb10730335400"
        )

    def test_get_events_handle_span_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(
            test_adapter, TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0"
        )
        assert rv["span"] == "663 years, 5 months"

    def test_get_events_handle_span_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0?junk_parm=1",
        )

    def test_get_events_handle_span_validate_semantics_precision(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0?precision",
            check="number",
        )

    def test_get_events_handle_span_expected_result_precision(self, test_adapter):
        """Test precision parameter expected response."""
        rv = check_success(
            test_adapter,
            TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0?precision=1",
        )
        assert rv["span"] == "663 years"

    def test_get_events_handle_span_validate_semantics_locale(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0?locale",
            check="base",
        )

    def test_get_events_handle_span_expected_result_locale(self, test_adapter):
        """Test locale parameter expected response."""
        rv = check_success(
            test_adapter,
            TEST_URL + "a5af0eb6ce0378db417/span/a5af0ecb107303354a0?locale=de",
        )
        assert rv["span"] == "663 Jahre, 5 Monate"
