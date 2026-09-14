#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests that paginated object lists are consistent with unpaginated ones.

A single page without filters is sorted without loading all objects, while
unpaginated requests load all objects, so this compares the two code paths.
When sorting a single page by keys available from the raw object data, ties
are broken by handle rather than by the default sort order.
"""

import unittest
from unittest.mock import patch

from gramps.gen.errors import HandleError

from gramps_webapi.api.resources.base import GrampsObjectResourceHelper
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

RAW_SORT_KEYS = {"change", "gramps_id", "private"}

GENERIC_SORTS = [
    "",
    "-change",
    "gramps_id",
    "-gramps_id",
    "private",
    "change,-gramps_id",
    "-private,change",
]

SORTS = {
    "people": GENERIC_SORTS + ["surname", "-birth"],
    "families": GENERIC_SORTS + ["surname"],
    "events": GENERIC_SORTS + ["date"],
    "places": GENERIC_SORTS + ["title"],
    "citations": GENERIC_SORTS,
    "sources": GENERIC_SORTS + ["title"],
    "repositories": GENERIC_SORTS,
    "media": GENERIC_SORTS,
    "notes": GENERIC_SORTS,
    "tags": ["", "-change", "change,-name"],
}


def is_raw_sort(sort: str) -> bool:
    """Return whether all sort keys are available from the raw object data."""
    return bool(sort) and all(
        sort_key.lstrip("-") in RAW_SORT_KEYS for sort_key in sort.split(",")
    )


class TestPagingSort(unittest.TestCase):
    """Test that single pages match slices of the full sorted list."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def _get(self, url, header):
        rv = self.client.get(url, headers=header)
        self.assertEqual(rv.status_code, 200, url)
        return rv

    def _expected_handles(self, endpoint, sort, items, header):
        """Get the expected order of handles for a single page."""
        if not is_raw_sort(sort):
            return [obj["handle"] for obj in items]
        gramps_id_rank = {}
        if "gramps_id" in sort:
            # gramps_id is unique, so its sort order is well-defined
            url = f"{BASE_URL}/{endpoint}/?keys=handle&sort=gramps_id"
            gramps_id_rank = {
                obj["handle"]: index
                for index, obj in enumerate(self._get(url, header).json)
            }
        expected = sorted(items, key=lambda obj: obj["handle"])
        for sort_key in sort.split(","):
            name = sort_key.lstrip("-")
            if name == "gramps_id":
                key = lambda obj: gramps_id_rank[obj["handle"]]
            else:
                key = lambda obj, name=name: obj[name]
            expected.sort(key=key, reverse=sort_key.startswith("-"))
        return [obj["handle"] for obj in expected]

    def _check_pages(self, role):
        header = fetch_header(self.client, role=role)
        for endpoint, sorts in SORTS.items():
            for sort in sorts:
                with self.subTest(endpoint=endpoint, sort=sort, role=role):
                    url = f"{BASE_URL}/{endpoint}/?keys=handle,change,private"
                    if sort:
                        url += f"&sort={sort}"
                    items = self._get(url, header).json
                    expected = self._expected_handles(endpoint, sort, items, header)
                    pagesize = max(len(expected) // 3, 1)
                    for page in [1, 2, 4]:
                        rv = self._get(f"{url}&page={page}&pagesize={pagesize}", header)
                        offset = (page - 1) * pagesize
                        self.assertEqual(
                            [obj["handle"] for obj in rv.json],
                            expected[offset : offset + pagesize],
                        )
                        self.assertEqual(
                            rv.headers["X-Total-Count"], str(len(expected))
                        )

    def test_pages_match_full_list_owner(self):
        """Test pages for a user with access to private records."""
        self._check_pages(ROLE_OWNER)

    def test_pages_match_full_list_guest(self):
        """Test pages for a user without access to private records."""
        self._check_pages(ROLE_GUEST)

    def test_invalid_sort_key_with_page(self):
        """Test an invalid sort key is rejected also for a single page."""
        header = fetch_header(self.client)
        rv = self.client.get(
            f"{BASE_URL}/tags/?sort=gramps_id&page=1&pagesize=5", headers=header
        )
        self.assertEqual(rv.status_code, 422)

    def test_object_deleted_while_loading_page(self):
        """Test objects deleted after sorting the handles are skipped."""
        header = fetch_header(self.client)
        url = f"{BASE_URL}/people/?keys=handle&sort=-change&page=1&pagesize=5"
        # different keys, so the request below is not served from the cache
        rv = self._get(url.replace("keys=handle", "keys=handle,change"), header)
        handles = [obj["handle"] for obj in rv.json]
        original = GrampsObjectResourceHelper.get_object_from_handle

        def get_object_from_handle(resource, handle):
            if handle == handles[0]:
                raise HandleError(f"Handle {handle} not found")
            return original(resource, handle)

        with patch.object(
            GrampsObjectResourceHelper, "get_object_from_handle", get_object_from_handle
        ):
            rv = self._get(url, header)
        self.assertEqual([obj["handle"] for obj in rv.json], handles[1:])
