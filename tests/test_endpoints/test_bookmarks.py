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

"""Tests for the /api/bookmarks endpoints using example_gramps."""

import unittest

from . import BASE_URL, get_test_client, ROLE_MEMBER
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/bookmarks/"


class TestBookmarks(unittest.TestCase):
    """Test cases for the /api/bookmarks endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_bookmarks_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_bookmarks_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "Bookmarks")

    def test_get_bookmarks_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?query")


class TestBookmarksNameSpace(unittest.TestCase):
    """Test cases for the /api/bookmarks/{namespace} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_bookmarks_namespace_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "families")

    def test_get_bookmarks_namespace_expected_result(self):
        """Test normal response."""
        rv = check_success(self, TEST_URL + "families")
        self.assertEqual(rv, ["9OUJQCBOHW9UEK9CNV"])

    def test_get_bookmarks_namespace_missing_content(self):
        """Test response for missing namespace."""
        check_resource_missing(self, TEST_URL + "missing")

    def test_get_bookmarks_namespace_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "families?query")

    def test_add_and_remove_bookmarks(self):
        for namespace in [
            "citations",
            "events",
            "families",
            "media",
            "notes",
            "people",
            "places",
            "repositories",
            "sources",
        ]:
            # fetch bookmarks
            rv = check_success(self, f"{TEST_URL}{namespace}")
            original = rv

            # find an object that is not bookmarked
            rv = check_success(self, f"{BASE_URL}/{namespace}/")
            for obj in rv:
                if obj["handle"] not in original:
                    new_handle = obj["handle"]
                    break

            # add bookmark
            header = fetch_header(self.client)
            header_member = fetch_header(self.client, role=ROLE_MEMBER)

            # this shouldn't work
            rv = self.client.put(
                f"{TEST_URL}{namespace}/{new_handle}", headers=header_member
            )
            assert rv.status_code == 403
            rv = check_success(self, f"{TEST_URL}{namespace}")
            assert rv == original

            # this should work
            rv = self.client.put(f"{TEST_URL}{namespace}/{new_handle}", headers=header)
            assert rv.status_code == 200
            rv = check_success(self, f"{TEST_URL}{namespace}")
            assert rv == original + [new_handle]

            # delete again

            # this shouldn't work
            rv = self.client.delete(
                f"{TEST_URL}{namespace}/{new_handle}", headers=header_member
            )
            assert rv.status_code == 403
            rv = check_success(self, f"{TEST_URL}{namespace}")
            assert rv == original + [new_handle]

            # this should work
            rv = self.client.delete(
                f"{TEST_URL}{namespace}/{new_handle}", headers=header
            )
            assert rv.status_code == 200
            rv = check_success(self, f"{TEST_URL}{namespace}")
            assert rv == original
