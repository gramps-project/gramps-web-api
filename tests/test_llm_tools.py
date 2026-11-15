#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
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

"""Tests for LLM tools."""

import os
import re
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import HTTPException

from gramps_webapi.api.llm import clean_answer
from gramps_webapi.api.llm.tools import (
    _describe_error,
    _page,
    _truncate_content,
    filter_events,
    filter_families,
    filter_people,
    get_event,
    get_family,
    get_note,
    get_person,
    get_place,
    search_genealogy_database,
)
from gramps_webapi.api.llm.deps import AgentDeps
from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.api.util import abort_with_message
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite

TEST_APP = None
TEST_TREE = None
_SEARCH_INDEX_TMPDIR = None


def setUpModule():
    """Test module setup."""
    global TEST_APP, TEST_TREE, _SEARCH_INDEX_TMPDIR

    _SEARCH_INDEX_TMPDIR = tempfile.mkdtemp()

    # create a database with the Gramps example tree
    test_db = ExampleDbSQLite(name="example_gramps")

    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        TEST_APP = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": f"{os.environ['GRAMPS_RESOURCES']}/doc/gramps/example/gramps",
                "LLM_MODEL": "mock-model",
                "SEARCH_INDEX_DB_URI": f"sqlite:///{_SEARCH_INDEX_TMPDIR}/search_index.db",
            },
            config_from_env=False,
        )

    with TEST_APP.app_context():
        user_db.create_all()
        db_manager = WebDbManager(name=test_db.name, create_if_missing=True)
        TEST_TREE = db_manager.dirname

        # Create test user
        add_user(
            name="test_user",
            password="test_password",
            role=ROLE_OWNER,
            tree=TEST_TREE,
        )

        db_state = db_manager.get_db()
        db = db_state.db
        get_search_indexer(TEST_TREE).reindex_full(db)
        db_state.db.close()


def tearDownModule():
    """Test module teardown."""
    if _SEARCH_INDEX_TMPDIR:
        shutil.rmtree(_SEARCH_INDEX_TMPDIR, ignore_errors=True)


def _result_ids(result: str) -> list[str]:
    """Return the Gramps IDs of the objects in a filter result, in order."""
    return re.findall(r"^(?:\[[^\]]+\] )?## \w+: .*?\(/\w+/(\w+)\)", result, re.M)


class TestDescribeError(unittest.TestCase):
    """The filter tools pass an API error's details on to the model."""

    def _raise(self, **kwargs):
        try:
            abort_with_message(422, "Rule HasBirth could not be evaluated", **kwargs)
        except HTTPException as error:
            return error
        raise AssertionError("no exception raised")

    def test_includes_messages(self):
        messages = {"query": {"rules": {"rules": {"0": ["invalid date"]}}}}
        text = _describe_error(self._raise(extra={"messages": messages}))
        self.assertTrue(text.startswith("Rule HasBirth could not be evaluated: "))
        self.assertIn("invalid date", text)

    def test_message_only(self):
        self.assertEqual(
            _describe_error(self._raise()), "Rule HasBirth could not be evaluated"
        )

    def test_other_exception(self):
        self.assertEqual(_describe_error(ValueError("boom")), "boom")


class FilterToolTestCase(unittest.TestCase):
    """Base class calling the filter tools on the example tree."""

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _call(self, tool, **kwargs):
        with TEST_APP.app_context():
            return tool(self.ctx, **kwargs)


class TestFilterPeopleTool(FilterToolTestCase):
    """Test cases for the filter_people tool."""

    def test_query(self):
        result = self._call(
            filter_people, query="Date('1855') <= birth.date.sortval < Date('1856')"
        )
        self.assertCountEqual(_result_ids(result), ["I1790", "I0044", "I0253", "I0364"])

    def test_query_without_private(self):
        self.ctx.deps.include_private = False
        result = self._call(
            filter_people, query="Date('1855') <= birth.date.sortval < Date('1856')"
        )
        self.assertIn("I0044", _result_ids(result))

    def test_birth_place(self):
        result = self._call(filter_people, birth_place="Gainesville")
        self.assertCountEqual(_result_ids(result), ["I1078", "I0001", "I0002", "I0003"])

    def test_birth_place_matches_enclosing_place(self):
        # Gainesville, Llano, TX, but not I1078 born in another Gainesville
        result = self._call(filter_people, birth_place="Llano")
        self.assertCountEqual(_result_ids(result), ["I0001", "I0002", "I0003"])

    def test_death_place(self):
        result = self._call(filter_people, death_place="Llano")
        self.assertNotIn("Invalid filter", result)
        self.assertNotIn("Error", result)

    def test_located_in_matches_like_place_parameter(self):
        # a city, its county, state and country
        for name in ["Gainesville", "Llano", "TX", "MT"]:
            with self.subTest(name=name):
                by_parameter = self._call(
                    filter_people, birth_place=name, max_results=100
                )
                by_query = self._call(
                    filter_people,
                    query=f"located_in(birth.place, '{name}')",
                    max_results=100,
                )
                self.assertTrue(_result_ids(by_query))
                self.assertEqual(_result_ids(by_query), _result_ids(by_parameter))

    def test_located_in_without_private(self):
        self.ctx.deps.include_private = False
        result = self._call(filter_people, query="located_in(birth.place, 'Llano')")
        self.assertCountEqual(_result_ids(result), ["I0001", "I0002", "I0003"])

    def test_located_in_event_collection(self):
        result = self._call(
            filter_people,
            query="any(events, type.value == EventType.BIRTH"
            " and located_in(place, 'Llano'))",
        )
        self.assertCountEqual(_result_ids(result), ["I0001", "I0002", "I0003"])

    def test_located_in_unknown_place(self):
        result = self._call(filter_people, query="located_in(birth.place, 'Atlantis')")
        self.assertEqual(
            result, "Invalid filter: no place in the tree matches 'Atlantis'"
        )

    def test_place_name_in_query_rejected(self):
        for query in [
            "'Denmark' in birth.place.name.value",
            "birth.place.title == 'Llano'",
            "any(events, 'TX' in place.enclosed_by.name.value)",
        ]:
            with self.subTest(query=query):
                result = self._call(filter_people, query=query)
                self.assertTrue(
                    result.startswith("Invalid filter: do not match place names"),
                    result,
                )

    def test_located_in_invalid_arguments(self):
        result = self._call(filter_people, query="located_in('Llano')")
        self.assertTrue(result.startswith("Invalid filter: located_in takes"), result)

    def test_criteria_are_combined_with_and(self):
        result = self._call(
            filter_people, birth_place="Gainesville", query="gender == Person.MALE"
        )
        self.assertCountEqual(_result_ids(result), ["I1078", "I0002", "I0003"])

    def test_ancestors_with_query_and_relation(self):
        result = self._call(
            filter_people,
            ancestor_of="I0044",
            ancestor_generations=2,
            query="gender == Person.MALE",
            show_relation_with="I0044",
        )
        self.assertCountEqual(_result_ids(result), ["I0106", "I0104", "I0044", "I0972"])
        # the example tree records a custom relationship to the father
        self.assertIn("[stepfather] ", result)

    def test_invalid_query(self):
        result = self._call(filter_people, query="surname ==")
        self.assertTrue(result.startswith("Invalid filter: "), result)
        self.assertIn("invalid syntax", result)

    def test_unknown_field(self):
        result = self._call(filter_people, query="'Garner' in last_name")
        self.assertTrue(result.startswith("Invalid filter: "), result)
        self.assertIn("primary_name", result)

    def test_no_criteria(self):
        result = filter_people(self.ctx)
        self.assertIn("No filter criteria provided", result)

    def test_max_results(self):
        result = self._call(filter_people, query="'Garner' in surname", max_results=5)
        self.assertEqual(len(_result_ids(result)), 5)
        self.assertRegex(result, r"Showing 5 of \d+ matching persons")

    def test_probably_alive(self):
        result = self._call(
            filter_people,
            probably_alive_on_date="1880-01-01",
            query="'Garner' in surname",
        )
        self.assertIn("I0044", _result_ids(result))

    def test_common_ancestor(self):
        result = self._call(filter_people, has_common_ancestor_with="I0552")
        self.assertTrue(_result_ids(result))

    def test_degrees_of_separation(self):
        result = self._call(
            filter_people, degrees_of_separation_from="I0552", degrees_of_separation=2
        )
        # the FilterRules addon may not be installed
        if "not available" in result:
            self.assertIn("FilterRules addon", result)
        else:
            self.assertTrue(_result_ids(result))

    def test_relationship_display_invalid_anchor(self):
        result = self._call(
            filter_people,
            ancestor_of="I0044",
            ancestor_generations=2,
            show_relation_with="INVALID",
        )
        self.assertEqual(len(_result_ids(result)), 7)


class TestFilterEventsTool(FilterToolTestCase):
    """Test cases for the filter_events tool."""

    def test_query(self):
        result = self._call(
            filter_events,
            query="type.value == EventType.DEATH"
            " and Date('1890') <= date.sortval < Date('1896')",
        )
        self.assertEqual(len(_result_ids(result)), 11)
        self.assertIn("E0204", _result_ids(result))

    def test_place(self):
        result = self._call(
            filter_events, query="type.value == EventType.BIRTH", place="Gainesville"
        )
        self.assertCountEqual(_result_ids(result), ["E0000", "E0138", "E1125", "E1378"])

    def test_participant(self):
        result = self._call(filter_events, participant_id="I0044")
        self.assertIn("E1656", _result_ids(result))

    def test_participant_with_query(self):
        result = self._call(
            filter_events, query="type.value == EventType.BIRTH", participant_id="I0044"
        )
        self.assertEqual(_result_ids(result), ["E1656"])

    def test_unknown_participant(self):
        result = self._call(filter_events, participant_id="INVALID")
        self.assertIn("No person found", result)

    def test_invalid_query(self):
        result = self._call(filter_events, query="type.value == EventType.WEDDING")
        self.assertTrue(result.startswith("Invalid filter: "), result)
        self.assertIn("EventType.MARRIAGE", result)

    def test_no_criteria(self):
        result = self._call(filter_events)
        self.assertIn("No filter criteria provided", result)


class TestFilterFamiliesTool(FilterToolTestCase):
    """Test cases for the filter_families tool."""

    def test_query(self):
        result = self._call(
            filter_families, query="'Garner' in father.surname and len(children) >= 5"
        )
        self.assertCountEqual(_result_ids(result), ["F0018", "F0031", "F0017", "F0002"])

    def test_located_in_through_partner(self):
        result = self._call(
            filter_families,
            query="located_in(mother.birth.place, 'TX')",
            max_results=100,
        )
        self.assertEqual(len(_result_ids(result)), 27)
        self.assertIn("F0031", _result_ids(result))

    def test_marriage_place(self):
        result = self._call(filter_families, marriage_place="Gainesville")
        self.assertCountEqual(_result_ids(result), ["F0065", "F0414", "F0354"])

    def test_no_criteria(self):
        result = self._call(filter_families)
        self.assertIn("No filter criteria", result)


class TestTruncateContent(unittest.TestCase):
    """Tests for the _truncate_content helper (1b)."""

    def test_short_content_unchanged(self):
        content = "hello world"
        self.assertEqual(_truncate_content(content, max_chars=100), content)

    def test_exact_length_unchanged(self):
        content = "x" * 100
        self.assertEqual(_truncate_content(content, max_chars=100), content)

    def test_long_content_truncated(self):
        content = "A" * 4000 + "B" * 2000 + "C" * 1000
        result = _truncate_content(content, max_chars=1000, head=4000, tail=1000)
        # Head preserved
        self.assertTrue(result.startswith("A" * 4000))
        # Tail preserved
        self.assertTrue(result.endswith("C" * 1000))
        # Elision marker present
        self.assertIn("chars elided", result)
        # Middle B section elided
        self.assertNotIn("B" * 100, result)

    def test_elision_count_correct(self):
        head, tail = 4000, 1000
        content = "A" * head + "M" * 3000 + "Z" * tail
        result = _truncate_content(content, max_chars=1000, head=head, tail=tail)
        self.assertIn("3000 chars elided", result)

    def test_result_is_shorter_than_original(self):
        content = "x" * 20000
        result = _truncate_content(content, max_chars=5000)
        self.assertLess(len(result), len(content))

    def test_no_negative_elision_when_head_tail_exceeds_content(self):
        # content (1500) > max_chars (1000) but head+tail (5000) >= content length:
        # truncation would make result longer, so content must be returned as-is.
        content = "x" * 1500
        result = _truncate_content(content, max_chars=1000, head=4000, tail=1000)
        self.assertEqual(result, content)
        self.assertNotIn("elided", result)

    def test_default_params_applied(self):
        # Default head=4000, tail=1000; content of 10000 chars
        content = "H" * 4000 + "M" * 5000 + "T" * 1000
        result = _truncate_content(content, max_chars=5000)
        self.assertTrue(result.startswith("H" * 4000))
        self.assertTrue(result.endswith("T" * 1000))


class TestSearchFulltext(unittest.TestCase):
    """Tests for the full-text search tool."""

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _search(self, **kwargs):
        with TEST_APP.app_context():
            return search_genealogy_database(self.ctx, **kwargs)

    def test_hits_have_type_and_link(self):
        result = self._search(query="Lewis Anderson Garner", object_type="Person")
        self.assertTrue(result.startswith("## Person: "), result[:100])
        self.assertIn("(/person/I0044)", result)

    def test_hits_include_dates(self):
        result = self._search(query="Lewis Anderson Garner", object_type="Person")
        self.assertIn("1855-06-21", result)

    def test_object_type_filter(self):
        result = self._search(query="Garner", object_type="Event", max_results=5)
        headers = [line for line in result.splitlines() if line.startswith("## ")]
        self.assertTrue(headers)
        self.assertTrue(all(h.startswith("## Event: ") for h in headers))

    def test_truncation_message(self):
        result = self._search(query="Garner", max_results=1)
        self.assertRegex(result, r"Showing 1 of \d+ matches\.")

    def test_no_results_hint(self):
        result = self._search(query="Xyzzyqwertyuiop")
        self.assertIn("No results found", result)
        self.assertIn("filter_people", result)

    def test_without_private(self):
        self.ctx.deps.include_private = False
        result = self._search(query="Garner", object_type="Person", max_results=3)
        self.assertNotIn("Error", result)
        self.assertIn("/person/", result)

    def test_tag_hits_skipped(self):
        # "ToDo" only matches a tag, which has no record to show
        result = self._search(query="ToDo")
        self.assertNotIn("Error", result)
        self.assertIn("No results found", result)

    def test_attribute_only_match_shows_attribute(self):
        # "fingers" only occurs in an attribute of I0044
        result = self._search(query="fingers toes", object_type="Person")
        self.assertIn("(/person/I0044)", result)
        self.assertIn("10 fingers, 10 toes.", result)

    def test_private_attribute(self):
        result = self._search(query="Big Louie", object_type="Person")
        self.assertIn("123-456-7890", result)
        self.ctx.deps.include_private = False
        result = self._search(query="Big Louie", object_type="Person")
        self.assertIn("(/person/I0044)", result)
        self.assertNotIn("123-456-7890", result)


class TestPage(unittest.TestCase):
    """Tests for reading long texts in sections."""

    def test_short_text_unchanged(self):
        self.assertEqual(_page("short", 0, 100, "get_note"), "short")

    def test_fact_in_the_middle_of_a_long_text(self):
        text = "x" * 25000 + " MIDDLE FACT " + "y" * 25000
        offset, pages = 0, []
        while True:
            page = _page(text, offset, 10000, "get_note")
            pages.append(page)
            match = re.search(r"Call get_note with offset=(\d+)", page)
            if not match:
                break
            offset = int(match.group(1))
        self.assertEqual(len(pages), 6)
        self.assertIn("MIDDLE FACT", "".join(pages))
        self.assertTrue(pages[-1].endswith("end of text.]"))

    def test_offset_beyond_end(self):
        self.assertIn("only 5 characters", _page("short", 10, 100, "get_note"))


class TestGetNote(unittest.TestCase):
    """Tests for the get_note tool."""

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _get_note(self, gramps_id):
        with TEST_APP.app_context():
            return get_note(self.ctx, gramps_id)

    def test_full_text_and_backlinks(self):
        result = self._get_note("N0003")
        self.assertIn("Mission Statement Generator", result)
        self.assertIn("Referenced by: [Lewis Anderson Garner", result)

    def test_unknown_id_returns_not_found(self):
        result = self._get_note("INVALID_XYZ_999")
        self.assertIn("No note found", result)


class TestCleanAnswer(unittest.TestCase):
    """Tests for cleaning the links in answers."""

    def _clean(self, answer):
        with TEST_APP.app_context():
            return clean_answer(
                answer, tree=TEST_TREE, include_private=True, user_id="test_user"
            )

    def test_keeps_links_to_existing_objects(self):
        answer = "[Lewis Anderson Garner](/person/I0044) wrote [a note](/note/N0003)."
        self.assertEqual(self._clean(answer), answer)

    def test_replaces_links_to_missing_objects_by_text(self):
        answer = (
            "[Lewis Anderson Garner](/person/I0044) had a son"
            " [John Garner](/person/I99999) in [Family](/family/F99999)."
        )
        self.assertEqual(
            self._clean(answer),
            "[Lewis Anderson Garner](/person/I0044) had a son John Garner in Family.",
        )

    def test_makes_placeholder_links_relative(self):
        answer = (
            "[Lewis Anderson Garner](https://www.example.com/person/I0044) and"
            " [John Garner](http://example.org/person/I99999)"
        )
        self.assertEqual(
            self._clean(answer),
            "[Lewis Anderson Garner](/person/I0044) and John Garner",
        )

    def test_keeps_other_links(self):
        answer = (
            "See [Wikipedia](https://en.wikipedia.org/), [tag](/tag/Foo) or"
            " [FamilySearch](https://www.familysearch.org/tree/person/details/L1)."
        )
        self.assertEqual(self._clean(answer), answer)


class TestGetPerson(unittest.TestCase):
    """Tests for the get_person tool (2a)."""

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _get_person(self, gramps_id):
        with TEST_APP.app_context():
            return get_person(self.ctx, gramps_id)

    def test_known_person_returns_content(self):
        result = self._get_person("I0044")
        self.assertNotIn("Error", result)
        self.assertNotIn("No person found", result)
        self.assertGreater(len(result), 50)

    def test_result_contains_person_link(self):
        result = self._get_person("I0044")
        self.assertNotIn("No person found", result)
        self.assertIn("/person/", result)

    def test_result_contains_gramps_id(self):
        result = self._get_person("I0044")
        self.assertNotIn("No person found", result)
        self.assertIn("I0044", result)

    def test_unknown_id_returns_not_found(self):
        result = self._get_person("INVALID_XYZ_999")
        self.assertIn("No person found", result)


class TestGetFamily(unittest.TestCase):
    """Tests for the get_family tool (2b)."""

    valid_family_id = None

    @classmethod
    def setUpClass(cls):
        from gramps_webapi.api.util import get_db_outside_request

        with TEST_APP.app_context():
            db = get_db_outside_request(
                tree=TEST_TREE,
                view_private=True,
                readonly=True,
                user_id="test_user",
            )
            try:
                for handle in db.get_family_handles():
                    fam = db.get_family_from_handle(handle)
                    cls.valid_family_id = fam.get_gramps_id()
                    break
            finally:
                db.close()

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _get_family(self, gramps_id):
        with TEST_APP.app_context():
            return get_family(self.ctx, gramps_id)

    def test_known_family_returns_content(self):
        if not self.valid_family_id:
            self.skipTest("No family found in test database")
        result = self._get_family(self.valid_family_id)
        self.assertNotIn("Error", result)
        self.assertNotIn("No family found", result)
        self.assertGreater(len(result), 50)

    def test_result_contains_family_link(self):
        if not self.valid_family_id:
            self.skipTest("No family found in test database")
        result = self._get_family(self.valid_family_id)
        self.assertNotIn("No family found", result)
        self.assertIn("/family/", result)

    def test_unknown_id_returns_not_found(self):
        result = self._get_family("INVALID_XYZ_999")
        self.assertIn("No family found", result)


class TestGetEvent(unittest.TestCase):
    """Tests for the get_event tool."""

    valid_event_id = None

    @classmethod
    def setUpClass(cls):
        from gramps_webapi.api.util import get_db_outside_request

        with TEST_APP.app_context():
            db = get_db_outside_request(
                tree=TEST_TREE,
                view_private=True,
                readonly=True,
                user_id="test_user",
            )
            try:
                for handle in db.get_event_handles():
                    event = db.get_event_from_handle(handle)
                    cls.valid_event_id = event.get_gramps_id()
                    break
            finally:
                db.close()

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _get_event(self, gramps_id):
        with TEST_APP.app_context():
            return get_event(self.ctx, gramps_id)

    def test_known_event_returns_content(self):
        if not self.valid_event_id:
            self.skipTest("No event found in test database")
        result = self._get_event(self.valid_event_id)
        self.assertNotIn("Error", result)
        self.assertNotIn("No event found", result)
        self.assertGreater(len(result), 50)

    def test_result_contains_event_link(self):
        if not self.valid_event_id:
            self.skipTest("No event found in test database")
        result = self._get_event(self.valid_event_id)
        self.assertNotIn("No event found", result)
        self.assertIn("/event/", result)

    def test_unknown_id_returns_not_found(self):
        result = self._get_event("INVALID_XYZ_999")
        self.assertIn("No event found", result)


class TestGetPlace(unittest.TestCase):
    """Tests for the get_place tool."""

    valid_place_id = None

    @classmethod
    def setUpClass(cls):
        from gramps_webapi.api.util import get_db_outside_request

        with TEST_APP.app_context():
            db = get_db_outside_request(
                tree=TEST_TREE,
                view_private=True,
                readonly=True,
                user_id="test_user",
            )
            try:
                for handle in db.get_place_handles():
                    place = db.get_place_from_handle(handle)
                    cls.valid_place_id = place.get_gramps_id()
                    break
            finally:
                db.close()

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _get_place(self, gramps_id):
        with TEST_APP.app_context():
            return get_place(self.ctx, gramps_id)

    def test_known_place_returns_content(self):
        if not self.valid_place_id:
            self.skipTest("No place found in test database")
        result = self._get_place(self.valid_place_id)
        self.assertNotIn("Error", result)
        self.assertNotIn("No place found", result)
        self.assertGreater(len(result), 50)

    def test_result_contains_place_link(self):
        if not self.valid_place_id:
            self.skipTest("No place found in test database")
        result = self._get_place(self.valid_place_id)
        self.assertNotIn("No place found", result)
        self.assertIn("/place/", result)

    def test_unknown_id_returns_not_found(self):
        result = self._get_place("INVALID_XYZ_999")
        self.assertIn("No place found", result)


if __name__ == "__main__":
    unittest.main()
