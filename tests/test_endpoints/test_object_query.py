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

"""Smoke tests for the non-Person `POST .../query/` endpoints.

`test_people_query.py` covers the Person endpoint (and the query AST) in
depth. This file exists to prove the generalization to the other nine object
types actually works end-to-end through real HTTP requests, not just through
`ObjectTypeSpec`/`compile_query()` unit tests -- each type is wired to its
own database table, whitelist, and privacy behavior.
"""

import unittest

from . import BASE_URL, get_object_count, get_test_client
from .util import fetch_header

# (url, object-count key, a real text-typed select column for that type)
TYPES = [
    ("/families/query/", "families", "father_handle"),
    ("/events/query/", "events", "description"),
    ("/places/query/", "places", "title"),
    ("/repositories/query/", "repositories", "name"),
    ("/sources/query/", "sources", "title"),
    ("/citations/query/", "citations", "page"),
    ("/notes/query/", "notes", "gramps_id"),
    ("/tags/query/", "tags", "name"),
]


class TestObjectQueryOtherTypes(unittest.TestCase):
    """Basic wiring checks for each non-Person, non-Media query endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def _fetch_all(self, header, url, body_without_paging, page_size=200):
        """Page through an endpoint via keyset pagination, collecting all rows."""
        body = dict(body_without_paging)
        body["limit"] = page_size
        items = []
        after = None
        while True:
            if after is not None:
                body["after"] = after
            rv = self.client.post(BASE_URL + url, json=body, headers=header)
            self.assertEqual(rv.status_code, 200)
            items.extend(rv.json["items"])
            after = rv.json["next_after"]
            if after is None:
                return items

    def test_each_type_returns_full_count_with_correct_columns(self):
        header = fetch_header(self.client)
        for url, count_key, column in TYPES:
            with self.subTest(url=url):
                items = self._fetch_all(header, url, {"select": ["handle", column]})
                self.assertEqual(len(items), get_object_count(count_key))
                for item in items:
                    self.assertEqual(set(item), {"handle", column})

    def test_each_type_rejects_unknown_column(self):
        header = fetch_header(self.client)
        for url, _count_key, _column in TYPES:
            with self.subTest(url=url):
                rv = self.client.post(
                    BASE_URL + url,
                    json={"select": ["not_a_real_column"]},
                    headers=header,
                )
                self.assertEqual(rv.status_code, 422)

    def test_each_type_requires_token(self):
        for url, _count_key, _column in TYPES:
            with self.subTest(url=url):
                rv = self.client.post(BASE_URL + url, json={})
                self.assertEqual(rv.status_code, 401)


class TestObjectQueryTag(unittest.TestCase):
    """Tag is the one type with no `private` secondary column."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tag_query_works_without_a_private_column(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            BASE_URL + "/tags/query/",
            json={"select": ["handle", "name"], "limit": 1000},
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["items"]), get_object_count("tags"))

    def test_private_is_not_a_selectable_tag_column(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            BASE_URL + "/tags/query/",
            json={"select": ["private"]},
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)


class TestObjectQueryMedia(unittest.TestCase):
    """Media has a `desc` column -- a reserved word on PostgreSQL.

    Regression coverage for `query.py`'s `_quote_column()`: selecting,
    filtering, and sorting by `desc` must not break the generated SQL.
    """

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_select_desc_column(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            BASE_URL + "/media/query/",
            json={"select": ["handle", "desc"], "limit": 1000},
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["items"]), get_object_count("media"))
        for item in rv.json["items"]:
            self.assertEqual(set(item), {"handle", "desc"})

    def test_order_by_desc_column(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            BASE_URL + "/media/query/",
            json={
                "select": ["desc"],
                "order_by": [{"column": "desc", "direction": "asc"}],
                "limit": 1000,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
        descs = [item["desc"] or "" for item in rv.json["items"]]
        self.assertEqual(descs, sorted(descs))

    def test_where_desc_column(self):
        header = fetch_header(self.client)
        rv = self.client.post(
            BASE_URL + "/media/query/",
            json={
                "select": ["handle"],
                "where": [{"column": "desc", "op": "ne", "value": ""}],
                "limit": 1000,
            },
            headers=header,
        )
        self.assertEqual(rv.status_code, 200)
