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

"""Tests for the /api/facts endpoint using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/facts/"


class TestFacts(unittest.TestCase):
    """Test cases for the /api/facts/ endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_records_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_records_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "RecordFact")

    def test_get_records_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?test=1")

    def test_get_records_expected_result(self):
        """Test expected response."""
        rv = check_success(self, TEST_URL)
        self.assertEqual(rv[0]["objects"][0]["handle"], "9BXKQC1PVLPYFMD6IX")
        
    def test_get_records_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?locale", check="base")

    def test_get_records_parameter_locale_expected_results(self):
        """Test locale parameter."""
        rv = check_success(self, TEST_URL + "?locale=de")
        self.assertEqual(rv[0]["description"], "Jüngste lebende Person")
        self.assertIn("Jahre", rv[0]["objects"][0]["value"])

    def test_get_records_parameter_rank_validate_semantics(self):
        """Test invalid rank parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?rank", check="number")

    def test_get_records_parameter_rank_expected_result(self):
        """Test rank parameter."""
        rv = check_success(self, TEST_URL + "?rank=3")
        self.assertEqual(len(rv[0]["objects"]), 3)

    def test_get_records_parameter_private_validate_semantics(self):
        """Test invalid private parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?private", check="boolean")

    def test_get_records_parameter_private_expected_result(self):
        """Test private parameter."""
        # best we can do is check we get a valid response
        check_success(self, TEST_URL + "?private=1")

    def test_get_records_parameter_living_validate_semantics(self):
        """Test invalid living parameter with bad filter."""
        check_invalid_semantics(self, TEST_URL + "?living=NoOneReal")

    def test_get_records_parameter_living_include_all(self):
        """Test living parameter with include all filter."""
        check_success(self, TEST_URL + "?living=IncludeAll")

    def test_get_records_parameter_living_full_name_only(self):
        """Test living parameter with full name only filter."""
        check_success(self, TEST_URL + "?living=FullNameOnly")

    def test_get_records_parameter_living_last_name_only(self):
        """Test living parameter with last name only filter."""
        check_success(self, TEST_URL + "?living=LastNameOnly")

    def test_get_records_parameter_living_replace_complete_name(self):
        """Test living parameter with replace complete name filter."""
        check_success(self, TEST_URL + "?living=ReplaceCompleteName")

    def test_get_records_parameter_living_exclude_all(self):
        """Test living parameter with exclude all filter."""
        check_success(self, TEST_URL + "?living=ExcludeAll")

    def test_get_records_parameter_person_validate_semantics(self):
        """Test invalid person parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?person=Descendants")
        check_invalid_semantics(self, TEST_URL + "?gramps_id=I0044")
        check_invalid_semantics(self, TEST_URL + "?handle=GNUJQCL9MD64AM56OH")

    def test_get_records_parameter_person_descendant_with_gramps_id(
        self,
    ):
        """Test person parameter descendant filter with gramps id."""
        check_success(
            self,
            TEST_URL + "?person=Descendants&gramps_id=I0044",
        )

    def test_get_records_parameter_person_descendant_with_handle(self):
        """Test person parameter descendant filter with handle."""
        check_success(
            self,
            TEST_URL + "?person=Descendants&handle=GNUJQCL9MD64AM56OH",
        )

    def test_get_records_parameter_person_descendant_families(self):
        """Test person parameter descendant families filter."""
        check_success(
            self,
            TEST_URL + "?person=DescendantFamilies&gramps_id=I0044",
        )

    def test_get_records_parameter_person_ancestor_families(self):
        """Test person parameter ancestors filter."""
        check_success(
            self,
            TEST_URL + "?person=Ancestors&gramps_id=I0044",
        )

    def test_get_records_parameter_person_common_ancestor_families(
        self,
    ):
        """Test person parameter common ancestors filter."""
        check_success(
            self,
            TEST_URL + "?person=CommonAncestor&gramps_id=I0044",
        )

    def test_get_records_parameter_person_custom_filter(self):
        """Test person parameter custom filter."""
        header = fetch_header(self.client)
        payload = {
            "comment": "Test records person custom filter",
            "name": "RecordsPersonCustomFilter",
            "rules": [{"name": "IsMale"}],
        }
        rv = self.client.post(
            BASE_URL + "/filters/people", json=payload, headers=header
        )
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, BASE_URL + "/filters/people/RecordsPersonCustomFilter")
        rv = check_success(
            self,
            TEST_URL + "?person=RecordsPersonCustomFilter&gramps_id=I0044",
            full=True,
        )
        self.assertNotIn(b"02NKQC5GOZFLSUSMW3", rv.data)
        header = fetch_header(self.client)
        rv = self.client.delete(
            BASE_URL + "/filters/people/RecordsPersonCustomFilter", headers=header
        )
        self.assertEqual(rv.status_code, 200)

    def test_get_records_parameter_person_missing_custom_filter(self):
        """Test person parameter missing custom filter."""
        check_invalid_semantics(
            self,
            TEST_URL + "?person=SomeFakeCustomFilter&gramps_id=I0044",
        )
