#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the /api/filters endpoints using example_gramps."""

import uuid
import unittest

from jsonschema import validate

from gramps_webapi.const import GRAMPS_NAMESPACES

from . import API_RESOLVER, API_SCHEMA, BASE_URL, get_test_client
from .checks import (
    check_filter_create_update_delete,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/filters/"


class TestAllFilters(unittest.TestCase):
    """Test cases for the /api/filters endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_filters_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_filters_conforms_to_schema(self):
        """Test conforms to schema."""
        rv = check_success(self, TEST_URL)
        for namespace in GRAMPS_NAMESPACES:
            self.assertIn(namespace, rv)
            validate(
                instance=rv[namespace],
                schema=API_SCHEMA["definitions"]["NamespaceFilters"],
                resolver=API_RESOLVER,
            )

    def test_get_filters_validate_sematics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?test")


class TestFilters(unittest.TestCase):
    """General test cases for the /api/filters/{namespace} endpoints."""

    #    These are safe to run in parallel, the create/update/delete ones
    #    must be serialized for now and are in separate test classes.

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_filters_namespace_requires_token(self):
        """Test authorization required."""
        rv = check_success(self, TEST_URL)
        for namespace in rv:
            check_requires_token(self, TEST_URL + namespace)

    def test_get_filters_namespace_missing_content(self):
        """Test response for missing resource."""
        check_resource_missing(self, TEST_URL + "nothing")

    def test_get_filters_namespace_validate_sematics(self):
        """Test invalid parameters and values."""
        for namespace in GRAMPS_NAMESPACES:
            check_invalid_semantics(self, TEST_URL + namespace + "?test")

    def test_get_filters_namespace_custom_filters_empty(self):
        """Test all namespaces have no custom filters yet."""
        for namespace in GRAMPS_NAMESPACES:
            rv = check_success(self, TEST_URL + namespace)
            self.assertEqual(rv["filters"], [])
            self.assertIn("rules", rv)

    def test_get_filters_namespace_rules_conform_to_schema(self):
        """Test all namespace rule sets conform to schema."""
        for namespace in GRAMPS_NAMESPACES:
            rv = check_success(self, TEST_URL + namespace)
            for rule in rv["rules"]:
                validate(
                    instance=rule,
                    schema=API_SCHEMA["definitions"]["FilterRuleDescription"],
                    resolver=API_RESOLVER,
                )

    def test_get_filters_namespace_rules_validate_semantics(self):
        """Test invalid rule parameter for each namespace."""
        for namespace in GRAMPS_NAMESPACES:
            check_invalid_semantics(self, TEST_URL + namespace + "?rules", check="base")

    def test_get_filters_namespace_rule_missing_content(self):
        """Test response for missing rule content."""
        for namespace in GRAMPS_NAMESPACES:
            check_resource_missing(
                self, TEST_URL + namespace + "?rules=ReallyNotARealRule"
            )

    def test_get_filters_namespace_rule_expected_result(self):
        """Test that rule parameter returns expected result."""
        for namespace in GRAMPS_NAMESPACES:
            rv = check_success(self, TEST_URL + namespace + "?rules=HasTag")
            self.assertEqual(len(rv["rules"]), 1)
            self.assertEqual(rv["rules"][0]["rule"], "HasTag")

    def test_get_filters_namespace_filters_validate_semantics(self):
        """Test invalid rule parameter for each namespace."""
        for namespace in GRAMPS_NAMESPACES:
            check_invalid_semantics(
                self, TEST_URL + namespace + "?filters", check="base"
            )

    def test_get_filters_namespace_filters_missing_content(self):
        """Test response for missing filters content."""
        for namespace in GRAMPS_NAMESPACES:
            check_resource_missing(
                self, TEST_URL + namespace + "?filters=ReallyNotARealFilter"
            )
            check_resource_missing(self, TEST_URL + namespace + "/ReallyNotARealFilter")


class TestFiltersPeople(unittest.TestCase):
    """Specific test cases for the /api/filters/people endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_create_update_delete(self):
        """Test creation, application, update, and deletion of filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "people")


class TestFiltersFamilies(unittest.TestCase):
    """Specific test cases for the /api/filters/families endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_families_filter(self):
        """Test creation and application of a families filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "families")


class TestFiltersEvents(unittest.TestCase):
    """Specific test cases for the /api/filters/events endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_events_filter(self):
        """Test creation and application of an events filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "events")


class TestFiltersPlaces(unittest.TestCase):
    """Specific test cases for the /api/filters/places endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_places_filter(self):
        """Test creation and application of a places filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "places")


class TestFiltersCitations(unittest.TestCase):
    """Specific test cases for the /api/filters/citations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_citations_filter(self):
        """Test creation and application of a citations filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "citations")


class TestFiltersSources(unittest.TestCase):
    """Specific test cases for the /api/filters/sources endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_sources_filter(self):
        """Test creation and application of a sources filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "sources")


class TestFiltersRepositories(unittest.TestCase):
    """Specific test cases for the /api/filters/repositories endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_repositories_filter(self):
        """Test creation and application of a repositories filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "repositories")


class TestFiltersMedia(unittest.TestCase):
    """Specific test cases for the /api/filters/media endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_media_filter(self):
        """Test creation and application of a media filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "media")


class TestFiltersNotes(unittest.TestCase):
    """Specific test cases for the /api/filters/notes endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filters_endpoint_notes_filter(self):
        """Test creation and application of a notes filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "notes")


def make_handle() -> str:
    """Make a new valid handle."""
    return str(uuid.uuid4())


class TestHasAssociationType(unittest.TestCase):
    """Test cases for the HasAssociationType filter."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_has_association_type(self):
        payload = {}
        # check authorization required to post to endpoint
        handle = make_handle()
        payload = {
            "_class": "Person",
            "handle": handle,
            "person_ref_list": [
                {
                    "_class": "PersonRef",
                    "rel": "DNA",
                    "ref": handle,  # self-reference, why not
                }
            ],
        }
        headers = fetch_header(self.client)
        url = '/api/people/?rules={"rules":[{"name":"HasAssociationType","values":["DNA"]}]}'
        # no result
        rv = self.client.get(url, headers=headers)
        assert rv.json == []
        # add person
        rv = self.client.post("/api/people/", json=payload, headers=headers)
        assert rv.status_code == 201
        # one result
        rv = self.client.get(url, headers=headers)
        assert rv.json
        assert rv.json[0]["handle"] == handle
        # no result for wrong type
        rv = self.client.get(url.replace("DNA", "NotDNA"), headers=headers)
        assert rv.json == []
        # delete person
        rv = self.client.delete(f"/api/people/{handle}", headers=headers)
        assert rv.status_code == 200
        # no result
        rv = self.client.get(url, headers=headers)
        assert rv.json == []
