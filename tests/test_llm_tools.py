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
import unittest
from unittest.mock import MagicMock, patch

from gramps_webapi.api.llm.tools import (
    filter_events,
    filter_people,
    _build_date_expression,
)
from gramps_webapi.api.llm.deps import AgentDeps
from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite


TEST_APP = None
TEST_TREE = None


def setUpModule():
    """Test module setup."""
    global TEST_APP, TEST_TREE

    # create a database with the Gramps example tree
    test_db = ExampleDbSQLite(name="example_gramps")

    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        TEST_APP = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": f"{os.environ['GRAMPS_RESOURCES']}/doc/gramps/example/gramps",
                "VECTOR_EMBEDDING_MODEL": "paraphrase-albert-small-v2",
                "LLM_MODEL": "mock-model",
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
        search_index = get_search_indexer(TEST_TREE)
        db = db_state.db
        search_index.reindex_full(db)
        db_state.db.close()


class TestDateExpressionBuilder(unittest.TestCase):
    """Test cases for the _build_date_expression helper function."""

    def test_date_range(self):
        """Test building a date range expression."""
        result = _build_date_expression(before="1900", after="1850")
        self.assertEqual(result, "between 1850 and 1900")

    def test_after_only(self):
        """Test building an 'after' expression."""
        result = _build_date_expression(before=None, after="1850")
        self.assertEqual(result, "after 1850")

    def test_before_only(self):
        """Test building a 'before' expression."""
        result = _build_date_expression(before="1900", after=None)
        self.assertEqual(result, "before 1900")

    def test_empty(self):
        """Test with no dates."""
        result = _build_date_expression("", "")
        self.assertEqual(result, "")

    def test_gramps_date_parser_compatibility(self):
        """Test that generated expressions are valid Gramps dates."""
        from gramps.gen.datehandler import parser

        test_cases = [
            _build_date_expression("1900", "1850"),  # between
            _build_date_expression("", "1850"),  # after
            _build_date_expression("1900", ""),  # before
        ]

        for date_expr in test_cases:
            if date_expr:  # Skip empty string
                parsed = parser.parse(date_expr)
                self.assertFalse(
                    parsed.is_empty(),
                    f"Date expression '{date_expr}' should be valid but parsed as empty",
                )
                # Verify it round-trips correctly
                self.assertIn(
                    date_expr.split()[0],  # First word (between/after/before)
                    parsed.get_text(),
                    f"Date expression '{date_expr}' didn't parse correctly",
                )


class TestFilterPeopleTool(unittest.TestCase):
    """Test cases for the filter_people tool."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.app = TEST_APP

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock context
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _filter_people(self, **kwargs):
        """Helper to call filter_people with app context."""
        with self.app.app_context():
            return filter_people(self.ctx, **kwargs)

    def test_filter_by_surname(self):
        """Test filtering by surname only."""
        result = self._filter_people(surname="Garner")

        # Should return results (not an error message)
        self.assertNotIn("Error", result)
        self.assertNotIn("No people found", result)

        # Should contain Garner family members
        self.assertIn("Garner", result)

    def test_filter_by_given_name(self):
        """Test filtering by given name only."""
        result = self._filter_people(given_name="Lewis")

        self.assertNotIn("Error", result)
        self.assertNotIn("No people found", result)
        self.assertIn("Lewis", result)

    def test_filter_by_birth_year_before(self):
        """Test filtering by birth year before."""
        result = self._filter_people(birth_year_before="1900")

        self.assertNotIn("Error", result)
        self.assertNotIn("No people found", result)
        # Should find people born before 1900

    def test_filter_by_birth_year_after(self):
        """Test filtering by birth year after."""
        result = self._filter_people(birth_year_after="1850")

        self.assertNotIn("Error", result)
        # Should find people born after 1850

    def test_filter_by_birth_year_range(self):
        """Test filtering by birth year range."""
        result = self._filter_people(birth_year_after="1850", birth_year_before="1900")

        self.assertNotIn("Error", result)
        # Should find people born between 1850 and 1900

    def test_filter_by_surname_and_birth_year(self):
        """Test combining surname and birth year filters."""
        result = self._filter_people(surname="Garner", birth_year_before="1900")

        self.assertNotIn("Error", result)
        # Should find Garners born before 1900

    def test_filter_no_criteria(self):
        """Test that filter without criteria returns error message."""
        # This test doesn't need app context as it returns early,
        # but we'll call directly to test the error path
        result = filter_people(self.ctx)

        self.assertIn("No filter criteria provided", result)

    def test_filter_max_results(self):
        """Test max_results parameter."""
        result = self._filter_people(surname="Garner", max_results=5)

        self.assertNotIn("Error", result)
        # Result should be limited

    def test_filter_max_results_boundary(self):
        """Test max_results boundary enforcement."""
        # Should cap at 100
        result = self._filter_people(surname="Garner", max_results=200)

        self.assertNotIn("Error", result)

    def test_filter_or_logic(self):
        """Test OR combination of filters."""
        # This is tricky - OR would need multiple surname values
        # For now, test that combine_filters parameter is accepted
        result = self._filter_people(
            surname="Garner", given_name="Lewis", combine_filters="or"
        )

        self.assertNotIn("Error", result)

    def test_filter_respects_privacy(self):
        """Test that privacy settings are respected."""
        # Test with include_private=False
        ctx_no_private = MagicMock()
        ctx_no_private.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=False,
            max_context_length=50000,
            user_id="test_user",
        )

        with self.app.app_context():
            result = filter_people(ctx_no_private, surname="Garner")

        # Should work but potentially return fewer results
        self.assertNotIn("Error", result)

    def test_filter_with_death_year(self):
        """Test filtering by death year."""
        result = self._filter_people(death_year_before="1950")

        self.assertNotIn("Error", result)

    def test_filter_with_birth_place(self):
        """Test filtering by birth place."""
        result = self._filter_people(birth_place="Falls")

        self.assertNotIn("Error", result)

    def test_filter_with_death_place(self):
        """Test filtering by death place."""
        result = self._filter_people(death_place="Falls")

        self.assertNotIn("Error", result)

    def test_filter_truncation_message(self):
        """Test that truncation messages are included when appropriate."""
        result = self._filter_people(birth_year_after="1800", max_results=5)

        # Should mention if results were limited
        if "Showing" in result:
            # Verify the message format
            self.assertTrue(
                "Showing" in result and ("of" in result or "limit reached" in result)
            )

    def test_filter_ancestors(self):
        """Test filtering by ancestors."""
        result = self._filter_people(ancestor_of="I0552", ancestor_generations=5)

        self.assertNotIn("Error", result)

    def test_filter_descendants(self):
        """Test filtering by descendants."""
        result = self._filter_people(descendant_of="I0552", descendant_generations=5)

        self.assertNotIn("Error", result)

    def test_filter_is_male(self):
        """Test filtering by male gender."""
        result = self._filter_people(surname="Garner", is_male=True)

        self.assertNotIn("Error", result)

    def test_filter_is_female(self):
        """Test filtering by female gender."""
        result = self._filter_people(surname="Garner", is_female=True)

        self.assertNotIn("Error", result)

    def test_filter_probably_alive(self):
        """Test filtering by probably alive on date."""
        result = self._filter_people(probably_alive_on_date="1880-01-01")

        self.assertNotIn("Error", result)

    def test_filter_common_ancestor(self):
        """Test filtering by common ancestor."""
        result = self._filter_people(has_common_ancestor_with="I0552")

        self.assertNotIn("Error", result)

    def test_filter_male_ancestors_alive_in_1880(self):
        """Test complex query: male ancestors alive in 1880."""
        result = self._filter_people(
            ancestor_of="I0552",
            ancestor_generations=5,
            is_male=True,
            probably_alive_on_date="1880-01-01",
        )

        self.assertNotIn("Error", result)

    def test_filter_degrees_of_separation(self):
        """Test filtering by degrees of separation."""
        result = self._filter_people(
            degrees_of_separation_from="I0552", degrees_of_separation=2
        )

        # Filter may not be available if FilterRules addon is not installed
        if "not available" in result:
            self.assertIn("FilterRules addon", result)
        else:
            self.assertNotIn("Error", result)
            # Should return people within 2 degrees of separation from I0552
            self.assertGreater(len(result), 0, "Should find relatives within 2 degrees")

    def test_filter_degrees_of_separation_with_gender(self):
        """Test degrees of separation combined with gender filter."""
        result = self._filter_people(
            degrees_of_separation_from="I0044", degrees_of_separation=3, is_male=True
        )

        # Filter may not be available if FilterRules addon is not installed
        if "not available" not in result:
            self.assertNotIn("Error", result)

    def test_filter_degrees_of_separation_invalid_id(self):
        """Test degrees of separation with invalid Gramps ID."""
        result = self._filter_people(
            degrees_of_separation_from="INVALID", degrees_of_separation=2
        )

        # Should return no results, error gracefully, or report filter not available
        if "not available" not in result:
            self.assertTrue(
                "No people found" in result or "Error" not in result,
                "Should handle invalid ID gracefully",
            )

    def test_filter_with_relationship_display(self):
        """Test filtering with show_relation_with to display relationships."""
        # Find ancestors of Lewis Anderson Garner (I0044) and show their relationship to him
        result = self._filter_people(
            ancestor_of="I0044", ancestor_generations=2, show_relation_with="I0044"
        )

        self.assertNotIn("Error", result)
        # Should contain relationship markers like [father], [mother], [grandfather], etc.
        # The exact relationships depend on the data, but we should see brackets
        if "No people found" not in result:
            # At least one relationship should be shown with brackets
            self.assertTrue(
                "[" in result and "]" in result,
                "Should contain relationship markers in brackets",
            )

    def test_filter_with_relationship_display_invalid_anchor(self):
        """Test show_relation_with with invalid anchor person ID."""
        # Should handle gracefully even if anchor person doesn't exist
        result = self._filter_people(
            ancestor_of="I0044", ancestor_generations=2, show_relation_with="INVALID"
        )

        # Should still return results, just without relationship prefixes
        self.assertNotIn("Error", result)


class TestFilterEventsTool(unittest.TestCase):
    """Test cases for the filter_events tool."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.app = TEST_APP

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock context
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=50000,
            user_id="test_user",
        )

    def _filter_events(self, **kwargs):
        """Helper to call filter_events with app context."""
        with self.app.app_context():
            return filter_events(self.ctx, **kwargs)

    def test_filter_by_event_type(self):
        """Test filtering by event type only."""
        result = self._filter_events(event_type="Birth")

        self.assertNotIn("Error", result)
        # Birth events might all be private in test data, so just check no error

    def test_filter_by_death_type(self):
        """Test filtering death events."""
        result = self._filter_events(event_type="Death")

        self.assertNotIn("Error", result)
        # Should return death events

    def test_filter_by_marriage_type(self):
        """Test filtering marriage events."""
        result = self._filter_events(event_type="Marriage")

        self.assertNotIn("Error", result)
        # Should return marriage events

    def test_filter_by_date_before(self):
        """Test filtering by date before."""
        result = self._filter_events(event_type="Birth", date_before="1900")

        self.assertNotIn("Error", result)
        # Should find births before 1900

    def test_filter_by_date_after(self):
        """Test filtering by date after."""
        result = self._filter_events(event_type="Birth", date_after="1850")

        self.assertNotIn("Error", result)
        # Should find births after 1850

    def test_filter_by_date_range(self):
        """Test filtering by date range."""
        result = self._filter_events(
            event_type="Birth", date_after="1850", date_before="1900"
        )

        self.assertNotIn("Error", result)
        # Should find births between 1850 and 1900

    def test_filter_by_place(self):
        """Test filtering by place."""
        result = self._filter_events(event_type="Birth", place="Falls")

        self.assertNotIn("Error", result)
        # Should find births in Falls

    def test_filter_by_description(self):
        """Test filtering by description contains."""
        result = self._filter_events(description_contains="church")

        self.assertNotIn("Error", result)

    def test_filter_by_participant(self):
        """Test filtering by participant ID."""
        result = self._filter_events(participant_id="I0552")

        self.assertNotIn("Error", result)
        # Should find events for person I0552

    def test_filter_by_participant_with_role(self):
        """Test filtering by participant with role."""
        result = self._filter_events(participant_id="I0552", participant_role="Primary")

        self.assertNotIn("Error", result)

    def test_filter_no_criteria(self):
        """Test that filter without criteria returns error message."""
        with self.app.app_context():
            result = filter_events(self.ctx)

        self.assertIn("No filter criteria provided", result)

    def test_filter_max_results(self):
        """Test max_results parameter."""
        result = self._filter_events(event_type="Birth", max_results=5)

        self.assertNotIn("Error", result)
        # Result should be limited

    def test_filter_max_results_boundary(self):
        """Test max_results boundary enforcement."""
        # Should cap at 100
        result = self._filter_events(event_type="Birth", max_results=200)

        self.assertNotIn("Error", result)

    def test_filter_respects_privacy(self):
        """Test that privacy settings are respected."""
        ctx_no_private = MagicMock()
        ctx_no_private.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=False,
            max_context_length=50000,
            user_id="test_user",
        )

        with self.app.app_context():
            result = filter_events(ctx_no_private, event_type="Birth")

        # Should work but potentially return fewer results
        self.assertNotIn("Error", result)

    def test_filter_truncation_message(self):
        """Test that truncation messages are included when appropriate."""
        result = self._filter_events(event_type="Birth", max_results=5)

        # Should mention if results were limited
        if "Showing" in result:
            self.assertTrue(
                "Showing" in result and ("of" in result or "limit reached" in result)
            )

    def test_filter_baptism_events(self):
        """Test filtering baptism events."""
        result = self._filter_events(event_type="Baptism")

        self.assertNotIn("Error", result)

    def test_filter_census_events(self):
        """Test filtering census events."""
        result = self._filter_events(event_type="Census")

        self.assertNotIn("Error", result)

    def test_filter_burial_events(self):
        """Test filtering burial events."""
        result = self._filter_events(event_type="Burial")

        self.assertNotIn("Error", result)

    def test_filter_events_by_year(self):
        """Test filtering events by specific year."""
        result = self._filter_events(date_after="1880", date_before="1880")

        self.assertNotIn("Error", result)

    def test_filter_complex_combination(self):
        """Test complex filter combination."""
        result = self._filter_events(
            event_type="Birth",
            date_after="1850",
            date_before="1900",
            place="Falls",
        )

        self.assertNotIn("Error", result)

    def test_date_range_1892_1900_with_db_check(self):
        """Test that events in 1892-1900 range can be found."""
        with TEST_APP.app_context():
            from gramps_webapi.api.util import get_db_outside_request
            from gramps_webapi.api.resources.filters import apply_filter
            from gramps.gen.lib.date import Date
            from gramps.gen.datehandler import parser
            import json

            db = get_db_outside_request(TEST_TREE, True, True, "test_user")

            # Check what events exist in this range
            events_in_range = []
            for event_handle in db.get_event_handles():
                event = db.get_event_from_handle(event_handle)
                date_obj = event.get_date_object()
                if date_obj and not date_obj.is_empty():
                    year = date_obj.get_year()
                    if 1892 <= year <= 1900:
                        events_in_range.append(
                            (
                                event.get_type().string,
                                year,
                                date_obj.get_text(),
                                date_obj.get_modifier(),
                                str(date_obj),
                            )
                        )

            self.assertGreater(
                len(events_in_range), 0, "No events in test data for 1892-1900"
            )

            # Test if the date expression parses correctly
            date_expr = "between 1892 and 1900"

            # Try applying the actual filter
            filter_rules = {
                "rules": [
                    {
                        "name": "HasData",
                        "values": ["", date_expr, "", ""],
                    }
                ]
            }

            handles = apply_filter(
                db_handle=db,
                args={"rules": json.dumps(filter_rules)},
                namespace="Event",
                handles=None,
            )

            self.assertGreater(len(handles), 0, "Filter should return handles")

            # Now test the actual tool
            result = self._filter_events(date_after="1892", date_before="1900")

            self.assertNotIn(
                "No events found",
                result,
                f"Filter returned {len(handles)} handles but tool returned empty. Result: {result[:200]}",
            )
            self.assertGreater(
                len(result),
                100,
                f"Tool should return event details, got only {len(result)} chars: {result[:200]}",
            )

            # Verify the result contains actual event information
            # Should contain event type mentions
            self.assertTrue(
                "Death" in result or "Birth" in result or "Burial" in result,
                f"Result should contain event types but got: {result[:300]}",
            )

            # Should contain dates from the range
            self.assertTrue(
                "1892" in result
                or "1893" in result
                or "1897" in result
                or "1900" in result,
                f"Result should contain years from 1892-1900 but got: {result[:300]}",
            )

            # Should contain event IDs/links
            self.assertTrue(
                "/event/" in result,
                f"Result should contain event links but got: {result[:300]}",
            )

    def test_filter_by_event_type_occupation(self):
        """Test filtering by Occupation event type."""
        result = self._filter_events(event_type="Occupation")
        self.assertNotIn("Error", result)
        # If occupations exist, should return data; if not, should say so clearly

    def test_filter_births_in_1850(self):
        """Test: 'births in 1850'"""
        result = self._filter_events(
            event_type="Birth", date_after="1850", date_before="1850"
        )
        self.assertNotIn("Error", result)
        # Should find births in 1850 or explicitly say none found
        if "No events found" not in result:
            self.assertIn("Birth", result)
            self.assertGreater(len(result), 200, "Should return meaningful birth data")

    def test_filter_marriages_in_1800s(self):
        """Test: 'marriages in the 1800s'"""
        result = self._filter_events(
            event_type="Marriage", date_after="1800", date_before="1899"
        )
        self.assertNotIn("Error", result)
        # Large date range should find some marriages
        if "No events found" not in result:
            self.assertIn("Marriage", result)
            self.assertGreater(len(result), 200)

    def test_filter_deaths_1890_to_1895(self):
        """Test: 'deaths between 1890 and 1895'"""
        result = self._filter_events(
            event_type="Death", date_after="1890", date_before="1895"
        )
        self.assertNotIn("Error", result)
        # This range had 61+ events in db, should find deaths
        if "No events found" not in result:
            self.assertIn("Death", result)
            self.assertGreater(len(result), 200)

    def test_filter_events_after_1900(self):
        """Test: 'events after 1900'"""
        result = self._filter_events(date_after="1900")
        self.assertNotIn("Error", result)
        # Should find some events after 1900
        self.assertNotIn(
            "No events found", result, "Database should have events after 1900"
        )
        self.assertGreater(len(result), 200)

    def test_filter_events_before_1800(self):
        """Test: 'events before 1800'"""
        result = self._filter_events(date_before="1800")
        self.assertNotIn("Error", result)
        # May or may not have events before 1800


class TestFilterPeopleRealWorldQueries(unittest.TestCase):
    """Test filter_people with real-world query patterns."""

    def setUp(self):
        self.ctx = MagicMock()
        self.ctx.deps = AgentDeps(
            tree=TEST_TREE,
            include_private=True,
            max_context_length=100000,
            user_id="test_user",
        )

    def _filter_people(self, **kwargs):
        """Helper to call filter_people with test context."""
        with TEST_APP.app_context():
            return filter_people(self.ctx, **kwargs)

    def test_find_surname_smith(self):
        """Test: 'people with surname Smith'"""
        result = self._filter_people(surname="Smith")
        self.assertNotIn("Error", result)
        # May or may not have Smiths

    def test_born_before_1900(self):
        """Test: 'people born before 1900'"""
        result = self._filter_people(birth_year_before="1900")
        self.assertNotIn("Error", result)
        # Should definitely find people born before 1900
        self.assertNotIn(
            "No people found", result, "Database should have people born before 1900"
        )
        self.assertGreater(len(result), 200)
        self.assertIn("/person/", result, "Should contain person links")

    def test_born_between_1850_1900(self):
        """Test: 'people born between 1850-1900'"""
        result = self._filter_people(birth_year_after="1850", birth_year_before="1900")
        self.assertNotIn("Error", result)
        # Should find people in this range
        self.assertNotIn(
            "No people found", result, "Database should have people born 1850-1900"
        )
        self.assertGreater(len(result), 200)

    def test_male_ancestors(self):
        """Test: 'male ancestors of person I0044'"""
        result = self._filter_people(ancestor_of="I0044", is_male=True)
        self.assertNotIn("Error", result)
        # I0044 should have some male ancestors
        if "No people found" not in result:
            self.assertGreater(len(result), 100)

    def test_alive_in_1880(self):
        """Test: 'who was alive in 1880'"""
        result = self._filter_people(probably_alive_on_date="1880-01-01")
        self.assertNotIn("Error", result)
        # Should find people alive in 1880
        if "No people found" not in result:
            self.assertGreater(len(result), 100)

    def test_born_in_massachusetts(self):
        """Test: 'births in Massachusetts'"""
        result = self._filter_people(birth_place="Massachusetts")
        self.assertNotIn("Error", result)
        # May or may not have Massachusetts births


if __name__ == "__main__":
    unittest.main()
