#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024 David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Test full-text search."""

import shutil
import tempfile
import unittest
from urllib.parse import quote

from gramps_webapi.api.search import SearchIndexer
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.dbmanager import WebDbManager

from . import BASE_URL, get_test_client
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_strip_parameter,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/search/"


class TestSearchEngine(unittest.TestCase):
    """Test cases for full-text search engine."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.index_dir = tempfile.mkdtemp()
        cls.dbmgr = WebDbManager(name="example_gramps", create_if_missing=False)
        tree = cls.dbmgr.dirname
        db_url = f"sqlite:///{cls.index_dir}/search_index.db"
        cls.search = SearchIndexer(tree, db_url)
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

    def test_reindexing_incremental(self):
        """Test if reindexing again leads to doubled rv."""
        total, rv = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(rv), 1)
        db = self.__class__.dbmgr.get_db().db
        self.__class__.search.reindex_incremental(db)
        db.close()
        total, rv = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(rv), 1)

    def test_search_method(self):
        """Test search engine returns an expected result."""
        total, rv = self.search.search("Lewis von", page=1, pagesize=20)
        self.assertEqual(
            {(hit["object_type"], hit["handle"]) for hit in rv},
            {
                ("person", "GNUJQCL9MD64AM56OH"),
                ("family", "9OUJQCBOHW9UEK9CNV"),
                ("note", "d0436be64ac277b615b79b34e72"),
                ("event", "a5af0ecb107303354a0"),  # person event
                ("event", "a5af0ecb11f5ac3110e"),  # person event
                ("event", "a5af0ecb12e29af8a5d"),  # person event
                ("event", "a5af0ed5df832ee65c1"),  # family event
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
            {hit["handle"] for hit in rv},
            {"b39fe2e143d1e599450", "b39fe3f390e30bd2b99", "b39fe1cfc1305ac4a21"},
        )
        self.assertIn(rv[0]["object_type"], ["source", "note"])
        self.assertEqual(rv[0]["rank"], 0)
        self.assertIsInstance(rv[0]["score"], float)

    def test_get_search_expected_result_text_string_wildcard(self):
        """Test expected result querying for text."""
        rv = check_success(self, TEST_URL + "?query=micr*")
        self.assertEqual(
            {hit["handle"] for hit in rv},
            {"b39fe2e143d1e599450", "b39fe3f390e30bd2b99", "b39fe1cfc1305ac4a21"},
        )
        self.assertIn(rv[0]["object_type"], ["source", "note"])
        self.assertEqual(rv[0]["rank"], 0)
        self.assertIsInstance(rv[0]["score"], float)

    def test_get_search_expected_result_specific_object(self):
        """Test expected result querying for a specific object by Gramps id."""
        rv = check_success(self, TEST_URL + "?query=I0044")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0044")

    def test_get_search_expected_result_or(self):
        """Test expected result querying for a specific object by Gramps id."""
        rv = check_success(self, TEST_URL + f"?query={quote('I0044 OR I0043')}")
        self.assertEqual(len(rv), 2)

    def test_get_search_expected_result_unicode(self):
        """Test expected result querying for a Unicode decoded string."""
        # 斎藤 is transliterated as Zhai Teng
        rv = check_success(self, TEST_URL + f"?query={quote('Zhai Teng')}&type=person")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0761")
        rv = check_success(self, TEST_URL + f"?query={quote('斎藤')}&type=person")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0761")

    def test_get_search_expected_result_unicode_2(self):
        """Test expected result querying for a Unicode decoded string."""
        # Шестаков is transliterated as Shestakov
        rv = check_success(self, TEST_URL + f"?query={quote('Shestakov')}&type=person")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0972")
        rv = check_success(self, TEST_URL + f"?query={quote('Шестаков')}&type=person")
        self.assertEqual(len(rv), 1)
        self.assertIn("object", rv[0])
        self.assertEqual(rv[0]["object"]["gramps_id"], "I0972")

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
            ["b39fe3f390e30bd2b99"],
        )
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "3")
        rv = check_success(
            self, TEST_URL + "?query=microfilm&page=2&pagesize=1", full=True
        )

        self.assertEqual(len(rv.json), 1)
        self.assertEqual(
            [hit["handle"] for hit in rv.json],
            ["b39fe1cfc1305ac4a21"],
        )
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "3")

        rv = check_success(
            self, TEST_URL + "?query=microfilm&page=3&pagesize=1", full=True
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(
            [hit["handle"] for hit in rv.json],
            ["b39fe2e143d1e599450"],
        )
        count = rv.headers.pop("X-Total-Count")
        self.assertEqual(count, "3")

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
        rv = check_success(self, TEST_URL + "?query=Lewis%20von&page=1&profile=all")
        self.assertEqual(rv[0]["object_type"], "person")
        self.assertIn("profile", rv[0]["object"])
        self.assertEqual(rv[0]["object"]["profile"]["name_given"], "Lewis Anderson")

    def test_get_search_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=Abigail&profile=self&locale", check="base"
        )

    def test_get_search_parameter_profile_expected_result_with_locale(self):
        """Test expected profile response for a locale."""
        rv = check_success(self, TEST_URL + "?query=Lewis%20von&profile=self&locale=de")
        self.assertEqual(rv[0]["object_type"], "person")
        self.assertIn("profile", rv[0]["object"])
        self.assertEqual(rv[0]["object"]["profile"]["name_given"], "Lewis Anderson")
        self.assertEqual(rv[0]["object"]["profile"]["birth"]["type"], "Geburt")
        self.assertEqual(rv[0]["object"]["profile"]["death"]["type"], "Tod")

    def test_get_search_private_attribute_guest(self):
        """Search for a private attribute as owner."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        # the guest won't find any results when searching for the private attribute
        rv = self.client.get(
            TEST_URL + f"?query={quote('123 456 7890')}", headers=header
        )
        self.assertEqual(len(rv.json), 0)

    def test_get_search_private_attribute_owner(self):
        """Search for a private attribute as owner."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        # the owner will get a hit when searching for the private attribute
        rv = self.client.get(
            TEST_URL + f"?query={quote('123 456 7890')}", headers=header
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["object"]["gramps_id"], "I0044")

    def test_get_search_explicit_fields_owner(self):
        """Search for an explicit type as owner."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(
            TEST_URL + f"?query={quote('a*')}&type=repository&sort=change&pagesize=1",
            headers=header,
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["object"]["gramps_id"], "R0003")

    def test_get_search_explicit_fields_guest(self):
        """Search for a an explicit type as guest."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        rv = self.client.get(
            TEST_URL + f"?query={quote('lib*')}&type=repository&sort=change&pagesize=1",
            headers=header,
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["object"]["gramps_id"], "R0003")

    def test_get_search_oldest(self):
        """Search for the oldest person record."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(
            TEST_URL + "?pagesize=1&page=1&query=Anderson&type=person",
            headers=header,
        )
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["object"]["gramps_id"], "I0044")

    # def test_get_search_newest(self):
    #     """Search for the newest person record."""
    #     header = fetch_header(self.client, role=ROLE_OWNER)
    #     rv = self.client.get(
    #         TEST_URL
    #         + "?sort=-change&pagesize=1&page=1&query={}".format(
    #             quote("type:person change:'1990 to now'")
    #         ),
    #         headers=header,
    #     )
    #     self.assertEqual(len(rv.json), 1)
    #     self.assertEqual(rv.json[0]["object"]["gramps_id"], "I0363")
