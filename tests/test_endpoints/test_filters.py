#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the /api/filters endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from gramps_webapi.const import GRAMPS_NAMESPACES
from tests.test_endpoints import API_SCHEMA, get_test_client
from tests.test_endpoints.runners import run_test_filters_endpoint_namespace


class TestAllFilters(unittest.TestCase):
    """Test cases for the /api/filters endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_schema(self):
        """Test against the filters schema."""
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        result = self.client.get("/api/filters/")
        for namespace in GRAMPS_NAMESPACES:
            # check present in response
            self.assertIn(namespace, result.json)
            # check against schema
            validate(
                instance=result.json[namespace],
                schema=API_SCHEMA["definitions"]["NamespaceFilters"],
                resolver=resolver,
            )


class TestFilters(unittest.TestCase):
    """Test cases for the /api/filters/{namespace} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_404(self):
        """Test response for unsupported namespace."""
        # check 404 returned for non-existent namespace
        result = self.client.get("/api/filters/nothing")
        self.assertEqual(result.status_code, 404)

    def test_filters_endpoint_schema(self):
        """Test all namespaces against the filters schema."""
        for namespace in GRAMPS_NAMESPACES:
            result = self.client.get("/api/filters/" + namespace)
            # check no custom filters present yet
            self.assertEqual(result.json["filters"], [])
            # check rules were returned
            self.assertIn("rules", result.json)
            # check all rule records found conform to expected schema
            resolver = RefResolver(
                base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA}
            )
            for rule in result.json["rules"]:
                validate(
                    instance=rule,
                    schema=API_SCHEMA["definitions"]["FilterRuleDescription"],
                    resolver=resolver,
                )


class TestFiltersPeople(unittest.TestCase):
    """Test cases for the /api/filters/people endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_people_filter(self):
        """Test creation and application of a people filter."""
        payload = {
            "comment": "Test person filter",
            "name": 123,
            "rules": [{"name": "IsMale"}, {"name": "MultipleMarriages"}],
        }
        run_test_filters_endpoint_namespace(self, "people", payload)


class TestFiltersFamilies(unittest.TestCase):
    """Test cases for the /api/filters/families endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_families_filter(self):
        """Test creation and application of a families filter."""
        payload = {
            "comment": "Test family filter",
            "name": 123,
            "rules": [
                {"name": "HasRelType", "values": ["Married"]},
                {"name": "IsBookmarked"},
            ],
        }
        run_test_filters_endpoint_namespace(self, "families", payload)


class TestFiltersEvents(unittest.TestCase):
    """Test cases for the /api/filters/events endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_events_filter(self):
        """Test creation and application of an events filter."""
        payload = {
            "comment": "Test event filter",
            "name": 123,
            "rules": [{"name": "HasType", "values": ["Death"]}, {"name": "HasNote"}],
        }
        run_test_filters_endpoint_namespace(self, "events", payload)


class TestFiltersPlaces(unittest.TestCase):
    """Test cases for the /api/filters/places endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_places_filter(self):
        """Test creation and application of a places filter."""
        payload = {
            "comment": "Test place filter",
            "name": 123,
            "rules": [{"name": "HasNoLatOrLon"}],
        }
        run_test_filters_endpoint_namespace(self, "places", payload)


class TestFiltersCitations(unittest.TestCase):
    """Test cases for the /api/filters/citations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_citations_filter(self):
        """Test creation and application of a citations filter."""
        payload = {
            "comment": "Test citation filter",
            "name": 123,
            "rules": [
                {"name": "MatchesPageSubstringOf", "values": ["Page"]},
                {"name": "HasNote"},
            ],
        }
        run_test_filters_endpoint_namespace(self, "citations", payload)


class TestFiltersSources(unittest.TestCase):
    """Test cases for the /api/filters/sources endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_sources_filter(self):
        """Test creation and application of a sources filter."""
        payload = {
            "comment": "Test source filter",
            "name": 123,
            "rules": [
                {"name": "MatchesTitleSubstringOf", "values": ["Church"]},
                {"name": "HasNote"},
            ],
        }
        run_test_filters_endpoint_namespace(self, "sources", payload)


class TestFiltersRepositories(unittest.TestCase):
    """Test cases for the /api/filters/repositories endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_repositories_filter(self):
        """Test creation and application of a repositories filter."""
        payload = {
            "comment": "Test repository filter",
            "name": 123,
            "rules": [{"name": "MatchesNameSubstringOf", "values": ["Library"]}],
        }
        run_test_filters_endpoint_namespace(self, "repositories", payload)


class TestFiltersMedia(unittest.TestCase):
    """Test cases for the /api/filters/media endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_media_filter(self):
        """Test creation and application of a media filter."""
        payload = {
            "comment": "Test media filter",
            "name": 123,
            "rules": [{"name": "HasTag", "values": ["ToDo"]}],
        }
        run_test_filters_endpoint_namespace(self, "media", payload)


class TestFiltersNotes(unittest.TestCase):
    """Test cases for the /api/filters/notes endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_notes_filter(self):
        """Test creation and application of a notes filter."""
        payload = {
            "comment": "Test notes filter",
            "name": 123,
            "rules": [{"name": "HasType", "values": ["Person Note"]}],
        }
        run_test_filters_endpoint_namespace(self, "notes", payload)
