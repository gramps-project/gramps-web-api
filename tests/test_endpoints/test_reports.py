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

from jsonschema import RefResolver, validate

from gramps_webapi.const import REPORT_DEFAULTS

from . import API_SCHEMA, get_test_client


class TestReports(unittest.TestCase):
    """Test cases for the /api/reports endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_reports_endpoint(self):
        """Test response for reports listing."""
        # check valid response
        result = self.client.get("/api/reports/")
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.json, type([]))
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for report in result.json:
            validate(
                instance=report,
                schema=API_SCHEMA["definitions"]["Report"],
                resolver=resolver,
            )
        # check bad query parm response
        result = self.client.get("/api/reports/?test=1")
        self.assertEqual(result.status_code, 422)


class TestReport(unittest.TestCase):
    """Test cases for the /api/reports/{report_id} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_reports_report_id_endpoint(self):
        """Test response for a specific report."""
        # check response for invalid report
        result = self.client.get("/api/reports/no_real_report")
        self.assertEqual(result.status_code, 404)
        # check response for valid report
        result = self.client.get("/api/reports/ancestor_report")
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.json, type({}))
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Report"],
            resolver=resolver,
        )
        # check bad query parm response
        result = self.client.get("/api/reports/ancestor_report?test=1")
        self.assertEqual(result.status_code, 422)


class TestReportFile(unittest.TestCase):
    """Test cases for the /api/reports/{report_id}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_reports_report_id_file_endpoint(self):
        """Test response for a fetching a specific report."""
        # check response for invalid report
        result = self.client.get("/api/reports/no_real_report/file")
        self.assertEqual(result.status_code, 404)
        # check response for valid report
        result = self.client.get("/api/reports/ancestor_report/file")
        self.assertEqual(result.status_code, 200)
        mime_type = "." + REPORT_DEFAULTS[0]
        self.assertEqual(result.mimetype, types_map[mime_type])
        # check bad query parm response
        result = self.client.get("/api/reports/ancestor_report/file?test=1")
        self.assertEqual(result.status_code, 422)

    def test_reports_report_id_file_options_parm(self):
        """Test options query parameter parsing and validation."""
        # check options parm json parsing error response
        result = self.client.get("/api/reports/ancestor_report/file?options={1: 2}")
        self.assertEqual(result.status_code, 400)
        # check invalid options parm response
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"one_three": "four_two"}'
        )
        self.assertEqual(result.status_code, 422)
        # check a valid options parm response
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"papero": "0"}'
        )
        self.assertEqual(result.status_code, 200)
        # check reponses for some valid options parms but with bad values as we validate
        # the values against the options_help data as best we can
        # - a true/false option
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"incl_private": "Baloney"}'
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"incl_private": true}'
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"incl_private": "True"}'
        )
        self.assertEqual(result.status_code, 200)
        # - a number option
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"maxgen": 2}'
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"maxgen": "2"}'
        )
        self.assertEqual(result.status_code, 200)
        # - a list selection option
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"papero": "5"}'
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"papero": 0}'
        )
        self.assertEqual(result.status_code, 422)
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"papero": "0"}'
        )
        self.assertEqual(result.status_code, 200)
        # check output file option is rejected as invalid in this context
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"of": "/tmp/junk.dat"}'
        )
        self.assertEqual(result.status_code, 422)
        # check different output format accepted and processed properly
        result = self.client.get(
            '/api/reports/ancestor_report/file?options={"off": "odt"}'
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, types_map[".odt"])

    def test_reports_report_id_file_each_one(self):
        """Test one of each available report."""
        # some reports have unidentified mandatory options with no defaults
        test_options = {
            "familylines_graph": '?options={"gidlist": "I0044"}',
            "place_report": '?options={"places": "P0863"}',
        }
        result_set = self.client.get("/api/reports/")
        bad_reports = []
        for report in result_set.json:
            options = test_options.get(report["id"]) or ""
            result = self.client.get("/api/reports/" + report["id"] + "/file" + options)
            if result.status_code != 200:
                bad_reports.append(report["id"])
        self.assertEqual(bad_reports, [])
