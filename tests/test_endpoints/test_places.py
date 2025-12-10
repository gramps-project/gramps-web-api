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

"""Tests for the /api/places endpoints using example_gramps."""


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

TEST_URL = BASE_URL + "/places/"


class TestPlaces:
    """Test cases for the /api/places endpoint for a list of places."""

    def test_get_places_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_places_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL + "?extend=all&profile=all&backlinks=1", "Place"
        )

    def test_get_places_expected_results_total(self, test_adapter, example_object_counts):
        """Test expected number of results returned."""
        check_totals(test_adapter, TEST_URL + "?keys=handle", example_object_counts["places"])

    def test_get_places_expected_results(self, test_adapter):
        """Test some expected results returned."""
        rv = check_success(test_adapter, TEST_URL)
        # check first expected record
        assert rv[0]["gramps_id"] == "P0441"
        assert rv[0]["handle"] == "dd445e5bfcc17bd1838"
        # check last expected record
        assert rv[-1]["gramps_id"] == "P0438"
        assert rv[-1]["handle"] == "d583a5b8b586fb992c8"

    def test_get_places_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk_parm=1")

    def test_get_places_parameter_gramps_id_validate_semantics(self, test_adapter):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?gramps_id", check="base")

    def test_get_places_parameter_gramps_id_missing_content(self, test_adapter):
        """Test response for missing gramps_id object."""
        check_resource_missing(test_adapter, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_places_parameter_gramps_id_expected_result(self, test_adapter):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=P1108")
        assert len(rv) == 1
        assert rv[0]["handle"] == "B9VKQCD14KD2OH3QZY"

    def test_get_places_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?strip", check="boolean")

    def test_get_places_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL)

    def test_get_places_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?keys", check="base")

    def test_get_places_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, ["alt_loc", "handle", "urls"])

    def test_get_places_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL, [",".join(["alt_loc", "handle", "urls"])])

    def test_get_places_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?skipkeys", check="base")

    def test_get_places_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(test_adapter, TEST_URL, ["alt_loc", "handle", "urls"])

    def test_get_places_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(test_adapter, TEST_URL, [",".join(["alt_loc", "handle", "urls"])]
        )

    def test_get_places_parameter_page_validate_semantics(self, test_adapter):
        """Test invalid page parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?page", check="number")

    def test_get_places_parameter_pagesize_validate_semantics(self, test_adapter):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?pagesize", check="number")

    def test_get_places_parameter_page_pagesize_expected_result(self, test_adapter):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(test_adapter, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_places_parameter_sort_validate_semantics(self, test_adapter):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?sort", check="list")

    def test_get_places_parameter_sort_change_ascending_expected_result(self, test_adapter):
        """Test sort parameter change ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change")

    def test_get_places_parameter_sort_change_descending_expected_result(self, test_adapter):
        """Test sort parameter change descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "change", direction="-")

    def test_get_places_parameter_sort_gramps_id_ascending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id ascending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id")
        assert rv[0]["gramps_id"] == "P0000"
        assert rv[-1]["gramps_id"] == "P1703"

    def test_get_places_parameter_sort_gramps_id_descending_expected_result(self, test_adapter):
        """Test sort parameter gramps_id descending result."""
        rv = check_sort_parameter(test_adapter, TEST_URL, "gramps_id", direction="-")
        assert rv[0]["gramps_id"] == "P1703"
        assert rv[-1]["gramps_id"] == "P0000"

    def test_get_places_parameter_sort_latitude_ascending_expected_result(self, test_adapter):
        """Test sort parameter latitude ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "latitude", value_key="lat")

    def test_get_places_parameter_sort_latitude_descending_expected_result(self, test_adapter):
        """Test sort parameter latitude descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "latitude", value_key="lat", direction="-")

    def test_get_places_parameter_sort_longitude_ascending_expected_result(self, test_adapter):
        """Test sort parameter longitude ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "longitude", value_key="long")

    def test_get_places_parameter_sort_longitude_descending_expected_result(self, test_adapter):
        """Test sort parameter longitude descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "longitude", value_key="long", direction="-"
        )

    def test_get_places_parameter_sort_private_ascending_expected_result(self, test_adapter):
        """Test sort parameter private ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private")

    def test_get_places_parameter_sort_private_descending_expected_result(self, test_adapter):
        """Test sort parameter private descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "private", direction="-")

    def test_get_places_parameter_sort_title_ascending_expected_result(self, test_adapter):
        """Test sort parameter title ascending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=title&sort=+title")
        assert rv[0]["title"] == "Aberdeen, SD"
        assert rv[-1]["title"] == "Σιάτιστα"

    def test_get_places_parameter_sort_title_descending_expected_result(self, test_adapter):
        """Test sort parameter title descending result."""
        rv = check_success(test_adapter, TEST_URL + "?keys=title&sort=-title")
        assert rv[0]["title"] == "Σιάτιστα"
        assert rv[-1]["title"] == "Aberdeen, SD"

    def test_get_places_parameter_sort_type_ascending_expected_result(self, test_adapter):
        """Test sort parameter type ascending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type", value_key="place_type")

    def test_get_places_parameter_sort_type_descending_expected_result(self, test_adapter):
        """Test sort parameter type descending result."""
        check_sort_parameter(test_adapter, TEST_URL, "type", value_key="place_type", direction="-"
        )

    def test_get_places_parameter_sort_type_ascending_expected_result_with_locale(self, test_adapter):
        """Test sort parameter type ascending result using different locale."""
        rv = check_success(test_adapter, TEST_URL + "?keys=place_type&sort=+type&locale=de")
        assert rv[0]["place_type"] == "State"
        assert rv[-1]["place_type"] == "City"

    def test_get_places_parameter_sort_type_descending_expected_result_with_locale(
        self, test_adapter
    ):
        """Test sort parameter type descending result using different locale."""
        rv = check_success(test_adapter, TEST_URL + "?keys=place_type&sort=-type&locale=de")
        assert rv[0]["place_type"] == "City"
        assert rv[-1]["place_type"] == "State"

    def test_get_places_parameter_filter_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?filter", check="base")

    def test_get_places_parameter_filter_missing_content(self, test_adapter):
        """Test response when missing the filter."""
        check_resource_missing(test_adapter, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_places_parameter_rules_validate_syntax(self, test_adapter):
        """Test invalid rules syntax."""
        check_invalid_syntax(test_adapter, TEST_URL + '?rules={"rules"[{"name":"HasNoLatOrLon"}]}'
        )

    def test_get_places_parameter_rules_validate_semantics(self, test_adapter):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?rules", check="base")
        check_invalid_semantics(test_adapter,
            TEST_URL + '?rules={"some":"where","rules":[{"name":"HasNoLatOrLon"}]}',
        )
        check_invalid_semantics(test_adapter,
            TEST_URL + '?rules={"function":"none","rules":[{"name":"HasNoLatOrLon"}]}',
        )

    def test_get_places_parameter_rules_missing_content(self, test_adapter):
        """Test rules parameter missing request content."""
        check_resource_missing(test_adapter, TEST_URL + '?rules={"rules":[{"name":"Shire"}]}')

    def test_get_places_parameter_rules_expected_response_single_rule(self, test_adapter):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(test_adapter, TEST_URL + '?keys=lat,long&rules={"rules":[{"name":"HasNoLatOrLon"}]}'
        )
        for item in rv:
            assert item["lat"] == ""
            assert item["long"] == ""

    def test_get_places_parameter_rules_expected_response_multiple_rules(self, test_adapter):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(test_adapter,
            TEST_URL
            + '?keys=lat,long,place_type&rules={"rules":[{"name":"HasData","values":["","City","",""]},{"name":"HasNoLatOrLon"}]}',
        )
        for item in rv:
            assert item["lat"] == ""
            assert item["long"] == ""
            assert item["place_type"] == "City"

    def test_get_places_parameter_rules_expected_response_or_function(self, test_adapter):
        """Test rules parameter expected response for or function."""
        rv = check_success(test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasData","values":["","City","",""]},{"name":"HasNoLatOrLon"}]}',
        )
        assert len(rv) == 1296

    def test_get_places_parameter_rules_expected_response_one_function(self, test_adapter):
        """Test rules parameter expected response for one function."""
        rv = check_success(test_adapter,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasData","values":["","City","",""]},{"name":"HasNoLatOrLon"}]}',
        )
        assert len(rv) == 811

    def test_get_places_parameter_rules_expected_response_invert(self, test_adapter):
        """Test rules parameter expected response for invert option."""
        rv = check_success(test_adapter,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasNoLatOrLon"}]}',
        )
        assert len(rv) == 373

    def test_get_places_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?extend", check="list")

    def test_get_places_parameter_extend_expected_result_citation_list(self, test_adapter):
        """Test extend citation_list result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "?gramps_id=P1108", "citation_list", "citations", join="&"
        )

    def test_get_places_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(test_adapter,
            TEST_URL + "?gramps_id=P1108",
            "media_list",
            "media",
            join="&",
            reference=True,
        )

    def test_get_places_parameter_extend_expected_result_note_list(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "?gramps_id=P1108", "note_list", "notes", join="&"
        )

    def test_get_places_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "?gramps_id=P1108", "tag_list", "tags", join="&"
        )

    def test_get_places_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=P1108&extend=all&keys=extended")
        assert len(rv[0]["extended"]) == 4
        for key in ["citations", "media", "notes", "tags"]:
            assert key in rv[0]["extended"]

    def test_get_places_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(test_adapter,
            TEST_URL
            + "?gramps_id=P1108&extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv[0]["extended"]) == 2
        assert "notes" in rv[0]["extended"]
        assert "tags" in rv[0]["extended"]

    def test_get_places_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?backlinks", check="boolean")

    def test_get_places_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_success(test_adapter, TEST_URL + "?gramps_id=P1108&keys=backlinks&backlinks=1"
        )
        for key in ["a5af0ec23c136ad6742", "a5af0ec27662bcd851c"]:
            assert key in rv[0]["backlinks"]["event"]


class TestPlacesHandle:
    """Test cases for the /api/places/{handle} endpoint for a specific place."""

    def test_get_places_handle_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "09UJQCF3TNGH9GU0P1")

    def test_get_places_handle_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter,
            TEST_URL + "09UJQCF3TNGH9GU0P1?extend=all&profile=all&backlinks=1",
            "Place",
        )

    def test_get_places_handle_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "does_not_exist")

    def test_get_places_handle_expected_result(self, test_adapter):
        """Test response for a specific event."""
        rv = check_success(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J")
        assert rv["gramps_id"] == "P1678"

    def test_get_places_handle_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?junk_parm=1")

    def test_get_places_handle_parameter_strip_validate_semantics(self, test_adapter):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?strip")

    def test_get_places_handle_parameter_strip_expected_result(self, test_adapter):
        """Test strip parameter produces expected result."""
        check_strip_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", paginate=False)

    def test_get_places_handle_parameter_keys_validate_semantics(self, test_adapter):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?keys", check="base"
        )

    def test_get_places_handle_parameter_keys_expected_result_single_key(self, test_adapter):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", ["alt_loc", "handle", "urls"]
        )

    def test_get_places_handle_parameter_keys_expected_result_multiple_keys(self, test_adapter):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(test_adapter,
            TEST_URL + "YNUJQC8YM5EGRG868J",
            [",".join(["alt_loc", "handle", "urls"])],
        )

    def test_get_places_handle_parameter_skipkeys_validate_semantics(self, test_adapter):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?skipkeys", check="base"
        )

    def test_get_places_handle_parameter_skipkeys_expected_result_single_key(self, test_adapter):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", ["alt_loc", "handle", "urls"]
        )

    def test_get_places_handle_parameter_skipkeys_expected_result_multiple_keys(self, test_adapter):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(test_adapter,
            TEST_URL + "YNUJQC8YM5EGRG868J",
            [",".join(["alt_loc", "handle", "urls"])],
        )

    def test_get_places_handle_parameter_extend_validate_semantics(self, test_adapter):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?extend", check="list"
        )

    def test_get_places_handle_parameter_extend_expected_result_citation_list(self, test_adapter):
        """Test extend citation_list result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", "citation_list", "citations"
        )

    def test_get_places_handle_parameter_extend_expected_result_media_list(self, test_adapter):
        """Test extend media_list result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", "media_list", "media", reference=True
        )

    def test_get_places_handle_parameter_extend_expected_result_notes(self, test_adapter):
        """Test extend notes result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", "note_list", "notes"
        )

    def test_get_places_handle_parameter_extend_expected_result_tag_list(self, test_adapter):
        """Test extend tag_list result."""
        check_single_extend_parameter(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J", "tag_list", "tags"
        )

    def test_get_places_handle_parameter_extend_expected_result_all(self, test_adapter):
        """Test extend all result."""
        rv = check_success(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?extend=all&keys=extended"
        )
        assert len(rv["extended"]) == 4
        for key in ["citations", "media", "notes", "tags"]:
            assert key in rv["extended"]

    def test_get_places_handle_parameter_extend_expected_result_multiple_keys(self, test_adapter):
        """Test extend result for multiple keys."""
        rv = check_success(test_adapter,
            TEST_URL
            + "YNUJQC8YM5EGRG868J?extend=note_list,tag_list&keys=note_list,tag_list,extended",
        )
        assert len(rv["extended"]) == 2
        assert "notes" in rv["extended"]
        assert "tags" in rv["extended"]

    def test_get_places_handle_parameter_profile(self, test_adapter):
        """Test place profile."""
        rv = check_success(test_adapter, TEST_URL + "08TJQCCFIX31BXPNXN?profile=self&locale=it")
        assert rv["profile"] == {
                "alternate_names": [],
                "alternate_place_names": [],
                "gramps_id": "P0860",
                "lat": 33.6259414,
                "long": -97.1333453,
                "name": "Gainesville",
                "parent_places": [
                    {
                        "alternate_names": [],
                        "alternate_place_names": [],
                        "gramps_id": "P0194",
                        "lat": 0,
                        "long": 0,
                        "name": "Llano",
                        "type": "Contea",
                    },
                    {
                        "alternate_names": [],
                        "alternate_place_names": [],
                        "gramps_id": "P0010",
                        "lat": 0,
                        "long": 0,
                        "name": "TX",
                        "type": "Stato (federato)",
                    },
                    {
                        "alternate_names": [],
                        "alternate_place_names": [],
                        "gramps_id": "P0957",
                        "lat": 0,
                        "long": 0,
                        "name": "USA",
                        "type": "Nazione",
                    },
                ],
                "direct_parent_places": [
                    {
                        "place": {
                            "alternate_names": [],
                            "alternate_place_names": [],
                            "gramps_id": "P0194",
                            "lat": 0,
                            "long": 0,
                            "name": "Llano",
                            "type": "Contea",
                        },
                        "date_str": "",
                    },
                ],
                "type": "Città",
            }

    def test_get_places_handle_parameter_profile_alternative_names(self, test_adapter):
        """Test place profile."""
        rv = check_success(test_adapter, TEST_URL + "fce62795df51c5d8ae432e3942c?profile=all&locale=en"
        )
        assert rv["profile"] == {
                "alternate_names": ["Leningrad", "Petrograd"],
                "alternate_place_names": [
                    {
                        "date_str": "between 1924-01-26 and 1991-09-06",
                        "value": "Leningrad",
                    },
                    {"date_str": "between 1914 and 1924", "value": "Petrograd"},
                ],
                "gramps_id": "P0443",
                "lat": 0,
                "long": 0,
                "name": "Saint Petersburg",
                "parent_places": [
                    {
                        "alternate_names": [],
                        "alternate_place_names": [],
                        "gramps_id": "P0442",
                        "lat": 0,
                        "long": 0,
                        "name": "Russia",
                        "type": "Country",
                    },
                ],
                "direct_parent_places": [
                    {
                        "place": {
                            "alternate_names": [],
                            "alternate_place_names": [],
                            "gramps_id": "P0442",
                            "lat": 0,
                            "long": 0,
                            "name": "Russia",
                            "type": "Country",
                        },
                        "date_str": "",
                    }
                ],
                "references": {},
                "type": "City",
            }

    def test_get_places_handle_parameter_backlinks_validate_semantics(self, test_adapter):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "YNUJQC8YM5EGRG868J?backlinks", check="boolean"
        )

    def test_get_places_handle_parameter_backlinks_expected_result(self, test_adapter):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(test_adapter, TEST_URL + "09UJQCF3TNGH9GU0P1", "backlinks")
        for key in ["a5af0ec6378200d83f5", "a5af0ec671815ecc2b6"]:
            assert key in rv["backlinks"]["event"]

    def test_get_places_handle_parameter_backlinks_expected_results_extended(self, test_adapter):
        """Test backlinks extended result."""
        rv = check_success(test_adapter, TEST_URL + "09UJQCF3TNGH9GU0P1?backlinks=1&extend=backlinks"
        )
        assert "backlinks" in rv
        assert "extended" in rv
        assert "backlinks" in rv["extended"]
        for obj in rv["extended"]["backlinks"]["event"]:
            assert obj["handle"] in ["a5af0ec6378200d83f5", "a5af0ec671815ecc2b6"]
