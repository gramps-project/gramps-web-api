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

"""Tests for the /api/living endpoints using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/living/"


class TestLiving(unittest.TestCase):
    """Test cases for the /api/living/{handle} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_living_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "9BXKQC1PVLPYFMD6IX")

    def test_get_living_expected_result(self):
        """Test request produces expected result."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX")
        self.assertEqual(rv, {"living": True})

    def test_get_living_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6I")

    def test_get_living_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "9BXKQC1PVLPYFMD6IX?junk=1")

    def test_get_living_parameter_average_generation_gap_validate_sematics(self):
        """Test invalid average generation gap parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX?average_generation_gap",
            check="number",
        )

    def test_get_living_parameter_max_age_probably_alive_validate_sematics(self):
        """Test invalid max age probably alive parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX?max_age_probably_alive",
            check="number",
        )

    def test_get_living_parameter_max_sibling_age_difference_validate_sematics(self):
        """Test invalid max age probably alive parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX?max_age_probably_alive",
            check="number",
        )


class TestLivingDates(unittest.TestCase):
    """Test cases for the /api/living/{handle}/dates endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_living_dates_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/dates")

    def test_get_living_dates_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/dates", "LivingDates"
        )

    def test_get_living_dates_expected_result(self):
        """Test response for valid request."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/dates")
        self.assertEqual(rv["birth"], "1999-04-11")
        self.assertEqual(rv["death"], "2109-04-11")
        self.assertEqual(
            rv["explain"],
            "Direct evidence for this person - birth: date, death: offset from birth date",
        )

    def test_get_living_dates_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6I/dates")

    def test_get_living_dates_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?junk=1")

    def test_get_living_dates_parameter_average_generation_gap_validate_sematics(self):
        """Test invalid average generation gap parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?average_generation_gap",
            check="number",
        )

    def test_get_living_dates_parameter_max_age_probably_alive_validate_sematics(self):
        """Test invalid max age probably alive parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?max_age_probably_alive",
            check="number",
        )

    def test_get_living_dates_parameter_max_sibling_age_difference_validate_sematics(
        self,
    ):
        """Test invalid max age probably alive parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?max_age_probably_alive",
            check="number",
        )

    def test_get_living_dates_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?locale",
            check="base",
        )

    def test_get_living_dates_parameter_locale_expected_result(self):
        """Test locale parameter working as expected."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/dates?locale=de")
        self.assertEqual(rv["birth"], "1999-04-11")
        self.assertEqual(rv["death"], "2109-04-11")
