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

"""Tests for the `gramps_webapi.api` module.

This module contains only constants and schema definitions that are used by
both pytest-based and unittest-based tests.

For unittest-based tests, the setUpModule() function has been moved to
unittest_setup.py to avoid triggering database setup when pytest tests
import from this package.

TODO: Once all tests are converted to pytest, this can be further simplified.
"""

from importlib.resources import as_file, files

import yaml
from jsonschema import RefResolver

from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)

# Load API schema for validation
ref = files("gramps_webapi") / "data/apispec.yaml"
with as_file(ref) as file_path:
    with open(file_path, encoding="utf-8") as file_handle:
        API_SCHEMA = yaml.safe_load(file_handle)

API_RESOLVER = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})

# Base URL for API endpoints
BASE_URL = "/api"

# Test users with different roles
TEST_USERS = {
    ROLE_ADMIN: {"name": "admin", "password": "ghi"},
    ROLE_OWNER: {"name": "owner", "password": "123"},
    ROLE_EDITOR: {"name": "editor", "password": "abc"},
    ROLE_MEMBER: {"name": "member", "password": "456"},
    ROLE_GUEST: {"name": "guest", "password": "def"},
}

# Re-export functions from unittest_setup for backward compatibility
# These will only work for unittest-based tests that call setUpModule()
from .unittest_setup import get_object_count, get_test_client, setUpModule

__all__ = [
    "API_SCHEMA",
    "API_RESOLVER",
    "BASE_URL",
    "TEST_USERS",
    "get_object_count",
    "get_test_client",
    "setUpModule",
]
