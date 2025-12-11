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

"""Tests for the /api/timelines endpoints using example_gramps."""


from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_invalid_syntax,
    check_keys_parameter,
    check_paging_parameters,
    check_requires_token,
    check_resource_missing,
    check_skipkeys_parameter,
    check_strip_parameter,
    check_success,
)

TEST_URL = BASE_URL + "/timelines/"


class TestTimelinesPeople:
    """Test cases for the /api/timelines/people endpoint for a group of people."""

    @classmethod
    def test_get_timelines_people_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "people/")

    def test_get_timelines_people_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "people/?ratings=1", "TimelineEventProfile"
        )

    def test_get_timelines_people_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL + "people/")
        # check first expected record
        assert rv[0]["gramps_id"] == "E2957"
        # check last expected record
        assert rv[-1]["gramps_id"] == "E3431"

    def test_get_timelines_people_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?junk_parm=1")

    def test_get_timelines_people_parameter_strip_validate_semantics(
        self, test_adapter
    ):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?strip", check="boolean"
        )

    def test_get_timelines_people_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "people/")

    def test_get_timelines_people_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?keys", check="base")

    def test_get_timelines_people_parameter_keys_expected_result_single_key(
        self, test_adapter
    ):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "people/", ["date", "handle", "type"]
        )

    def test_get_timelines_people_parameter_keys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "people/", [",".join(["date", "handle", "type"])]
        )

    def test_get_timelines_people_parameter_skipkeys_validate_semantics(
        self, test_adapter
    ):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?skipkeys", check="base"
        )

    def test_get_timelines_people_parameter_skipkeys_expected_result_single_key(
        self, test_adapter
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "people/", ["date", "handle", "type"]
        )

    def test_get_timelines_people_parameter_skipkeys_expected_result_multiple_keys(
        self,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "people/", [",".join(["date", "handle", "type"])]
        )

    def test_get_timelines_people_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?page", check="number")

    def test_get_timelines_people_parameter_pagesize_validate_semantics(
        self, test_adapter
    ):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?pagesize", check="number"
        )

    def test_get_timelines_people_parameter_page_pagesize_expected_result(
        self, test_adapter
    ):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(
            test_adapter, TEST_URL + "people/?keys=handle", 10, join="&"
        )

    def test_get_timelines_people_parameter_filter_validate_semantics(
        self, test_adapter
    ):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?filter", check="base")

    def test_get_timelines_people_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(
            test_adapter, TEST_URL + "people/?filter=ReallyNotARealFilterYouSee"
        )

    def test_get_timelines_people_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            test_adapter, TEST_URL + 'people/?rules={"rules"[{"name":"IsMale"}]}'
        )

    def test_get_timelines_people_parameter_rules_validate_semantics(
        self, test_adapter
    ):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?rules", check="base")
        check_invalid_semantics(
            test_adapter,
            TEST_URL + 'people/?rules={"some":"where","rules":[{"name":"IsMale"}]}',
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL + 'people/?rules={"function":"none","rules":[{"name":"IsMale"}]}',
        )

    def test_get_timelines_people_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(
            test_adapter, TEST_URL + 'people/?rules={"rules":[{"name":"OldForest"}]}'
        )

    # If this works take rest on faith, should be same code path anyway
    def test_get_timelines_people_parameter_rules_expected_response_single_rule(
        self, test_adapter
    ):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + 'people/?keys=gender&rules={"rules":[{"name":"HasUnknownGender"}]}',
        )
        assert len(rv) == 4

    def test_get_timelines_people_parameter_locale_expected_result(self, test_adapter):
        """Test expected profile response for a locale."""
        rv = check_success(test_adapter, TEST_URL + "people/?page=1&locale=de")
        assert rv[0]["label"] == "Heirat"
        assert rv[0]["role"] == "Familie"
        assert rv[0]["person"]["birth"]["type"] == "Geburt"
        assert rv[0]["person"]["death"]["type"] == "Tod"

    def test_get_timelines_people_parameter_anchor_missing_content(self, test_adapter):
        """Test missing content response."""
        check_resource_missing(
            test_adapter, TEST_URL + "people/?anchor=not_real_person"
        )

    def test_get_timelines_people_parameter_anchor_validate_semantics(
        self, test_adapter
    ):
        """Test invalid anchor parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?anchor", check="base")

    def test_get_timelines_people_parameter_anchor_expected_result(self, test_adapter):
        """Test anchor parameter expected result."""
        rv = check_success(test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH")
        assert rv[0]["gramps_id"] == "E1656"
        assert rv[1]["label"] == "Marriage"
        assert rv[10]["label"] == "Birth (Stepsister)"

    def test_get_timelines_people_parameter_precision_validate_semantics(
        self, test_adapter
    ):
        """Test invalid precision parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&precision",
            check="number",
        )

    def test_get_timelines_people_parameter_precision_expected_result(
        self, test_adapter
    ):
        """Test precision parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&precision=3"
        )
        assert rv[11]["label"] == "Birth"
        assert rv[11]["age"] == "2 years, 6 months, 1 days"

    def test_get_timelines_people_parameter_first_validate_semantics(
        self, test_adapter
    ):
        """Test invalid first parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&first",
            check="boolean",
        )

    def test_get_timelines_people_parameter_first_expected_result(self, test_adapter):
        """Test first parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&first=1"
        )
        assert rv[0]["date"] == "1855-06-21"
        rv = check_success(
            test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&first=0"
        )
        assert rv[0]["date"] == "5"

    def test_get_timelines_people_parameter_last_validate_semantics(self, test_adapter):
        """Test invalid last parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&last",
            check="boolean",
        )

    def test_get_timelines_people_parameter_last_expected_result(self, test_adapter):
        """Test last parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&last=1"
        )
        assert rv[310]["date"] == "1911-07-01"
        rv = check_success(
            test_adapter, TEST_URL + "people/?anchor=GNUJQCL9MD64AM56OH&last=0"
        )
        assert rv[1066]["date"] == "2006-01-11"

    def test_get_timelines_people_parameter_events_validate_semantics(
        self, test_adapter
    ):
        """Test invalid events parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?keys=type&events", check="list"
        )

    def test_get_timelines_people_parameter_events_expected_result(self, test_adapter):
        """Test events parameter for expected results."""
        rv = check_success(test_adapter, TEST_URL + "people/?keys=type&events=Birth")
        for item in rv:
            assert item["type"] in ["Birth", "Death"]
        rv = check_success(test_adapter, TEST_URL + "people/?keys=type&events=Burial")
        for item in rv:
            assert item["type"] in ["Birth", "Death", "Burial"]

    def test_get_timelines_people_parameter_event_class_validate_semantics(
        self, test_adapter
    ):
        """Test invalid event_class parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?event_class", check="list"
        )

    def test_get_timelines_people_parameter_event_class_expected_result(
        self, test_adapter
    ):
        """Test event_class parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "people/?keys=type&event_classes=other"
        )
        for item in rv:
            assert item["type"] != "Burial"
        rv = check_success(
            test_adapter, TEST_URL + "people/?keys=type&event_classes=vital"
        )
        for item in rv:
            assert item["type"] in ["Birth", "Death", "Burial"]

    def test_get_timelines_people_parameter_ratings_validate_semantics(
        self, test_adapter
    ):
        """Test invalid ratings parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?ratings", check="boolean"
        )

    def test_get_timelines_people_parameter_handles_missing_content(self, test_adapter):
        """Test missing content response."""
        check_resource_missing(
            test_adapter, TEST_URL + "people/?handles=not_a_real_handle"
        )

    def test_get_timelines_people_parameter_handles_validate_semantics(
        self, test_adapter
    ):
        """Test invalid handles parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?handles", check="base"
        )

    def test_get_timelines_people_parameter_handles_expected_result(self, test_adapter):
        """Test handles parameter for expected results."""
        rv = check_success(
            test_adapter,
            TEST_URL + "people/?handles=TDTJQCGYRS2RCCGQN3,GNUJQCL9MD64AM56OH",
        )
        for item in rv:
            assert item["person"]["name_given"] in ["Lewis Anderson", "Howard Lane"]

    def test_get_timelines_people_parameter_dates_validate_semantics(
        self, test_adapter
    ):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates", check="list")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=/1/1")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=1900//1")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=1900/1/")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=-1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=1900/a/1-")
        check_invalid_semantics(
            test_adapter, TEST_URL + "people/?dates=1855/1/1-1900/*/1"
        )
        check_invalid_semantics(test_adapter, TEST_URL + "people/?dates=1855/*/*")

    def test_get_timelines_people_parameter_dates_expected_result(self, test_adapter):
        """Test dates parameter expected results."""
        rv = check_success(test_adapter, TEST_URL + "people/?dates=-1900/1/1")
        assert len(rv) == 1235
        rv = check_success(test_adapter, TEST_URL + "people/?dates=1900/1/1-")
        assert len(rv) == 903
        rv = check_success(test_adapter, TEST_URL + "people/?dates=1855/1/1-1900/12/31")
        assert len(rv) == 300


class TestTimelinesFamilies:
    """Test cases for the /api/timelines/families endpoint for a group of families."""

    @classmethod
    def test_get_timelines_families_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "families/")

    def test_get_timelines_families_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(
            test_adapter, TEST_URL + "families/?ratings=1", "TimelineEventProfile"
        )

    def test_get_timelines_families_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL + "families/")
        # check first expected record
        assert rv[0]["gramps_id"] == "E2957"
        # check last expected record
        assert rv[-1]["gramps_id"] == "E3431"

    def test_get_timelines_families_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "families/?junk_parm=1")

    def test_get_timelines_families_parameter_strip_validate_semantics(
        self, test_adapter
    ):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?strip", check="boolean"
        )

    def test_get_timelines_families_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "families/")

    def test_get_timelines_families_parameter_keys_validate_semantics(
        self, test_adapter
    ):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "families/?keys", check="base")

    def test_get_timelines_families_parameter_keys_expected_result_single_key(
        self, test_adapter
    ):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "families/", ["date", "handle", "type"]
        )

    def test_get_timelines_families_parameter_keys_expected_result_multiple_keys(
        self, test_adapter
    ):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            test_adapter, TEST_URL + "families/", [",".join(["date", "handle", "type"])]
        )

    def test_get_timelines_families_parameter_skipkeys_validate_semantics(
        self, test_adapter
    ):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?skipkeys", check="base"
        )

    def test_get_timelines_families_parameter_skipkeys_expected_result_single_key(
        self, test_adapter
    ):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "families/", ["date", "handle", "type"]
        )

    def test_get_timelines_families_parameter_skipkeys_expected_result_multiple_keys(
        self,
    ):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            test_adapter, TEST_URL + "families/", [",".join(["date", "handle", "type"])]
        )

    def test_get_timelines_families_parameter_page_validate_semantics(
        self, test_adapter
    ):
        """Test invalid page parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?page", check="number"
        )

    def test_get_timelines_families_parameter_pagesize_validate_semantics(
        self, test_adapter
    ):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?pagesize", check="number"
        )

    def test_get_timelines_families_parameter_page_pagesize_expected_result(
        self, test_adapter
    ):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(
            test_adapter, TEST_URL + "families/?keys=handle", 10, join="&"
        )

    def test_get_timelines_families_parameter_filter_validate_semantics(
        self, test_adapter
    ):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?filter", check="base"
        )

    def test_get_timelines_families_parameter_filter_missing_content(
        self, test_adapter
    ):
        """Test response when missing the filter."""
        check_resource_missing(
            test_adapter, TEST_URL + "families/?filter=ReallyNotARealFilterYouSee"
        )

    def test_get_timelines_families_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            test_adapter,
            TEST_URL + 'families/?rules={"rules"[{"name":"IsBookmarked"}]}',
        )

    def test_get_timelines_families_parameter_rules_validate_semantics(
        self, test_adapter
    ):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?rules", check="base"
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + 'families/?rules={"some":"where","rules":[{"name":"IsBookmarked"}]}',
        )
        check_invalid_semantics(
            test_adapter,
            TEST_URL
            + 'families/?rules={"function":"none","rules":[{"name":"IsBookmarked"}]}',
        )

    def test_get_timelines_families_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(
            test_adapter, TEST_URL + 'families/?rules={"rules":[{"name":"Brandywine"}]}'
        )

    # If this works take rest on faith, should be same code path anyway
    def test_get_timelines_families_parameter_rules_expected_response_single_rule(
        self, test_adapter
    ):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            test_adapter,
            TEST_URL
            + 'families/?keys=handles&rules={"rules":[{"name":"IsBookmarked"}]}',
        )
        assert len(rv) == 33

    def test_get_timelines_families_parameter_locale_expected_result(
        self, test_adapter
    ):
        """Test expected profile response for a locale."""
        rv = check_success(test_adapter, TEST_URL + "families/?page=1&locale=de")
        assert rv[0]["label"] == "Heirat"
        assert rv[0]["person"]["birth"]["type"] == "Geburt"
        assert rv[0]["person"]["death"]["type"] == "Tod"
        assert rv[0]["place"]["type"] == "Stadt"

    def test_get_timelines_families_parameter_events_validate_semantics(
        self, test_adapter
    ):
        """Test invalid events parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?keys=type&events", check="list"
        )

    def test_get_timelines_families_parameter_events_expected_result(
        self, test_adapter
    ):
        """Test events parameter for expected results."""
        rv = check_success(test_adapter, TEST_URL + "families/?keys=type&events=Birth")
        for item in rv:
            assert item["type"] in ["Birth", "Death"]
        rv = check_success(test_adapter, TEST_URL + "families/?keys=type&events=Burial")
        for item in rv:
            assert item["type"] in ["Birth", "Death", "Burial"]

    def test_get_timelines_families_parameter_event_class_validate_semantics(
        self, test_adapter
    ):
        """Test invalid event_class parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?event_class", check="list"
        )

    def test_get_timelines_families_parameter_event_class_expected_result(
        self, test_adapter
    ):
        """Test event_class parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "families/?keys=type&event_classes=other"
        )
        for item in rv:
            assert item["type"] != "Burial"
        rv = check_success(
            test_adapter, TEST_URL + "families/?keys=type&event_classes=vital"
        )
        for item in rv:
            assert item["type"] in ["Birth", "Death", "Burial"]

    def test_get_timelines_families_parameter_ratings_validate_semantics(
        self, test_adapter
    ):
        """Test invalid ratings parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?ratings", check="boolean"
        )

    def test_get_timelines_families_parameter_handles_missing_content(
        self, test_adapter
    ):
        """Test missing content response."""
        check_resource_missing(
            test_adapter, TEST_URL + "families/?handles=not_a_real_handle"
        )

    def test_get_timelines_families_parameter_handles_validate_semantics(
        self, test_adapter
    ):
        """Test invalid handles parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?handles", check="base"
        )

    def test_get_timelines_families_parameter_handles_expected_result(
        self, test_adapter
    ):
        """Test handles parameter for expected results."""
        rv = check_success(
            test_adapter, TEST_URL + "families/?handles=9OUJQCBOHW9UEK9CNV"
        )
        assert len(rv) == 33

    def test_get_timelines_families_parameter_dates_validate_semantics(
        self, test_adapter
    ):
        """Test invalid dates parameter and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?dates", check="list"
        )
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=/1/1")
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=1900//1")
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=1900/1/")
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=-1900/a/1")
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=1900/a/1-")
        check_invalid_semantics(
            test_adapter, TEST_URL + "families/?dates=1855/1/1-1900/*/1"
        )
        check_invalid_semantics(test_adapter, TEST_URL + "families/?dates=1855/*/*")

    def test_get_timelines_families_parameter_dates_expected_result(self, test_adapter):
        """Test dates parameter expected results."""
        rv = check_success(test_adapter, TEST_URL + "families/?dates=-1900/1/1")
        assert len(rv) == 1214
        rv = check_success(test_adapter, TEST_URL + "families/?dates=1900/1/1-")
        assert len(rv) == 885
        rv = check_success(
            test_adapter, TEST_URL + "families/?dates=1855/1/1-1900/12/31"
        )
        assert len(rv) == 290
