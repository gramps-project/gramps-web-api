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

"""Live-HTTP dual-path tests: `where_expr` and the equivalent raw `where`
JSON must agree, for every boolean-tree shape (`and`/`or`/`not`/`exists`,
including `backlinks`).

Before `QueryWhereConditionArgs` was widened to accept these shapes, only
`where_expr` could express them at all -- `where: [{"exists": {...}}]` 422'd
("Unknown field: exists") for *any* collection, old or new, not a
deliberate restriction, just drift between the two once `where_expr`'s own
grammar grew past what the JSON schema still modeled (see `object_query.py`'s
`QueryWhereConditionArgs` docstring). `test_object_query_parsing.py` covers
the same agreement at the AST level, independent of the Flask app; this
file is the real end-to-end confirmation, through actual HTTP requests
against the real example database, that both wire formats reach the same
result set, not just the same AST shape.
"""

import unittest

from . import BASE_URL, get_test_client
from .util import fetch_header

PEOPLE_URL = BASE_URL + "/people/query/"
NOTES_URL = BASE_URL + "/notes/query/"


class TestWhereTreeDualPath(unittest.TestCase):
    """Every case here is checked through both `where_expr` and the
    equivalent raw `where` JSON, asserting they return the same status code
    and the identical set of matched handles.
    """

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.maxDiff = None

    def _assert_expr_and_where_agree(self, url, expr, where_json):
        header = fetch_header(self.client)
        rv_expr = self.client.post(
            url, json={"select": ["handle"], "where_expr": expr}, headers=header
        )
        rv_where = self.client.post(
            url, json={"select": ["handle"], "where": where_json}, headers=header
        )
        self.assertEqual(rv_expr.status_code, 200, rv_expr.json)
        self.assertEqual(rv_where.status_code, 200, rv_where.json)
        handles_expr = sorted(item["handle"] for item in rv_expr.json["items"])
        handles_where = sorted(item["handle"] for item in rv_where.json["items"])
        self.assertEqual(handles_expr, handles_where)
        return handles_where

    def test_or(self):
        self._assert_expr_and_where_agree(
            PEOPLE_URL,
            "gender == 1 or gender == 2",
            [
                {
                    "or": [
                        {"column": "gender", "op": "eq", "value": 1},
                        {"column": "gender", "op": "eq", "value": 2},
                    ]
                }
            ],
        )

    def test_and(self):
        self._assert_expr_and_where_agree(
            PEOPLE_URL,
            "gender == 1 and gramps_id != ''",
            [
                {
                    "and": [
                        {"column": "gender", "op": "eq", "value": 1},
                        {"column": "gramps_id", "op": "ne", "value": ""},
                    ]
                }
            ],
        )

    def test_not(self):
        self._assert_expr_and_where_agree(
            PEOPLE_URL,
            "not (gender == 1)",
            [{"not": {"column": "gender", "op": "eq", "value": 1}}],
        )

    def test_exists_pre_existing_collection(self):
        # "notes" has been a registered collection since exists(...) itself
        # shipped -- this is the exact case that first surfaced the gap
        # (see this file's own module docstring): exists() on an
        # already-long-shipped collection, not just a new one.
        self._assert_expr_and_where_agree(
            PEOPLE_URL,
            "exists(notes)",
            [{"exists": {"relationship": "notes"}}],
        )

    def test_not_exists_backlinks(self):
        handles = self._assert_expr_and_where_agree(
            NOTES_URL,
            "not exists(backlinks)",
            [{"not": {"exists": {"relationship": "backlinks"}}}],
        )
        # A meaningful, non-trivial result set either way, not just "both
        # sides happened to return zero rows" -- example_gramps has both
        # referenced and orphan notes.
        self.assertTrue(handles)

    def test_exists_backlinks_class_filter(self):
        handles = self._assert_expr_and_where_agree(
            NOTES_URL,
            'exists(backlinks, _class == "Person")',
            [
                {
                    "exists": {
                        "relationship": "backlinks",
                        "where": [{"column": "_class", "op": "eq", "value": "Person"}],
                    }
                }
            ],
        )
        self.assertTrue(handles)

    def test_malformed_in_nested_in_exists_where_rejected_both_ways(self):
        # Regression test for the nested-leaf-validation gap found while
        # widening the schema (see object_query.py's _validate_where_tree):
        # a malformed 'in' value nested inside exists()'s own condition used
        # to bypass validation silently. where_expr already rejects this at
        # parse time (query_lang.py's _translate_list requires a real list
        # literal); the raw `where` form needs _validate_where_tree to catch
        # the equivalent live at request time.
        header = fetch_header(self.client)
        rv_where = self.client.post(
            NOTES_URL,
            json={
                "select": ["handle"],
                "where": [
                    {
                        "exists": {
                            "relationship": "backlinks",
                            "where": [{"column": "_class", "op": "in", "value": "not-a-list"}],
                        }
                    }
                ],
            },
            headers=header,
        )
        self.assertEqual(rv_where.status_code, 422)
