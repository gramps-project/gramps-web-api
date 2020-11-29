#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn, David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Test full-text search."""

import shutil
import tempfile
import unittest

from gramps_webapi.api.search import SearchIndexer
from tests.test_endpoints import get_test_client


class TestSearch(unittest.TestCase):
    """Test cases for full-text search."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.index_dir = tempfile.mkdtemp()
        cls.dbmgr = cls.client.application.config["DB_MANAGER"]
        cls.search = SearchIndexer(cls.index_dir)
        db = cls.dbmgr.get_db().db
        cls.search.reindex_full(db)
        db.close()

    @classmethod
    def tearDownClass(cls):
        """Remove the temp directory."""
        shutil.rmtree(cls.index_dir)

    def test_reindex(self):
        # test if reindexing again leads to doubled results
        total, results = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(results), 1)
        db = self.__class__.dbmgr.get_db().db
        self.__class__.search.reindex_full(db)
        db.close()
        total, results = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(results), 1)

    def test_search_1(self):
        total, results = self.search.search("Abigail", page=1, pagesize=2)
        self.assertEqual(
            {(hit["object_type"], hit["handle"]) for hit in results},
            {
                ("person", "1QTJQCP5QMT2X7YJDK"),
                ("person", "APWKQCI6YXAXBLC33I"),
            },
        )

    def test_search_endpoint_1(self):
        # missing query parameter
        result = self.client.get("/api/search/")
        self.assertEqual(result.status_code, 422)

    def test_search_endpoint_2(self):
        results = self.client.get("/api/search/?query=microfilm")
        self.assertEqual(
            [hit["handle"] for hit in results.json],
            ["b39fe2e143d1e599450", "b39fe3f390e30bd2b99"],
        )
        self.assertEqual(results.json[0]["object_type"], "note")
        self.assertEqual(results.json[0]["rank"], 0)
        self.assertIsInstance(results.json[0]["score"], float)

    def test_search_endpoint_3(self):
        results = self.client.get("/api/search/?query=microfilm&page=1&pagesize=1")
        self.assertEqual(
            [hit["handle"] for hit in results.json],
            ["b39fe2e143d1e599450"],
        )
        count = results.headers.pop("X-Total-Count")
        self.assertEqual(count, "2")
        results = self.client.get("/api/search/?query=microfilm&page=2&pagesize=1")
        count = results.headers.pop("X-Total-Count")
        self.assertEqual(count, "2")
        self.assertEqual(
            [hit["handle"] for hit in results.json],
            ["b39fe3f390e30bd2b99"],
        )

    def test_search_endpoint_4(self):
        results = self.client.get("/api/search/?query=LoremIpsumDolorSitAmet")
        self.assertEqual(results.json, [])
        count = results.headers.pop("X-Total-Count")
        self.assertEqual(count, "0")

    def test_object(self):
        results = self.client.get("/api/search/?query=I0044")
        self.assertEqual(len(results.json), 1)
        hit = results.json[0]
        self.assertIn("object", hit)
        self.assertEqual(hit["object"]["gramps_id"], "I0044")
