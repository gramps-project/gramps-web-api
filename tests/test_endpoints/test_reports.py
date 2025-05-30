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

"""Tests for the /api/reports endpoints using example_gramps."""

import os
import unittest
from mimetypes import types_map
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.const import (
    ENV_CONFIG_FILE,
    REPORT_DEFAULTS,
    TEST_EMPTY_GRAMPS_AUTH_CONFIG,
)

from . import BASE_URL, TEST_USERS, get_test_client
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

    def test_get_reports_validate_semantics_without_help(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?include_help")

    def test_get_reports_without_help(self):
        """Test invalid parameters and values."""
        check_success(self, TEST_URL + "?include_help=0")


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

    def test_get_report_id_validate_semantics_without_help(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "ancestor_report?include_help")

    def test_get_report_id_without_help(self):
        """Test invalid parameters and values."""
        check_success(self, TEST_URL + "ancestor_report?include_help=0")


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

    def test_get_reports_report_localized_content(self):
        """Test that localized output works."""
        rv = check_success(
            self,
            TEST_URL + 'ancestor_report/file?options={"off": "tex"}&locale=de',
            full=True,
        )
        contents = rv.get_data(as_text=True)
        assert "Ahnentafel Bericht für" in contents

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

    def test_post_reports_report_id_file_one_of_each(self):
        """Test one of each available report using POST."""
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
            rv = self.client.post(
                TEST_URL + report["id"] + "/file" + options, headers=header
            )
            if rv.status_code != 201:
                bad_reports.append(report["id"])
            assert (
                rv.json["url"]
                == TEST_URL + report["id"] + "/file/processed/" + rv.json["file_name"]
            )
            assert rv.json["file_name"].endswith(rv.json["file_type"])
            rv = self.client.get(rv.json["url"], headers=header)
            if rv.status_code != 200:
                bad_reports.append(report["id"])
        self.assertEqual(bad_reports, [])


class TestReportsEmptyDatabase(unittest.TestCase):
    """Test cases for the /api/reports/ endpoint with an empty database."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "empty2"
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(config_from_env=False, config={"TREE": cls.name})
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        cls.tree = os.path.basename(cls.dbpath)
        with cls.test_app.app_context():
            user_db.create_all()
            for role in TEST_USERS:
                add_user(
                    name=TEST_USERS[role]["name"],
                    password=TEST_USERS[role]["password"],
                    role=role,
                )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_reports_empty_db(self):
        """Test that importers are loaded also for a fresh db."""
        rv = check_success(self, TEST_URL)
        assert len(rv) > 0
