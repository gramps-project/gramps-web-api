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

from . import BASE_URL, get_test_client
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_strip_parameter,
    check_success,
)

TEST_URL = BASE_URL + "/search/"


class TestSearchEngine(unittest.TestCase):
    """Test cases for full-text search engine."""

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
        """Remove the temporary index directory."""
        shutil.rmtree(cls.index_dir)

    def test_reindexing(self):
        """Test if reindexing again leads to doubled rv."""
        total, rv = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(rv), 1)
        db = self.__class__.dbmgr.get_db().db
        self.__class__.search.reindex_full(db)
        db.close()
        total, rv = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(rv), 1)

    def test_search_method(self):
        """Test search engine returns an expected result."""
        total, rv = self.search.search("Abigail", page=1, pagesize=2)
        self.assertEqual(
            {(hit["object_type"], hit["handle"]) for hit in rv},
            {
                ("person", "1QTJQCP5QMT2X7YJDK"),
                ("person", "APWKQCI6YXAXBLC33I"),
            },
        )


class TestSearch(unittest.TestCase):
    """Test cases for the /api/search endpoint for full-text searches."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_search_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "?query=microfilm")

    def test_get_search_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL)
        check_invalid_semantics(self, TEST_URL + "?query", check="base")

    def test_get_search_expected_result_text_string(self):
        """Test expected result querying for text."""
        rv = check_success(self, TEST_URL + "?query=microfilm")
        self.assertEqual(
            [hit["handle"] for hit in rv],
            ["b39fe2e143d1e599450", "b39fe3f390e30bd2b99"],
        )
        self.assertEqual(rv[0]["object_type"], "note")
        self.assertEqual(rv[0]["rank"], 0)
        self.assertIsInstance(rv[0]["score"], float)

    def test_get_search_expected_result_specific_object(self):
        """Test expected result querying for a specific object by Gramps id."""
        rv = check_success(self, TEST_URL + "?query=I0044")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0044")

    def test_get_search_expected_result_no_hits(self):
        """Test expected result when no hits."""
        rv = check_success(self, TEST_URL + "?query=LoremIpsumDolorSitAmet", full=True)
        self.assertEqual(rv.json, [])
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "0")

    def test_get_search_parameter_page_validate_semantics(self):
        """Test invalid page parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=microfilm&page", check="number"
        )

    def test_get_search_parameter_pagesize_validate_semantics(self):
        """Test invalid pagesize parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=microfilm&page=1&pagesize", check="number"
        )

    def test_get_search_parameter_page_pagesize_expected_result(self):
        """Test page and pagesize parameters expected result."""
        rv = check_success(
            self, TEST_URL + "?query=microfilm&page=1&pagesize=1", full=True
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(
            [hit["handle"] for hit in rv.json],
            ["b39fe2e143d1e599450"],
        )
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "2")
        rv = check_success(
            self, TEST_URL + "?query=microfilm&page=2&pagesize=1", full=True
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(
            [hit["handle"] for hit in rv.json],
            ["b39fe3f390e30bd2b99"],
        )
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "2")

    def test_get_search_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=microfilm&strip", check="boolean"
        )

    def test_get_search_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "?query=Abigail", join="&")

    def test_get_search_parameter_profile_validate_semantics(self):
        """Test invalid profile parameter and values."""
        check_invalid_semantics(self, TEST_URL + "?query=Abigail&profile", check="list")

    def test_get_search_parameter_profile_expected_result(self):
        """Test expected response."""
        rv = check_success(self, TEST_URL + "?query=Abigail&page=1&profile=all")
        self.assertEqual(rv[0]["object_type"], "person")
        self.assertIn("profile", rv[0]["object"])
        self.assertEqual(rv[0]["object"]["profile"]["name_given"], "Abigail")

    def test_get_search_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=Abigail&profile=self&locale", check="base"
        )

    def test_get_search_parameter_profile_expected_result_with_locale(self):
        """Test expected profile response for a locale."""
        rv = check_success(self, TEST_URL + "?query=Abigail&profile=self&locale=de")
        self.assertEqual(rv[0]["object_type"], "person")
        self.assertIn("profile", rv[0]["object"])
        self.assertEqual(rv[0]["object"]["profile"]["name_given"], "Abigail")
        self.assertEqual(rv[0]["object"]["profile"]["birth"]["type"], "Geburt")
        self.assertEqual(rv[0]["object"]["profile"]["death"]["type"], "Tod")
