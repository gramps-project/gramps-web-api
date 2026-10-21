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
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from werkzeug.exceptions import Conflict

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


class TestSearchReindexIncrementalOnEmptyIndex(unittest.TestCase):
    """reindex_incremental() on a never-before-indexed tree.

    Unlike TestSearchEngine, this class builds a fresh SearchIndexer
    whose index is still empty (count() == 0) when reindex_incremental()
    is called -- the case the automatic post-import reindex actually
    hits, and the one that routes to reindex_full() internally instead
    of the per-object diff-and-update path.
    """

    def setUp(self):
        """Create a fresh, empty index for each test."""
        self.index_dir = tempfile.mkdtemp()
        self.dbmgr = WebDbManager(name="example_gramps", create_if_missing=False)
        db_url = f"sqlite:///{self.index_dir}/search_index.db"
        self.search = SearchIndexer(self.dbmgr.dirname, db_url)

    def tearDown(self):
        """Remove the temporary index directory."""
        shutil.rmtree(self.index_dir)

    def test_empty_index_is_fully_indexed_and_searchable(self):
        """reindex_incremental() on an empty index indexes every object."""
        self.assertEqual(self.search.count(include_private=True), 0)
        self.assertFalse(self.search.is_built())
        db = self.dbmgr.get_db().db
        self.search.reindex_incremental(db)
        db.close()
        self.assertGreater(self.search.count(include_private=True), 0)
        self.assertTrue(self.search.is_built())
        total, rv = self.search.search("I0044", page=1, pagesize=10)
        self.assertEqual(len(rv), 1)
        # event participants (see get_event_participants_for_handle /
        # preload_event_backlinks) must be indexed too, not just skipped
        # because the fast bulk path was taken.
        total, rv = self.search.search("Lewis von", page=1, pagesize=20)
        self.assertEqual(
            {(hit["object_type"], hit["handle"]) for hit in rv},
            {
                ("person", "GNUJQCL9MD64AM56OH"),
                ("family", "9OUJQCBOHW9UEK9CNV"),
                ("note", "d0436be64ac277b615b79b34e72"),
                ("event", "a5af0ecb107303354a0"),
                ("event", "a5af0ecb11f5ac3110e"),
                ("event", "a5af0ecb12e29af8a5d"),
                ("event", "a5af0ed5df832ee65c1"),
            },
        )

    def test_empty_index_reports_progress_per_object(self):
        """reindex_incremental() on an empty index still reports progress
        for every object indexed via reindex_full()'s own per-object
        progress_cb() calls -- throttling that reporting down to Celery's
        actual Redis writes is progress_callback_count()'s job (see
        tests/test_tasks.py), not something reindex_full() should do to
        every caller regardless of how it's consumed."""
        calls = []

        def progress_cb(current, total, prev=None):
            calls.append(current)

        db = self.dbmgr.get_db().db
        self.search.reindex_incremental(db, progress_cb=progress_cb)
        db.close()
        object_count = self.search.count(include_private=True)
        self.assertGreater(object_count, 0)
        # One call per object, plus reindex_full()'s own final call after
        # the loop (current=total - 1, matching the last object's index).
        self.assertEqual(len(calls), object_count + 1)


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
        self.assertIn(rv[0]["object_type"], ["source", "note", "media"])
        self.assertEqual(rv[0]["rank"], 0)
        self.assertIsInstance(rv[0]["score"], float)

    def test_get_search_semantic_is_ignored(self):
        """Test that the removed semantic parameter falls back to full-text search."""
        rv = check_success(self, TEST_URL + "?query=microfilm&semantic=1&sort=-change")
        self.assertEqual(
            {hit["handle"] for hit in rv},
            {"b39fe2e143d1e599450", "b39fe3f390e30bd2b99", "b39fe1cfc1305ac4a21"},
        )

    def test_get_search_expected_result_text_string_wildcard(self):
        """Test expected result querying for text."""
        rv = check_success(self, TEST_URL + "?query=micr*")
        self.assertEqual(
            {hit["handle"] for hit in rv},
            {"b39fe2e143d1e599450", "b39fe3f390e30bd2b99", "b39fe1cfc1305ac4a21"},
        )
        self.assertIn(rv[0]["object_type"], ["source", "note", "media"])
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
        # the order depends on the ranking, which differs between database
        # backends, so pages are compared to the unpaged result
        rv = check_success(self, TEST_URL + "?query=microfilm", full=True)
        ordered = [hit["handle"] for hit in rv.json]
        self.assertEqual(len(ordered), 3)
        for page in (1, 2, 3):
            rv = check_success(
                self,
                TEST_URL + f"?query=microfilm&page={page}&pagesize=1",
                full=True,
            )
            self.assertEqual([hit["handle"] for hit in rv.json], [ordered[page - 1]])
            self.assertEqual(rv.headers.pop("X-Total-Count"), "3")
        # past the last page: no hits, but still the total
        rv = check_success(
            self, TEST_URL + "?query=microfilm&page=4&pagesize=1", full=True
        )
        self.assertEqual(rv.json, [])
        self.assertEqual(rv.headers.pop("X-Total-Count"), "3")

    def test_get_search_parameter_strip_validate_semantics(self):
        """Test invalid strip parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "?query=microfilm&strip", check="boolean"
        )

    def test_get_search_parameter_strip_expected_result(self):
        """Test strip parameter produces expected result."""
        check_strip_parameter(self, TEST_URL + "?query=Abigail")

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

    def test_get_search_sort_by_change(self):
        """Search results sorted by last change, in both directions."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        for sort, reverse in (("change", False), ("-change", True)):
            rv = self.client.get(
                TEST_URL + f"?pagesize=100&query=Anderson&type=person&sort={sort}",
                headers=header,
            )
            changes = [hit["object"]["change"] for hit in rv.json]
            self.assertGreater(len(changes), 1)
            self.assertEqual(changes, sorted(changes, reverse=reverse))

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


class TestQueueSearchIndexBuild(unittest.TestCase):
    """Building a missing search index in the background."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.app = cls.client.application

    def _queue(self, tree, run_task=None, celery=True):
        from gramps_webapi.api import tasks

        config = {"broker_url": "redis://"} if celery else {}
        with (
            self.app.app_context(),
            patch.dict(self.app.config, {"CELERY_CONFIG": config}),
            patch.object(tasks, "run_task", run_task or MagicMock()) as mock,
        ):
            return tasks.queue_search_index_build(tree, user_id="user"), mock

    def test_built_index_is_not_rebuilt(self):
        tree = WebDbManager(name="example_gramps", create_if_missing=False).dirname
        building, run_task = self._queue(tree)
        self.assertFalse(building)
        run_task.assert_not_called()

    def test_missing_index_is_built(self):
        from gramps_webapi.api.tasks import search_reindex_full

        building, run_task = self._queue("never-indexed")
        self.assertTrue(building)
        self.assertIs(run_task.call_args[0][0], search_reindex_full)
        self.assertEqual(run_task.call_args[1]["tree"], "never-indexed")

    def test_no_task_queue(self):
        """Without a queue, a build would block the request: leave it to an admin."""
        building, run_task = self._queue("never-indexed", celery=False)
        self.assertFalse(building)
        run_task.assert_not_called()

    def test_build_already_running(self):
        building, _ = self._queue("never-indexed", MagicMock(side_effect=Conflict()))
        self.assertTrue(building)

    def test_failure_to_start_does_not_raise(self):
        building, _ = self._queue(
            "never-indexed", MagicMock(side_effect=ConnectionError("no broker"))
        )
        self.assertFalse(building)

    def test_metadata_reports_building(self):
        rv = check_success(self, BASE_URL + "/metadata/")
        self.assertIs(rv["search"]["building"], False)
