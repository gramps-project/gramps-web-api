"""Test full-text search."""

import shutil
import tempfile
import unittest

from tests.test_endpoints import get_test_client

from gramps_webapi.api.search import SearchIndexer


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
        result = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(result["hits"]), 1)
        db = self.__class__.dbmgr.get_db().db
        self.__class__.search.reindex_full(db)
        db.close()
        result = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(result["hits"]), 1)

    def test_search_1(self):
        result = self.search.search("Abigail", page=1, pagesize=2)
        hits = result["hits"]
        self.assertEqual(
            {(hit["object_type"], hit["handle"]) for hit in hits},
            {("person", "1QTJQCP5QMT2X7YJDK"), ("person", "APWKQCI6YXAXBLC33I"),},
        )

    def test_search_endpoint_1(self):
        # missing query parameter
        result = self.client.get("/api/search/")
        self.assertEqual(result.status_code, 422)

    def test_search_endpoint_2(self):
        result = self.client.get("/api/search/?query=microfilm")
        hits = result.json["hits"]
        self.assertEqual(
            [hit["handle"] for hit in hits],
            ["b39fe2e143d1e599450", "b39fe3f390e30bd2b99"],
        )
        self.assertEqual(hits[0]["object_type"], "note")
        self.assertEqual(hits[0]["rank"], 0)
        self.assertIsInstance(hits[0]["score"], float)

    def test_search_endpoint_3(self):
        result = self.client.get("/api/search/?query=microfilm&page=1&pagesize=1")
        hits = result.json["hits"]
        self.assertEqual(
            [hit["handle"] for hit in hits], ["b39fe2e143d1e599450"],
        )
        self.assertEqual(result.json["info"]["total"], 2)
        self.assertEqual(result.json["info"]["pagecount"], 2)
        self.assertEqual(result.json["info"]["pagenum"], 1)
        self.assertEqual(result.json["info"]["offset"], 0)
        result = self.client.get("/api/search/?query=microfilm&page=2&pagesize=1")
        hits = result.json["hits"]
        self.assertEqual(result.json["info"]["total"], 2)
        self.assertEqual(result.json["info"]["pagecount"], 2)
        self.assertEqual(result.json["info"]["pagenum"], 2)
        self.assertEqual(result.json["info"]["offset"], 1)
        self.assertEqual(
            [hit["handle"] for hit in hits], ["b39fe3f390e30bd2b99"],
        )

    def test_search_endpoint_4(self):
        result = self.client.get("/api/search/?query=LoremIpsumDolorSitAmet")
        self.assertEqual(result.json["hits"], [])
        self.assertEqual(result.json["info"]["total"], 0)
        self.assertEqual(result.json["info"]["pagecount"], 0)
        self.assertEqual(result.json["info"]["pagenum"], 0)
        self.assertEqual(result.json["info"]["offset"], 0)

    def test_object(self):
        result = self.client.get("/api/search/?query=I0044")
        self.assertEqual(len(result.json["hits"]), 1)
        hit = result.json["hits"][0]
        self.assertIn("object", hit)
        self.assertEqual(hit["object"]["gramps_id"], "I0044")
