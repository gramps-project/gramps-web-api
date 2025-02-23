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

"""Tests for the /api/notes endpoints using example_gramps."""

import json
import re
import unittest
from urllib.parse import quote

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

TEST_URL = BASE_URL + "/notes/"


class TestNotes(unittest.TestCase):
    """Test cases for the /api/notes endpoint for a list of notes."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_notes_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_notes_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "?extend=all&profile=all&backlinks=1", "Note"
        )

    def test_get_notes_expected_results_total(self):
        """Test expected number of results returned."""
        check_totals(self, TEST_URL + "?keys=handle", get_object_count("notes"))

    def test_get_notes_expected_results(self):
        """Test some expected results returned."""
        rv = check_success(self, TEST_URL)
        # check first expected record
        self.assertEqual(rv[0]["gramps_id"], "N0001")
        self.assertEqual(rv[0]["handle"], "ac380498bac48eedee8")
        self.assertEqual(rv[0]["type"], "Name Note")
        # check last expected record
        self.assertEqual(rv[-1]["gramps_id"], "_custom1")
        self.assertEqual(rv[-1]["handle"], "d0436be64ac277b615b79b34e72")
        self.assertEqual(rv[-1]["type"], "General")

    def test_get_notes_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk_parm=1")

    def test_get_notes_parameter_gramps_id_validate_semantics(self):
        """Test invalid gramps_id parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?gramps_id", check="base")

    def test_get_notes_parameter_gramps_id_missing_content(self):
        """Test response for missing gramps_id object."""
        check_resource_missing(self, TEST_URL + "?gramps_id=does_not_exist")

    def test_get_notes_parameter_gramps_id_expected_result(self):
        """Test gramps_id parameter returns expected result."""
        rv = check_success(self, TEST_URL + "?gramps_id=_header1")
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0]["handle"], "d0436bba4ec328d3b631259a4ee")

    def test_get_notes_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?strip", check="boolean")

    def test_get_notes_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL)

    def test_get_notes_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?keys", check="base")

    def test_get_notes_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(self, TEST_URL, ["change", "handle", "type"])

    def test_get_notes_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(self, TEST_URL, [",".join(["change", "handle", "type"])])

    def test_get_notes_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?skipkeys", check="base")

    def test_get_notes_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(self, TEST_URL, ["change", "handle", "type"])

    def test_get_notes_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL, [",".join(["change", "handle", "type"])]
        )

    def test_get_notes_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?page", check="number")

    def test_get_notes_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?pagesize", check="number")

    def test_get_notes_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters produce expected result."""
        check_paging_parameters(self, TEST_URL + "?keys=handle", 4, join="&")

    def test_get_notes_parameter_sort_validate_semantics(self):
        """Test invalid sort parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?sort", check="list")

    def test_get_notes_parameter_sort_change_ascending_expected_result(self):
        """Test sort parameter change ascending result."""
        check_sort_parameter(self, TEST_URL, "change")

    def test_get_notes_parameter_sort_change_descending_expected_result(self):
        """Test sort parameter change descending result."""
        check_sort_parameter(self, TEST_URL, "change", direction="-")

    def test_get_notes_parameter_sort_gramps_id_ascending_expected_result(self):
        """Test sort parameter gramps_id ascending result."""
        rv = check_success(self, TEST_URL + "?keys=gramps_id&sort=+gramps_id")
        self.assertEqual(rv[0]["gramps_id"], "_custom1")
        self.assertEqual(rv[-1]["gramps_id"], "N0015")

    def test_get_notes_parameter_sort_gramps_id_descending_expected_result(self):
        """Test sort parameter gramps_id descending result."""
        rv = check_success(self, TEST_URL + "?keys=gramps_id&sort=-gramps_id")
        self.assertEqual(rv[0]["gramps_id"], "N0015")
        self.assertEqual(rv[-1]["gramps_id"], "_custom1")

    def test_get_notes_parameter_sort_private_ascending_expected_result(self):
        """Test sort parameter private ascending result."""
        check_sort_parameter(self, TEST_URL, "private")

    def test_get_notes_parameter_sort_private_descending_expected_result(self):
        """Test sort parameter private descending result."""
        check_sort_parameter(self, TEST_URL, "private", direction="-")

    def test_get_notes_parameter_sort_text_ascending_expected_result(self):
        """Test sort parameter text ascending result."""
        rv = check_success(self, TEST_URL + "?keys=text,handle&sort=+text")
        self.assertEqual(rv[0]["handle"], "b39feb55e1173f4a699")
        self.assertEqual(rv[-1]["handle"], "ac380498c020c7bcdc7")

    def test_get_notes_parameter_sort_text_descending_expected_result(self):
        """Test sort parameter text descending result."""
        rv = check_success(self, TEST_URL + "?keys=text,handle&sort=-text")
        self.assertEqual(rv[0]["handle"], "ac380498c020c7bcdc7")
        self.assertEqual(rv[-1]["handle"], "b39feb55e1173f4a699")

    def test_get_notes_parameter_sort_type_ascending_expected_result(self):
        """Test sort parameter type ascending result."""
        check_sort_parameter(self, TEST_URL, "type")

    def test_get_notes_parameter_sort_type_descending_expected_result(self):
        """Test sort parameter type descending result."""
        check_sort_parameter(self, TEST_URL, "type", direction="-")

    def test_get_notes_parameter_sort_type_ascending_expected_result_with_locale(self):
        """Test sort parameter type ascending result using different locale."""
        rv = check_success(self, TEST_URL + "?keys=type&sort=+type&locale=de")
        self.assertEqual(rv[0]["type"], "Transcript")
        self.assertEqual(rv[-1]["type"], "Source text")

    def test_get_notes_parameter_sort_type_descending_expected_result_with_locale(self):
        """Test sort parameter type descending result using different locale."""
        rv = check_success(self, TEST_URL + "?keys=type&sort=-type&locale=de")
        self.assertEqual(rv[0]["type"], "Source text")
        self.assertEqual(rv[-1]["type"], "Transcript")

    def test_get_notes_parameter_filter_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?filter", check="base")

    def test_get_notes_parameter_filter_missing_content(self):
        """Test response when missing the filter."""
        check_resource_missing(self, TEST_URL + "?filter=ReallyNotARealFilterYouSee")

    def test_get_notes_parameter_rules_validate_syntax(self):
        """Test invalid rules syntax."""
        check_invalid_syntax(
            self,
            TEST_URL + '?rules={"rules"[{"name":"HasType","values":["Person Note"]}]}',
        )

    def test_get_notes_parameter_rules_validate_semantics(self):
        """Test invalid rules parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rules", check="base")
        check_invalid_semantics(
            self,
            TEST_URL
            + '?rules={"some":"where","rules":[{"name":"HasType","values":["Person Note"]}]}',
        )
        check_invalid_semantics(
            self,
            TEST_URL
            + '?rules={"function":"none","rules":[{"name":"HasType","values":["Person Note"]}]}',
        )

    def test_get_notes_parameter_rules_missing_content(self):
        """Test rules parameter missing request content."""
        check_resource_missing(
            self, TEST_URL + '?rules={"rules":[{"name":"Grey Havens"}]}'
        )

    def test_get_notes_parameter_rules_expected_response_single_rule(self):
        """Test rules parameter expected response for a single rule."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=type&rules={"rules":[{"name":"HasType","values":["Person Note"]}]}',
        )
        for item in rv:
            self.assertEqual(item["type"], "Person Note")

    def test_get_notes_parameter_rules_expected_response_multiple_rules(self):
        """Test rules parameter expected response for multiple rules."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
        )
        self.assertEqual(rv, [])

    def test_get_notes_parameter_rules_expected_response_or_function(self):
        """Test rules parameter expected response for or function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"or","rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
        )
        self.assertEqual(len(rv), 3)

    def test_get_notes_parameter_rules_expected_response_one_function(self):
        """Test rules parameter expected response for one function."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"function":"one","rules":[{"name":"HasType","values":["Person Note"]},{"name":"NotePrivate"}]}',
        )
        self.assertEqual(len(rv), 3)

    def test_get_notes_parameter_rules_expected_response_invert(self):
        """Test rules parameter expected response for invert option."""
        rv = check_success(
            self,
            TEST_URL
            + '?keys=handle&rules={"invert":true,"rules":[{"name":"HasType","values":["Person Note"]}]}',
        )
        self.assertEqual(len(rv), 16)

    def test_get_notes_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?extend", check="list")

    def test_get_notes_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "?gramps_id=N0011", "tag_list", "tags", join="&"
        )

    def test_get_notes_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(self, TEST_URL + "?gramps_id=N0011&extend=all&keys=extended")
        self.assertEqual(len(rv[0]["extended"]), 1)
        for key in ["tags"]:
            self.assertIn(key, rv[0]["extended"])

    def test_get_notes_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?backlinks", check="boolean")

    def test_get_notes_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_success(self, TEST_URL + "?page=1&keys=backlinks&backlinks=1")
        for key in ["GNUJQCL9MD64AM56OH"]:
            self.assertIn(key, rv[0]["backlinks"]["person"])


class TestNotesHandle(unittest.TestCase):
    """Test cases for the /api/notes/{handle} endpoint for a specific note."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_notes_handle_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "ac3804aac6b762b75a5")

    def test_get_notes_handle_conforms_to_schema(self):
        """Test conforms to schema."""
        check_conforms_to_schema(
            self,
            TEST_URL + "ac3804aac6b762b75a5?extend=all&profile=all&backlinks=1",
            "Note",
        )

    def test_get_notes_handle_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "does_not_exist")

    def test_get_notes_handle_expected_result(self):
        """Test response for a specific event."""
        rv = check_success(self, TEST_URL + "ac3804aac6b762b75a5")
        self.assertEqual(rv["gramps_id"], "N0008")

    def test_get_notes_handle_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "ac3804aac6b762b75a5?junk_parm=1")

    def test_get_notes_handle_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "ac3804aac6b762b75a5?strip", check="boolean"
        )

    def test_get_notes_handle_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "ac3804aac6b762b75a5")

    def test_get_notes_handle_parameter_keys_validate_semantics(self):
        """Test invalid keys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "ac3804aac6b762b75a5?keys", check="base"
        )

    def test_get_notes_handle_parameter_keys_expected_result_single_key(self):
        """Test keys parameter for some single keys produces expected result."""
        check_keys_parameter(
            self, TEST_URL + "ac3804aac6b762b75a5", ["change", "handle", "type"]
        )

    def test_get_notes_handle_parameter_keys_expected_result_multiple_keys(self):
        """Test keys parameter for multiple keys produces expected result."""
        check_keys_parameter(
            self,
            TEST_URL + "ac3804aac6b762b75a5",
            [",".join(["change", "handle", "type"])],
        )

    def test_get_notes_handle_parameter_skipkeys_validate_semantics(self):
        """Test invalid skipkeys parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "ac3804aac6b762b75a5?skipkeys", check="base"
        )

    def test_get_notes_handle_parameter_skipkeys_expected_result_single_key(self):
        """Test skipkeys parameter for some single keys produces expected result."""
        check_skipkeys_parameter(
            self, TEST_URL + "ac3804aac6b762b75a5", ["change", "handle", "type"]
        )

    def test_get_notes_handle_parameter_skipkeys_expected_result_multiple_keys(self):
        """Test skipkeys parameter for multiple keys produces expected result."""
        check_skipkeys_parameter(
            self,
            TEST_URL + "ac3804aac6b762b75a5",
            [",".join(["change", "handle", "type"])],
        )

    def test_get_notes_handle_parameter_extend_validate_semantics(self):
        """Test invalid extend parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "ac3804aac6b762b75a5?extend", check="list"
        )

    def test_get_notes_handle_parameter_extend_expected_result_tag_list(self):
        """Test extend tag_list result."""
        check_single_extend_parameter(
            self, TEST_URL + "ac3804aac6b762b75a5", "tag_list", "tags"
        )

    def test_get_notes_handle_parameter_extend_expected_result_all(self):
        """Test extend all result."""
        rv = check_success(
            self, TEST_URL + "ac3804aac6b762b75a5?extend=all&keys=extended"
        )
        self.assertEqual(len(rv["extended"]), 1)
        for key in ["tags"]:
            self.assertIn(key, rv["extended"])

    def test_get_notes_handle_parameter_backlinks_validate_semantics(self):
        """Test invalid backlinks parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "b39ff01f75c1f76859a?backlinks", check="boolean"
        )

    def test_get_notes_handle_parameter_backlinks_expected_result(self):
        """Test backlinks expected result."""
        rv = check_boolean_parameter(
            self, TEST_URL + "b39ff01f75c1f76859a", "backlinks"
        )
        for key in ["GNUJQCL9MD64AM56OH"]:
            self.assertIn(key, rv["backlinks"]["person"])

    def test_get_notes_handle_parameter_backlinks_expected_results_extended(self):
        """Test backlinks extended result."""
        rv = check_success(
            self, TEST_URL + "b39ff01f75c1f76859a?backlinks=1&extend=backlinks"
        )
        self.assertIn("backlinks", rv)
        self.assertIn("extended", rv)
        self.assertIn("backlinks", rv["extended"])
        for obj in rv["extended"]["backlinks"]["person"]:
            self.assertIn(obj["handle"], ["GNUJQCL9MD64AM56OH"])

    def test_get_notes_handle_parameter_formats_html(self):
        """Test formats for html."""
        rv = check_success(self, TEST_URL + "b39ff01f75c1f76859a?formats=html")
        self.assertIn("formatted", rv)
        self.assertIn("html", rv["formatted"])
        html = rv["formatted"]["html"]
        self.assertIsInstance(html, str)
        # strip tags
        html_stripped = re.sub("<[^<]+?>", "", html)
        # strip whitespace
        html_stripped = re.sub(r"\s", "", html_stripped)
        text_stripped = re.sub(r"\s", "", rv["text"]["string"])
        # the HTML stripped of tags should be equal to the pure text string,
        # up to white space
        self.assertEqual(text_stripped, html_stripped)

    def test_get_notes_link_format(self):
        """Test formatting of internal links."""
        options = {"link_format": "__{gramps_id}__{handle}__{obj_class}__"}
        rv = check_success(
            self,
            "{}ac380498bac48eedee8?formats=html&format_options={}".format(
                TEST_URL, quote(json.dumps(options))
            ),
        )
        self.assertIn("formatted", rv)
        self.assertIn("html", rv["formatted"])
        html = rv["formatted"]["html"]
        self.assertIsInstance(html, str)
        self.assertIn(
            '<a href="__I0044__GNUJQCL9MD64AM56OH__person__">Lewis Anderson Garner</a>',
            html,
        )
