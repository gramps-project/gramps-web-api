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

"""Tests for the /api/reports endpoints using example_gramps."""

import unittest
from mimetypes import types_map

from gramps_webapi.const import REPORT_DEFAULTS

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_invalid_syntax,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/reports/"


class TestReports(unittest.TestCase):
    """Test cases for the /api/reports endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_reports_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_reports_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "Report")

    def test_get_reports_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?test=1")


class TestReportsReportId(unittest.TestCase):
    """Test cases for the /api/reports/{report_id} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_reports_report_id_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "ancestor_report")

    def test_get_reports_report_id_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL + "ancestor_report", "Report")

    def test_get_reports_report_id_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "no_real_report")

    def test_get_reports_report_id_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "ancestor_report?test=1")


class TestReportsReportIdFile(unittest.TestCase):
    """Test cases for the /api/reports/{report_id}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_reports_report_id_file_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "ancestor_report/file")

    def test_get_reports_report_id_file_expected_result(self):
        """Test response for a fetching a specific report."""
        rv = check_success(self, TEST_URL + "ancestor_report/file", full=True)
        mime_type = "." + REPORT_DEFAULTS[0]
        self.assertEqual(rv.mimetype, types_map[mime_type])

    def test_get_reports_report_id_file_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "no_real_report/file")

    def test_get_reports_report_id_file_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "ancestor_report/file?test=1")

    def test_get_reports_report_id_file_parameter_options_validate_syntax(self):
        """Test invalid options syntax."""
        check_invalid_syntax(self, TEST_URL + "ancestor_report/file?options={1: 2}")

    def test_get_reports_report_id_file_parameter_options_validate_semantics(self):
        """Test invalid options parameters and values."""
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"one_three": "four_two"}',
        )

    def test_get_reports_report_id_file_parameter_options_validate_semantics_booleans(
        self,
    ):
        """Test options parameter boolean validation."""
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"incl_private": "Baloney"}',
        )
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"incl_private": true}',
        )
        check_success(
            self,
            TEST_URL + 'ancestor_report/file?options={"incl_private": "True"}',
        )

    def test_get_reports_report_id_file_parameter_options_validate_semantics_numbers(
        self,
    ):
        """Test options parameter number validation."""
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"maxgen": "two"}',
        )
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"maxgen": 2}',
        )
        check_success(
            self,
            TEST_URL + 'ancestor_report/file?options={"maxgen": "2"}',
        )

    def test_get_reports_report_id_file_parameter_options_validate_semantics_lists(
        self,
    ):
        """Test options parameter list item validation."""
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"papero": "5"}',
        )
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"papero": 0}',
        )
        check_success(
            self,
            TEST_URL + 'ancestor_report/file?options={"papero": "0"}',
        )

    def test_get_reports_report_id_file_parameter_options_output_file_option(self):
        """Test options parameter output file handling as invalid in this context."""
        check_invalid_semantics(
            self,
            TEST_URL + 'ancestor_report/file?options={"of": "/tmp/junk.dat"}',
        )

    def test_get_reports_report_id_file_parameter_options_output_format_option(self):
        """Test options parameter output format selection working."""
        rv = check_success(
            self, TEST_URL + 'ancestor_report/file?options={"off": "odt"}', full=True
        )
        self.assertEqual(rv.mimetype, types_map[".odt"])

    def test_get_reports_report_id_file_one_of_each(self):
        """Test one of each available report."""
        # note some reports have unidentified mandatory options with no defaults
        test_options = {
            "familylines_graph": '?options={"gidlist": "I0044"}',
            "place_report": '?options={"places": "P0863"}',
        }
        rv_set = check_success(self, TEST_URL)
        bad_reports = []
        header = fetch_header(self.client)
        for report in rv_set:
            options = test_options.get(report["id"]) or ""
            rv = self.client.get(
                TEST_URL + report["id"] + "/file" + options, headers=header
            )
            if rv.status_code != 200:
                bad_reports.append(report["id"])
        self.assertEqual(bad_reports, [])
