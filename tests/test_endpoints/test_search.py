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

    def test_search_1(self):
        handles = self.search.search("Abigail")
        self.assertEqual(
            handles,
            [
                ("person", "1QTJQCP5QMT2X7YJDK"),
                ("person", "APWKQCI6YXAXBLC33I"),
                ("person", "H4UJQCQI05USCJ93RO"),
                ("event", "a5af0ec3be8255006e4"),
                ("event", "a5af0ec5165620023c2"),
                ("event", "a5af0ec51752bb3933a"),
                ("event", "a5af0ec51864cfd234f"),
                ("event", "a5af0ec600f56496ec9"),
                ("event", "a5af0ec602419320d6a"),
                ("event", "a5af0ec60365264cf35"),
            ],
        )

    def test_search_2(self):
        handles = self.search.search("microfilm")
        self.assertEqual(
            handles,
            [("note", "b39fe2e143d1e599450"), ("source", "b39fe3f390e30bd2b99")],
        )

    def test_search_3(self):
        handles = self.search.search("LoremIpsumDolorSitAmet")
        self.assertEqual(handles, [])
