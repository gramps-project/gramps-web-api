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

"""Tests for the /api/holidays endpoints using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/holidays/"


class TestHolidays(unittest.TestCase):
    """Test cases for the /api/holidays/ endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_holidays_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_holidays_expected_result(self):
        """Test expected result."""
        rv = check_success(self, TEST_URL)
        self.assertEqual(rv[0], "Bulgaria")

    def test_get_holidays_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk=1")


class TestHoliday(unittest.TestCase):
    """Test cases for the /api/holidays/{country}/{year}/{month}/{day} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_holidays_day_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "United States of America/2020/1/1")

    def test_get_holidays_day_expected_result(self):
        """Test response for valid request."""
        rv = check_success(self, TEST_URL + "United States of America/2020/1/1")
        self.assertEqual(rv, ["New Year's Day"])

    def test_get_holidays_day_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "Somewhere/2020/1/1")
        check_resource_missing(self, TEST_URL + "United Slates of America/2020/1/1")
        check_resource_missing(self, TEST_URL + "United Slates of America/beta/1/1")
        check_resource_missing(self, TEST_URL + "United States of America/2020/abc/1")
        check_resource_missing(self, TEST_URL + "United States of America/2020/1/abc")

    def test_get_holidays_day_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "United States of America/2020/13/1")
        check_invalid_semantics(self, TEST_URL + "United States of America/2020/1/32")
