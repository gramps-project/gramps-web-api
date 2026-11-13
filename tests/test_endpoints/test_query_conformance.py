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

"""Conformance tests for the GOQL syntax the `POST .../query/` endpoints accept.

`where_expr`, `select` and `order_by` are GOQL strings passed through to
gramps-object-query-language, so its grammar is part of this API's
contract. These tests pin that contract: each string below must keep being
accepted, and match the same rows of example_gramps, or keep being
rejected. A GOQL release that changes any of them fails here, before it
reaches clients.

They are not GOQL's own tests. Each case is one representative of a form a
client may have saved, and goes through HTTP on both execution paths (SQL
and proxied), which must agree.

If a case fails after a GOQL upgrade, the change is breaking for clients:
it belongs in ROADMAP.md, not in a quietly updated number here.
"""

import unittest
from unittest.mock import patch

from gramps.gen.proxy.proxybase import ProxyDbBase

from gramps_webapi.api.util import get_db_handle

from . import BASE_URL, get_object_count, get_test_client
from .util import fetch_header

PEOPLE_URL = BASE_URL + "/people/query/"
FAMILIES_URL = BASE_URL + "/families/query/"
EVENTS_URL = BASE_URL + "/events/query/"

# (url, where_expr, env, number of matching rows in example_gramps)
WHERE_CASES = [
    # comparisons and constants
    (PEOPLE_URL, "gender == Person.MALE", None, 1184),
    (PEOPLE_URL, "gender == 1", None, 1184),
    (PEOPLE_URL, "gender != Person.MALE", None, 973),
    (PEOPLE_URL, "surname == 'Garner'", None, 70),
    (PEOPLE_URL, "'Garner' == surname", None, 70),
    (PEOPLE_URL, "birth.date.sortval >= Date('Jan 1, 1900')", None, 457),
    (PEOPLE_URL, "Date('Jan 1, 1900') <= birth.date.sortval", None, 457),
    # boolean logic
    (PEOPLE_URL, "surname == 'Garner' and gender == Person.FEMALE", None, 37),
    (PEOPLE_URL, "surname == 'Garner' or surname == 'Warner'", None, 182),
    (PEOPLE_URL, "not (gender == Person.MALE)", None, 973),
    # a row with no birth date matches neither the condition nor its negation
    (PEOPLE_URL, "not (birth.date.sortval >= Date('Jan 1, 1900'))", None, 920),
    (PEOPLE_URL, "surname == 'Garner' and not (gender == 1 or gender == 2)", None, 37),
    # in, not in, substring, like, regex
    (PEOPLE_URL, "given_name in ['Lewis', 'Anna']", None, 4),
    (PEOPLE_URL, "gender not in [Person.FEMALE, Person.UNKNOWN]", None, 1184),
    (PEOPLE_URL, "'arn' in surname", None, 185),
    (PEOPLE_URL, "'arn' not in surname", None, 1972),
    (PEOPLE_URL, "like(surname, 'garn%')", None, 70),
    (PEOPLE_URL, "regex(surname, '^G.rner$')", None, 70),
    # is / is not
    (PEOPLE_URL, "death.gramps_id is None", None, 1501),
    (PEOPLE_URL, "death.gramps_id is not None", None, 656),
    # relationships, collections, counting
    (PEOPLE_URL, "birth.place.title == death.place.title", None, 1092),
    (PEOPLE_URL, "any(parent_families)", None, 1377),
    (PEOPLE_URL, "len(families) >= 2", None, 51),
    (PEOPLE_URL, "len(events) > 3", None, 4),
    (FAMILIES_URL, "father.surname == 'Garner'", None, 24),
    (FAMILIES_URL, "any(children, gender == Person.FEMALE)", None, 309),
    (FAMILIES_URL, "not any(children)", None, 256),
    # Env
    (PEOPLE_URL, "surname == Env.NAME", {"NAME": "Garner"}, 70),
    (PEOPLE_URL, "surname in Env.NAMES", {"NAMES": ["Garner", "Warner"]}, 182),
    (PEOPLE_URL, "surname in Env.NAMES", {"NAMES": []}, 0),
]

# Strings that must stay a 422, one per kind of mistake.
INVALID_WHERE = [
    "gender = 1",  # assignment, not comparison
    "gender === 1",
    "gender ==",
    "not_a_field == 1",
    "surname == Smith",  # bare name: an unknown field, not a string
    "surname.upper() == 'SMITH'",  # method calls
    "__import__('os')",
    "lambda: 1",
    "gender in []",
    "handle == Env.MISSING",
]

# (select entries, the response keys they must produce)
SELECT_CASES = [
    (["gramps_id"], ["gramps_id"]),
    (["handle", "gramps_id as id"], ["handle", "id"]),
    (["primary_name.first_name"], ["primary_name.first_name"]),
    (["primary_name.surname_list[0].surname as s"], ["s"]),
    (["birth.date.sortval as born"], ["born"]),
    (["birth.place.title"], ["birth.place.title"]),
    (["count(events) as n"], ["n"]),
    (["count(events)"], ["count(events)"]),
    (["len(event_ref_list) as n"], ["n"]),
]

INVALID_SELECT = [
    "not_a_field",
    "gramps_id as",
    "gramps_id as handle",
    "count(not_a_relationship)",
    "gramps_id,",
]

# (order_by entries, the select column to check, descending?)
ORDER_BY_CASES = [
    (["gramps_id"], "gramps_id", False),
    (["-gramps_id"], "gramps_id", True),
    (["- gramps_id"], "gramps_id", True),
    (["-birth.date.sortval"], "birth.date.sortval", True),
    (["-count(events)"], "count(events)", True),
    (["-len(event_ref_list)"], "len(event_ref_list)", True),
]

INVALID_ORDER_BY = [
    "not_a_field",
    "-",
    "--gramps_id",
    "gramps_id desc",
    "gramps_id as g",
    "gender > 1",
]


def _proxied_db_handle(readonly=True):
    """An unfiltering `ProxyDbBase` over the real database, so a request
    takes the proxied (Gramps `Filter`) path with the same rows as the SQL
    path.
    """
    db = get_db_handle(readonly=readonly)
    base = db.basedb if isinstance(db, ProxyDbBase) else db
    proxy = ProxyDbBase.__new__(ProxyDbBase)
    proxy.db = proxy.basedb = base
    return proxy


class TestQueryConformance(unittest.TestCase):
    """The GOQL strings clients send keep their meaning across GOQL releases."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def setUp(self):
        self.header = fetch_header(self.client)

    def _post(self, url, body, proxied=False):
        if not proxied:
            return self.client.post(url, json=body, headers=self.header)
        with patch(
            "gramps_webapi.api.resources.object_query.get_db_handle",
            side_effect=_proxied_db_handle,
        ):
            return self.client.post(url, json=body, headers=self.header)

    def test_where_expr(self):
        for url, where_expr, env, expected in WHERE_CASES:
            body = {"select": ["handle"], "where_expr": where_expr, "count": True}
            if env is not None:
                body["env"] = env
            for proxied in (False, True):
                with self.subTest(url=url, where_expr=where_expr, proxied=proxied):
                    rv = self._post(url, body, proxied)
                    self.assertEqual(rv.status_code, 200, rv.json)
                    self.assertEqual(int(rv.headers["X-Total-Count"]), expected)

    def test_where_expr_complement(self):
        """A condition on a field every row has and its `not (...)` together
        cover every row. (Not so for a path a row may lack, such as
        `birth.date.sortval`: a missing value matches neither, as in SQL.)
        """
        total = get_object_count("people")
        for _, where_expr, env, expected in WHERE_CASES[:5]:
            with self.subTest(where_expr=where_expr):
                rv = self._post(
                    PEOPLE_URL,
                    {"where_expr": f"not ({where_expr})", "count": True},
                )
                self.assertEqual(rv.status_code, 200, rv.json)
                self.assertEqual(int(rv.headers["X-Total-Count"]), total - expected)

    def test_invalid_where_expr(self):
        for where_expr in INVALID_WHERE:
            for proxied in (False, True):
                with self.subTest(where_expr=where_expr, proxied=proxied):
                    rv = self._post(PEOPLE_URL, {"where_expr": where_expr}, proxied)
                    self.assertEqual(rv.status_code, 422, rv.json)

    def test_select(self):
        for select, keys in SELECT_CASES:
            for proxied in (False, True):
                with self.subTest(select=select, proxied=proxied):
                    rv = self._post(PEOPLE_URL, {"select": select, "limit": 5}, proxied)
                    self.assertEqual(rv.status_code, 200, rv.json)
                    self.assertEqual(len(rv.json["items"]), 5)
                    for item in rv.json["items"]:
                        self.assertEqual(sorted(item), keys)

    def test_select_paths_agree(self):
        """A path and the alias for it select the same values on both paths."""
        select = [
            "gramps_id",
            "birth.date.sortval as born",
            "count(events) as n",
            "primary_name.surname_list[0].surname as s",
        ]
        body = {"select": select, "order_by": ["gramps_id"], "limit": 50}
        sql = self._post(PEOPLE_URL, body)
        proxied = self._post(PEOPLE_URL, body, proxied=True)
        self.assertEqual(sql.status_code, 200, sql.json)
        self.assertEqual(sql.json, proxied.json)
        self.assertTrue(any(item["born"] for item in sql.json["items"]))
        self.assertTrue(any(item["n"] for item in sql.json["items"]))

    def test_invalid_select(self):
        for entry in INVALID_SELECT:
            for proxied in (False, True):
                with self.subTest(entry=entry, proxied=proxied):
                    rv = self._post(PEOPLE_URL, {"select": [entry]}, proxied)
                    self.assertEqual(rv.status_code, 422, rv.json)

    def test_order_by(self):
        for order_by, column, descending in ORDER_BY_CASES:
            body = {
                "select": [column],
                "where_expr": "birth.date.sortval > 0",
                "order_by": order_by,
                "limit": 100,
            }
            for proxied in (False, True):
                with self.subTest(order_by=order_by, proxied=proxied):
                    rv = self._post(PEOPLE_URL, body, proxied)
                    self.assertEqual(rv.status_code, 200, rv.json)
                    values = [item[column] for item in rv.json["items"]]
                    self.assertEqual(len(values), 100)
                    self.assertGreater(len(set(values)), 1)
                    self.assertEqual(values, sorted(values, reverse=descending))

    def test_order_by_multiple_keys(self):
        body = {
            "select": ["surname", "gramps_id"],
            "where_expr": "like(surname, 'G%')",
            "order_by": ["surname", "-gramps_id"],
            "limit": 200,
        }
        for proxied in (False, True):
            with self.subTest(proxied=proxied):
                rv = self._post(PEOPLE_URL, body, proxied)
                self.assertEqual(rv.status_code, 200, rv.json)
                rows = [(i["surname"], i["gramps_id"]) for i in rv.json["items"]]
                self.assertGreater(len(rows), 1)
                expected = sorted(rows, key=lambda row: row[1], reverse=True)
                expected = sorted(expected, key=lambda row: row[0].lower())
                self.assertEqual(rows, expected)

    def test_invalid_order_by(self):
        for entry in INVALID_ORDER_BY:
            for proxied in (False, True):
                with self.subTest(entry=entry, proxied=proxied):
                    rv = self._post(PEOPLE_URL, {"order_by": [entry]}, proxied)
                    self.assertEqual(rv.status_code, 422, rv.json)
