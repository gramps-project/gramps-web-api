#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Douglas Blank
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
from unittest.mock import patch

from gramps.gen.proxy.proxybase import ProxyDbBase

from gramps_webapi.api.resources.object_query import run_query as _real_run_query
from gramps_webapi.api.util import get_db_handle
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_object_count, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/people/query/"


class _FakeNonPrivateProxy(ProxyDbBase):
    """Minimal stand-in for a non-privacy proxy (e.g. `LivingProxyDb`).

    Deliberately skips `ProxyDbBase.__init__`'s bookmark/name-format wiring
    -- it only needs to be recognized as *some* `ProxyDbBase`, to exercise
    the endpoint's proxied dispatch path. Defines no `include_*`/`sanitize_*`
    overrides of its own, so `ProxyDbBase`'s own defaults (pass everything
    through) apply -- this proxy filters nothing, so a query through it
    should return exactly what an unproxied query would.
    """

    def __init__(self, db):
        self.db = self.basedb = db


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

    def test_non_private_proxy_database_routes_through_proxied_path(self):
        # get_db_handle() never actually constructs anything other than the
        # raw db or a PrivateProxyDb today -- but the endpoint must not
        # *assume* that. Any `ProxyDbBase` (e.g. a future LivingProxyDb)
        # must be queryable correctly: dispatch goes through Gramps' own
        # Filter/Rule machinery (proxied_query.run_query) rather than a
        # second, SQL-side reimplementation of that proxy's rules -- so
        # results reflect whatever *this* proxy actually filters, not a
        # hardcoded assumption about which proxy types are "safe" to bypass.
        header = fetch_header(self.client)

        def fake_get_db_handle(readonly=True):
            db = get_db_handle(readonly=readonly)
            base = db.basedb if isinstance(db, ProxyDbBase) else db
            return _FakeNonPrivateProxy(base)

        with patch(
            "gramps_webapi.api.resources.object_query.get_db_handle",
            side_effect=fake_get_db_handle,
        ):
            items = self._fetch_all(header, {"select": ["handle"]})
        # This fake proxy filters nothing, so it must match the unproxied
        # SQL path's result exactly.
        self.assertEqual(len(items), get_object_count("people"))

    def test_default_query_returns_all_people(self):
        header = fetch_header(self.client)
        items = self._fetch_all(header, {"select": ["handle"]})
        self.assertEqual(len(items), get_object_count("people"))

    def test_total_count_omitted_by_default(self):
        # Matches the rest of the API's convention (objects.py/emit.py/
        # history.py): total count is an X-Total-Count response header, not
        # a body field -- and it's opt-in here since, unlike those endpoints,
        # it costs a genuinely separate COUNT(*) query.
        header = fetch_header(self.client)
        rv = self.client.post(TEST_URL, json={"limit": 5}, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn("X-Total-Count", rv.headers)

    def test_total_count_reflects_all_matching_rows_not_just_this_page(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL, json={"select": ["handle"], "limit": 5, "count": True}, headers=header
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["items"]), 5)  # capped by limit
        self.assertEqual(int(rv.headers["X-Total-Count"]), get_object_count("people"))

    def test_total_count_respects_where_filter(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            TEST_URL,
            json={
                "select": ["handle"],
                "where": [{"column": "gender", "op": "eq", "value": 1}],
                "limit": 5,
                "count": True,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        all_items = self._fetch_all(header, {"select": ["handle"]})
        total_count = int(rv.headers["X-Total-Count"])
        self.assertGreater(total_count, 0)
        self.assertLess(total_count, len(all_items))

    def test_total_count_stable_across_pages(self):
        header = fetch_header(self.client)
        body = {
            "select": ["handle"],
            "order_by": [{"column": "handle", "direction": "asc"}],
            "limit": 5,
            "count": True,
        }
        rv1 = self.client.post(TEST_URL, json=body, headers=header)
        body_page2 = dict(body, after=rv1.json["next_after"])
        rv2 = self.client.post(TEST_URL, json=body_page2, headers=header)
        self.assertEqual(rv1.headers["X-Total-Count"], rv2.headers["X-Total-Count"])
        self.assertEqual(int(rv1.headers["X-Total-Count"]), get_object_count("people"))

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

    def test_next_after_is_null_when_page_exactly_exhausts_results(self):
        # Regression test: a naive `len(rows) == limit` check can't tell "the
        # last page happens to be full" apart from "there's another page
        # coming", forcing a wasted follow-up request. Asking for exactly
        # as many rows as match in one page must report no next page.
        # Filtered to gender == FEMALE since example_gramps has more people
        # than the endpoint's max `limit` (1000) -- a where filter is needed
        # to get a matching count small enough to request in a single page.
        header = fetch_header(self.client)
        where = [{"column": "gender", "op": "eq", "value": 0}]
        probe = self.client.post(
            TEST_URL,
            json={"select": ["handle"], "where": where, "limit": 1, "count": True},
            headers=header,
        )
        self.assertEqual(probe.status_code, 200)
        total = int(probe.headers["X-Total-Count"])
        self.assertLessEqual(total, 1000)  # fits in a single page

        rv = self.client.post(
            TEST_URL,
            json={
                "select": ["handle"],
                "where": where,
                "order_by": [{"column": "handle", "direction": "asc"}],
                "limit": total,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["items"]), total)
        self.assertIsNone(rv.json["next_after"])

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

    def test_locale_rejected_on_proxied_path(self):
        # The proxied path (`run_query`) sorts in plain Python order with no
        # `COLLATE` equivalent to the SQL path's `locale` param -- silently
        # ignoring `locale` there would return a different sort order than
        # the same request gets when unproxied, depending on the caller's
        # permissions alone. Must be rejected outright instead.
        header = fetch_header(self.client)

        def fake_get_db_handle(readonly=True):
            db = get_db_handle(readonly=readonly)
            base = db.basedb if isinstance(db, ProxyDbBase) else db
            return _FakeNonPrivateProxy(base)

        with patch(
            "gramps_webapi.api.resources.object_query.get_db_handle",
            side_effect=fake_get_db_handle,
        ):
            rv = self.client.post(
                TEST_URL,
                json={
                    "select": ["handle"],
                    "order_by": [{"column": "surname", "direction": "asc"}],
                    "locale": "de",
                    "limit": 5,
                },
                headers=header,
            )
        self.assertEqual(rv.status_code, 422)

    def _count_with_call_tracking(self, header, body):
        """POST to the proxied path, returning (response, run_query call count)."""

        def fake_get_db_handle(readonly=True):
            db = get_db_handle(readonly=readonly)
            base = db.basedb if isinstance(db, ProxyDbBase) else db
            return _FakeNonPrivateProxy(base)

        calls = []

        def counting_run_query(*args, **kwargs):
            calls.append(kwargs)
            return _real_run_query(*args, **kwargs)

        with patch(
            "gramps_webapi.api.resources.object_query.get_db_handle",
            side_effect=fake_get_db_handle,
        ), patch(
            "gramps_webapi.api.resources.object_query.run_query",
            side_effect=counting_run_query,
        ):
            rv = self.client.post(TEST_URL, json=body, headers=header)
        return rv, len(calls)

    def test_proxied_count_reuses_first_page_when_it_is_the_whole_result(self):
        # When the (over-fetched) first page already contains every match --
        # no `after`, and fewer rows came back than the over-fetch asked
        # for -- the total is just `len(rows)`. No need to re-run
        # `run_query` a second time, with no `limit` at all, just to
        # recompute a number the first call already established.
        header = fetch_header(self.client)
        rv, call_count = self._count_with_call_tracking(
            header,
            {
                "select": ["handle"],
                "where": [{"column": "gramps_id", "op": "eq", "value": "I0000"}],
                "limit": 50,
                "count": True,
            },
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(int(rv.headers["X-Total-Count"]), len(rv.json["items"]))
        self.assertEqual(call_count, 1)  # no second, unlimited count query

    def test_proxied_count_still_needs_second_query_when_paginated(self):
        # A page that does *not* already contain every match -- because
        # there are more rows beyond it -- can't infer the total from
        # `rows` alone, and still needs the second, unlimited `run_query`.
        header = fetch_header(self.client)
        rv, call_count = self._count_with_call_tracking(
            header,
            {"select": ["handle"], "limit": 2, "count": True},
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(int(rv.headers["X-Total-Count"]), get_object_count("people"))
        self.assertEqual(call_count, 2)

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
