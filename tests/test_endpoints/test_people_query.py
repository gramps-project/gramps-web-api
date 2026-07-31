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

"""Tests for the POST /api/people/query/ endpoint using example_gramps."""

import unittest

from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_object_count, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/people/query/"


class TestPeopleQuery(unittest.TestCase):
    """Test cases for the fast, SQL-pushed-down Person query endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def _fetch_all(self, header, body_without_paging, page_size=200):
        """Page through the endpoint via keyset pagination, collecting all rows.

        Needed because example_gramps has more people than the endpoint's
        max `limit` (1000), so a single request can't retrieve everything.
        """
        body = dict(body_without_paging)
        body.setdefault("order_by", [{"column": "handle", "direction": "asc"}])
        body["limit"] = page_size
        items = []
        after = None
        while True:
            if after is not None:
                body["after"] = after
            rv = self.client.post(TEST_URL, json=body, headers=header)
            self.assertEqual(rv.status_code, 200)
            items.extend(rv.json["items"])
            after = rv.json["next_after"]
            if after is None:
                return items

    def test_requires_token(self):
        rv = self.client.post(TEST_URL, json={})
        self.assertEqual(rv.status_code, 401)

    def test_default_query_returns_all_people(self):
        header = fetch_header(self.client)
        items = self._fetch_all(header, {"select": ["handle"]})
        self.assertEqual(len(items), get_object_count("people"))

    def test_select_restricts_returned_columns(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={"select": ["handle", "surname"], "limit": 5},
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        for item in rv.json["items"]:
            self.assertEqual(set(item), {"handle", "surname"})

    def test_where_eq_filters_rows(self):
        header = fetch_header(self.client)
        all_items = self._fetch_all(header, {"select": ["handle"]})
        male_items = self._fetch_all(
            header,
            {
                "select": ["handle"],
                "where": [{"column": "gender", "op": "eq", "value": 1}],
            },
        )
        self.assertGreater(len(male_items), 0)
        self.assertLess(len(male_items), len(all_items))

    def test_unknown_column_in_where_rejected(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={"where": [{"column": "not_a_column", "op": "eq", "value": 1}]},
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)

    def test_unknown_column_in_select_rejected(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL, json={"select": ["not_a_column"]}, headers=header
        )
        self.assertEqual(rv.status_code, 422)

    def test_unknown_column_in_order_by_rejected(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={"order_by": [{"column": "not_a_column"}]},
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)

    def test_in_requires_nonempty_list(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={"where": [{"column": "gender", "op": "in", "value": []}]},
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)

    def test_order_by_surname_is_sorted(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={
                "select": ["surname"],
                "order_by": [{"column": "surname", "direction": "asc"}],
                "limit": 1000,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        surnames = [item["surname"] or "" for item in rv.json["items"]]
        self.assertEqual(surnames, sorted(surnames))

    def test_no_locale_uses_plain_codepoint_order_not_system_locale(self):
        # Regression test: requests without an explicit `locale` must sort by
        # plain codepoint order (matching Python's sorted()), not silently
        # apply the server process's system locale collation. example_gramps
        # includes "Álvarez", which a locale-aware (e.g. en_US) collation
        # sorts near "Alvarez" -- with "A" names -- while codepoint order
        # (and SQLite's default BINARY collation) sorts it after all
        # plain-ASCII names, since 'Á' > 'z' by codepoint.
        header = fetch_header(self.client)
        items = self._fetch_all(
            header,
            {
                "select": ["surname"],
                "order_by": [{"column": "surname", "direction": "asc"}],
            },
        )
        surnames = [item["surname"] or "" for item in items]
        self.assertEqual(surnames, sorted(surnames))
        self.assertIn("Álvarez", surnames)
        # Under codepoint order, "Á" (U+00C1) sorts after all plain-ASCII
        # letters -- so "Álvarez" must come after "Andersen", not be
        # interleaved with the "A" names the way locale-aware collation
        # (which treats "Á" as close to "A") would place it.
        self.assertGreater(surnames.index("Álvarez"), surnames.index("Andersen"))

    def test_keyset_pagination_covers_all_rows_without_overlap(self):
        header = fetch_header(self.client)
        total = get_object_count("people")
        page_size = max(1, total // 3)

        seen_handles = []
        after = None
        for _ in range(total + 1):  # safety bound against an infinite loop
            body = {
                "select": ["handle"],
                "order_by": [{"column": "surname", "direction": "asc"}],
                "limit": page_size,
            }
            if after is not None:
                body["after"] = after
            rv = self.client.post(TEST_URL, json=body, headers=header)
            self.assertEqual(rv.status_code, 200)
            handles = [item["handle"] for item in rv.json["items"]]
            seen_handles.extend(handles)
            after = rv.json["next_after"]
            if after is None:
                break

        self.assertEqual(len(seen_handles), total)
        self.assertEqual(len(set(seen_handles)), total)  # no duplicates/overlap

    def test_invalid_after_cursor_rejected(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={"after": "does-not-exist"},
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)

    def test_limit_out_of_range_rejected(self):
        header = fetch_header(self.client)
        rv = self.client.post(TEST_URL, json={"limit": 0}, headers=header)
        self.assertEqual(rv.status_code, 422)
        rv = self.client.post(TEST_URL, json={"limit": 100000}, headers=header)
        self.assertEqual(rv.status_code, 422)

    def test_locale_sort_returns_sorted_results(self):
        header = fetch_header(self.client)
        items = self._fetch_all(
            header,
            {
                "select": ["surname"],
                "order_by": [{"column": "surname", "direction": "asc"}],
                "locale": "de",
            },
        )
        # Locale collation can reorder relative to a plain Python sort (e.g.
        # accented characters), so just confirm the request succeeds and
        # returns every row -- exact ordering under German collation isn't
        # asserted here.
        self.assertEqual(len(items), get_object_count("people"))

    def test_unrecognized_locale_falls_back_to_default(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={
                "select": ["handle"],
                "order_by": [{"column": "surname", "direction": "asc"}],
                "locale": "zz",
                "limit": 5,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)

    def test_locale_sort_does_not_apply_collate_to_non_text_columns(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={
                "select": ["handle"],
                "order_by": [{"column": "gender", "direction": "asc"}],
                "locale": "de",
                "limit": 5,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)

    def test_private_people_excluded_without_permission(self):
        # ROLE_GUEST lacks PERM_VIEW_PRIVATE; ROLE_OWNER has it. (ROLE_MEMBER
        # is *not* a valid "lacks PERM_VIEW_PRIVATE" role in this codebase --
        # PERMISSIONS[ROLE_MEMBER] already grants it, per auth/const.py.)
        header_owner = fetch_header(self.client, role=ROLE_OWNER)
        header_guest = fetch_header(self.client, role=ROLE_GUEST)

        # example_gramps ships with no private people, so create one --
        # otherwise this check would pass vacuously regardless of whether
        # privacy filtering actually works.
        handle = "test_query_private_person"
        rv = self.client.post(
            BASE_URL + "/people/",
            json={"_class": "Person", "handle": handle, "private": True},
            headers=header_owner,
        )
        self.assertEqual(rv.status_code, 201)
        try:
            owner_items = self._fetch_all(header_owner, {"select": ["handle"]})
            guest_items = self._fetch_all(header_guest, {"select": ["handle"]})
            owner_handles = {item["handle"] for item in owner_items}
            guest_handles = {item["handle"] for item in guest_items}

            self.assertIn(handle, owner_handles)
            self.assertNotIn(handle, guest_handles)
            self.assertEqual(len(owner_handles) - len(guest_handles), 1)
        finally:
            self.client.delete(BASE_URL + f"/people/{handle}", headers=header_owner)
