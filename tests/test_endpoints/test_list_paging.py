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

"""Pages of list endpoints must be slices of the full list."""

import unittest

from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

ENDPOINTS = ["people", "events", "citations", "notes", "tags"]
SORTS = [None, "-change", "gramps_id", "-private,change"]


class TestListPaging(unittest.TestCase):
    """Compare pages, sorted in SQL, with the full list, sorted in memory."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_pages_match_full_list(self):
        """Pages and totals equal those of the full list."""
        for role in [ROLE_OWNER, ROLE_GUEST]:
            header = fetch_header(self.client, role=role)
            for endpoint in ENDPOINTS:
                for sort in SORTS:
                    if endpoint == "tags" and sort not in (None, "-change"):
                        continue
                    url = f"{BASE_URL}/{endpoint}/?keys=handle"
                    if sort:
                        url += f"&sort={sort}"
                    with self.subTest(role=role, endpoint=endpoint, sort=sort):
                        rv = self.client.get(url, headers=header)
                        self.assertEqual(rv.status_code, 200)
                        expected = [obj["handle"] for obj in rv.json]
                        for page in [1, 2, len(expected) // 10 + 1, 1000]:
                            rv = self.client.get(
                                f"{url}&page={page}&pagesize=10", headers=header
                            )
                            self.assertEqual(rv.status_code, 200)
                            self.assertEqual(
                                [obj["handle"] for obj in rv.json],
                                expected[(page - 1) * 10 : page * 10],
                            )
                            self.assertEqual(
                                int(rv.headers["X-Total-Count"]), len(expected)
                            )
