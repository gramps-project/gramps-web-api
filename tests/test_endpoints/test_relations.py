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

"""Tests for the /api/relations endpoints using example_gramps."""

import pytest

from . import BASE_URL
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/relations/"


class TestRelations:
    """Test cases for the /api/relations/{handle1}/{handle2} endpoint."""

    def test_get_relations_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L"
        )

    def test_get_relations_expected_result(self, test_adapter):
        """Test request produces expected result."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L"
        )
        assert rv == {
            "distance_common_origin": 5,
            "distance_common_other": 1,
            "relationship_string": "second great stepgrandaunt",
        }

    def test_get_relations_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX")
        check_resource_missing(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR1"
        )
        check_resource_missing(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6I/ORFKQC4KLWEGTGR19L"
        )

    def test_get_relations_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?junk=1"
        )

    def test_get_relations_parameter_depth_validate_semantics(self, test_adapter):
        """Test invalid depth parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth",
            check="number",
        )

    def test_get_relations_parameter_depth_expected_result(self, test_adapter):
        """Test depth parameter working as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth=5"
        )
        assert rv["relationship_string"] == ""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth=6"
        )
        assert rv["relationship_string"] == "second great stepgrandaunt"

    def test_get_relations_parameter_locale_validate_semantics(self, test_adapter):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?locale",
            check="base",
        )

    def test_get_relations_parameter_locale_expected_result(self, test_adapter):
        """Test locale parameter working as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L"
        )
        assert rv["relationship_string"] == "second great stepgrandaunt"
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?locale=de"
        )
        assert rv["relationship_string"] == "Stief-/Adoptivalttante"

    def test_get_relations_parameter_locale_expected_result_partner(self, test_adapter):
        """Test locale parameter working as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "cc8205d87831c772e87/cc8205d872f532ab14e"
        )
        assert rv["relationship_string"] == "husband"
        rv = check_success(
            test_adapter, TEST_URL + "cc8205d87831c772e87/cc8205d872f532ab14e?locale=it"
        )
        assert rv["relationship_string"] == "marito"


class TestRelationsAll:
    """Test cases for the /api/relations/{handle1}/{handle2}/all endpoint."""

    def test_get_relations_all_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all"
        )

    def test_get_relations_all_expected_result(self, test_adapter):
        """Test response for valid request."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all"
        )
        assert "common_ancestors" in rv[0]
        assert rv[0]["relationship_string"] == "second great stepgrandaunt"

    def test_get_relations_all_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/all")
        check_resource_missing(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR1/all"
        )
        check_resource_missing(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6I/ORFKQC4KLWEGTGR19L/all"
        )

    def test_get_relations_all_validate_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?junk=1"
        )

    def test_get_relations_all_parameter_depth_validate_semantics(self, test_adapter):
        """Test invalid depth parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth",
            check="number",
        )

    def test_get_relations_all_parameter_depth_expected_result(self, test_adapter):
        """Test depth parameter working as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth=5"
        )
        assert rv == [{}]
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth=6"
        )
        assert rv[0]["relationship_string"] == "second great stepgrandaunt"

    def test_get_relations_all_parameter_locale_validate_semantics(self, test_adapter):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            test_adapter,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?locale",
            check="base",
        )

    def test_get_relations_all_parameter_locale_expected_result(self, test_adapter):
        """Test locale parameter working as expected."""
        rv = check_success(
            test_adapter, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all"
        )
        assert rv[0]["relationship_string"] == "second great stepgrandaunt"
        rv = check_success(
            test_adapter,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?locale=de",
        )
        assert rv[0]["relationship_string"] == "Stief-/Adoptivalttante"
