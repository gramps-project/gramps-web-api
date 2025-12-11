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

"""Tests for the /api/types endpoints using example_gramps."""


from . import BASE_URL
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/types/"


class TestTypes:
    """Test cases for the /api/types endpoint."""

    def test_get_types_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL)

    def test_get_types_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL, "Types")

    def test_get_types_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "?test=1")


class TestDefaultTypes:
    """Test cases for the /api/types/default endpoints."""

    def test_get_types_default_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "default/")

    def test_get_types_default_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL + "default/", "DefaultTypes")

    def test_get_types_default_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "default/?test=1")

    def test_get_types_default_type_requires_token(self, test_adapter):
        """Test authorization required."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_requires_token(test_adapter, TEST_URL + "default/" + item)

    def test_get_types_default_type_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_invalid_semantics(test_adapter, TEST_URL + "default/" + item + "?test=1")

    def test_get_types_default_type_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "default/junk")

    def test_get_types_default_type_expected_result(self, test_adapter):
        """Test response for default types type listing."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_success(test_adapter, TEST_URL + "default/" + item)

    def test_get_types_default_type_map_requires_token(self, test_adapter):
        """Test authorization required."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_requires_token(test_adapter, TEST_URL + "default/" + item + "/map")

    def test_get_types_default_type_map_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_invalid_semantics(test_adapter, TEST_URL + "default/" + item + "?test=1")

    def test_get_types_default_type_map_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "default/junk/map")
        check_resource_missing(test_adapter, TEST_URL + "default/event_types/junk")

    def test_get_types_default_type_map_expected_result(self, test_adapter):
        """Test response for default types type map listing."""
        type_list = check_success(test_adapter, TEST_URL + "default/")
        for item in type_list:
            check_success(test_adapter, TEST_URL + "default/" + item + "/map")


class TestCustomTypes:
    """Test cases for the /api/types/custom endpoints."""

    def test_get_types_custom_requires_token(self, test_adapter):
        """Test authorization required."""
        check_requires_token(test_adapter, TEST_URL + "custom/")

    def test_get_types_custom_conforms_to_schema(self, test_adapter):
        """Test conforms to schema."""
        check_conforms_to_schema(test_adapter, TEST_URL + "custom/", "CustomTypes")

    def test_get_types_custom_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        check_invalid_semantics(test_adapter, TEST_URL + "custom/?test=1")

    def test_get_types_custom_type_requires_token(self, test_adapter):
        """Test authorization required."""
        type_list = check_success(test_adapter, TEST_URL + "custom/")
        for item in type_list:
            check_requires_token(test_adapter, TEST_URL + "custom/" + item)

    def test_get_types_custom_type_invalid_semantics(self, test_adapter):
        """Test invalid parameters and values."""
        type_list = check_success(test_adapter, TEST_URL + "custom/")
        for item in type_list:
            check_invalid_semantics(test_adapter, TEST_URL + "custom/" + item + "?test=1")

    def test_get_types_custom_type_missing_content(self, test_adapter):
        """Test response for missing content."""
        check_resource_missing(test_adapter, TEST_URL + "custom/junk")

    def test_get_types_custom_type_expected_result(self, test_adapter):
        """Test response for default types type listing."""
        type_list = check_success(test_adapter, TEST_URL + "custom/")
        for item in type_list:
            check_success(test_adapter, TEST_URL + "custom/" + item)
