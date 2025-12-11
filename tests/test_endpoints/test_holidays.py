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


from . import BASE_URL
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/holidays/"


class TestHolidays:
    """Test cases for the /api/holidays/ endpoint."""

    def test_get_holidays_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_holidays_expected_result(self, test_adapter):
        """Test expected result."""
        rv = check_success(test_adapter, TEST_URL)
        assert rv[0] == "Bulgaria"

    def test_get_holidays_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?junk=1")


class TestHoliday:
    """Test cases for the /api/holidays/{country}/{year}/{month}/{day} endpoint."""

    def test_get_holidays_day_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "United States of America/2020/1/1")

    def test_get_holidays_day_expected_result(self, test_adapter):
        """Test response for valid request."""
        rv = check_success(test_adapter, TEST_URL + "United States of America/2020/1/1")
        assert rv == ["New Year's Day"]

    def test_get_holidays_day_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "Somewhere/2020/1/1")
        check_resource_missing(test_adapter, TEST_URL + "United Slates of America/2020/1/1")
        check_resource_missing(test_adapter, TEST_URL + "United Slates of America/beta/1/1")
        check_resource_missing(test_adapter, TEST_URL + "United States of America/2020/abc/1")
        check_resource_missing(test_adapter, TEST_URL + "United States of America/2020/1/abc")

    def test_get_holidays_day_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "United States of America/2020/13/1")
        check_invalid_semantics(test_adapter, TEST_URL + "United States of America/2020/1/32")
