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

from . import BASE_URL, get_single_tree_test_client, get_test_client
from .checks import (
    check_filter_create_update_delete,
    check_filter_multi_tree_blocked,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
    get_openapi_schema_validator,
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
        schema, resolver = get_openapi_schema_validator(self.client, "NamespaceFilters")

        for namespace in GRAMPS_NAMESPACES:
            self.assertIn(namespace, rv)
            validate(
                instance=rv[namespace],
                schema=schema,
                resolver=resolver,
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
        schema, resolver = get_openapi_schema_validator(
            self.client, "FilterRuleDescription"
        )

        for namespace in GRAMPS_NAMESPACES:
            rv = check_success(self, TEST_URL + namespace)
            for rule in rv["rules"]:
                validate(
                    instance=rule,
                    schema=schema,
                    resolver=resolver,
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
    """Test /api/filters/people in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "people")


class TestFiltersFamilies(unittest.TestCase):
    """Test /api/filters/families in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "families")


class TestFiltersEvents(unittest.TestCase):
    """Test /api/filters/events in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "events")


class TestFiltersPlaces(unittest.TestCase):
    """Test /api/filters/places in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "places")


class TestFiltersCitations(unittest.TestCase):
    """Test /api/filters/citations in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "citations")


class TestFiltersSources(unittest.TestCase):
    """Test /api/filters/sources in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "sources")


class TestFiltersRepositories(unittest.TestCase):
    """Test /api/filters/repositories in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "repositories")


class TestFiltersMedia(unittest.TestCase):
    """Test /api/filters/media in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "media")


class TestFiltersNotes(unittest.TestCase):
    """Test /api/filters/notes in multi-tree setup (write ops must be blocked)."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_filter_write_blocked_multi_tree(self):
        """Test that filter mutations return 405 in multi-tree setup."""
        check_filter_multi_tree_blocked(self, TEST_URL, "notes")


class TestFiltersPeopleSingleTree(unittest.TestCase):
    """Test /api/filters/people CRUD in single-tree setup."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_single_tree_test_client()

    def test_filter_create_update_delete(self):
        """Test creation, application, update, and deletion of filter."""
        check_filter_create_update_delete(self, BASE_URL, TEST_URL, "people")

    def test_filter_write_requires_editor(self):
        """Test that POST, PUT, DELETE all require at least editor role."""
        from gramps_webapi.auth.const import ROLE_MEMBER

        header = fetch_header(self.client, role=ROLE_MEMBER)

        # POST blocked for non-editor on people
        payload = {
            "name": "PeoplePermissionTestFilter",
            "rules": [{"name": "HasTag", "values": ["ToDo"]}],
        }
        rv = self.client.post(TEST_URL + "people", json=payload, headers=header)
        self.assertEqual(rv.status_code, 403)

        # PUT blocked for non-editor on events (different namespace)
        payload = {
            "name": "EventsPermissionTestFilter",
            "rules": [{"name": "HasTag", "values": ["ToDo"]}],
        }
        rv = self.client.put(TEST_URL + "events", json=payload, headers=header)
        self.assertEqual(rv.status_code, 403)

        # DELETE blocked for non-editor on events
        rv = self.client.delete(
            TEST_URL + "events/EventsPermissionTestFilter", headers=header
        )
        self.assertEqual(rv.status_code, 403)


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


class TestIsReferencedByObjectType(unittest.TestCase):
    """Test cases for the IsReferencedByObjectType filter."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_is_referenced_by_object_type(self):
        """Test filtering media by the type of object referencing it."""
        media_handle = make_handle()
        person_handle = make_handle()
        headers = fetch_header(self.client)
        url = '/api/media/?rules={"rules":[{"name":"IsReferencedByObjectType","values":["Person"]}]}'
        url_event = '/api/media/?rules={"rules":[{"name":"IsReferencedByObjectType","values":["Event"]}]}'

        def handles(rv):
            return {obj["handle"] for obj in rv.json}

        # add media object (unreferenced) via /api/objects/
        media_payload = {"_class": "Media", "handle": media_handle}
        rv = self.client.post("/api/objects/", json=[media_payload], headers=headers)
        assert rv.status_code == 201

        # not yet referenced by any person → handle absent from Person filter
        rv = self.client.get(url, headers=headers)
        assert media_handle not in handles(rv)

        # not referenced by any event either
        rv = self.client.get(url_event, headers=headers)
        assert media_handle not in handles(rv)

        # add person with a media reference
        person_payload = {
            "_class": "Person",
            "handle": person_handle,
            "media_list": [{"_class": "MediaRef", "ref": media_handle}],
        }
        rv = self.client.post("/api/people/", json=person_payload, headers=headers)
        assert rv.status_code == 201

        # now the media handle appears in Person filter results
        rv = self.client.get(url, headers=headers)
        assert media_handle in handles(rv)

        # still absent from Event filter
        rv = self.client.get(url_event, headers=headers)
        assert media_handle not in handles(rv)

        # clean up
        rv = self.client.delete(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200
        rv = self.client.delete(f"/api/media/{media_handle}", headers=headers)
        assert rv.status_code == 200

        # handle gone from Person filter after cleanup
        rv = self.client.get(url, headers=headers)
        assert media_handle not in handles(rv)


class TestExpandedRuleList(unittest.TestCase):
    """Previously excluded rules (not in editor_rule_list) are now available."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()

    def test_match_id_of_rule_available_in_rule_list(self):
        """MatchIdOf appears in the people rule list."""
        headers = fetch_header(self.client)
        rv = self.client.get(
            BASE_URL + "/filters/people?rules=MatchIdOf", headers=headers
        )
        assert rv.status_code == 200
        assert rv.json["rules"][0]["rule"] == "MatchIdOf"

    def test_match_id_of_filters_by_gramps_id(self):
        """MatchIdOf returns the person with the given Gramps ID."""
        handle = make_handle()
        gramps_id = "I_TEST_MATCHID_" + handle[:8]
        headers = fetch_header(self.client)
        rv = self.client.post(
            "/api/people/",
            json={"_class": "Person", "handle": handle, "gramps_id": gramps_id},
            headers=headers,
        )
        assert rv.status_code == 201

        import json as _json

        url = f'/api/people/?rules={_json.dumps({"rules": [{"name": "MatchIdOf", "values": [gramps_id]}]})}'
        rv = self.client.get(url, headers=headers)
        assert rv.status_code == 200
        assert len(rv.json) == 1
        assert rv.json[0]["handle"] == handle

        rv = self.client.delete(f"/api/people/{handle}", headers=headers)
        assert rv.status_code == 200

    def test_search_name_rule_available(self):
        """SearchName appears in the people rule list."""
        headers = fetch_header(self.client)
        rv = self.client.get(
            BASE_URL + "/filters/people?rules=SearchName", headers=headers
        )
        assert rv.status_code == 200
        assert rv.json["rules"][0]["rule"] == "SearchName"


class TestNestedFilters(unittest.TestCase):
    """Inline nested filter composition using sub-filter specs inside rules."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()
        headers = fetch_header(cls.client)

        # Create three people with distinct tags to use as test fixtures.
        # tag_a only, tag_b only, both tags.
        cls.handle_a = make_handle()
        cls.handle_b = make_handle()
        cls.handle_ab = make_handle()
        cls.tag_a = "NestedFilterTestTagA_" + cls.handle_a[:6]
        cls.tag_b = "NestedFilterTestTagB_" + cls.handle_b[:6]

        for handle, tags in [
            (cls.handle_a, [cls.tag_a]),
            (cls.handle_b, [cls.tag_b]),
            (cls.handle_ab, [cls.tag_a, cls.tag_b]),
        ]:
            rv = cls.client.post(
                "/api/people/",
                json={
                    "_class": "Person",
                    "handle": handle,
                    "tag_list": [
                        {"_class": "TagBase", "tag": tag_name} for tag_name in tags
                    ],
                },
                headers=headers,
            )
            # tag_list on Person uses Tag handles, not names; use a note workaround:
            # just store the gramps_id instead so we can find them by ID later.
            # Re-create with gramps_id encoding the tag scenario.
            cls.client.delete(f"/api/people/{handle}", headers=headers)

        # Simpler: encode the scenario in gramps_id and use HasAssociationType
        # as a proxy for "has tag X". Two people with DNA, one without.
        cls.handle_dna = make_handle()
        cls.handle_no_dna = make_handle()
        cls.handle_dna_and_id = make_handle()
        cls.special_id = "I_NESTED_" + cls.handle_dna_and_id[:8]

        rv = cls.client.post(
            "/api/people/",
            json={
                "_class": "Person",
                "handle": cls.handle_dna,
                "person_ref_list": [
                    {"_class": "PersonRef", "rel": "DNA", "ref": cls.handle_dna}
                ],
            },
            headers=headers,
        )
        assert rv.status_code == 201

        rv = cls.client.post(
            "/api/people/",
            json={"_class": "Person", "handle": cls.handle_no_dna},
            headers=headers,
        )
        assert rv.status_code == 201

        rv = cls.client.post(
            "/api/people/",
            json={
                "_class": "Person",
                "handle": cls.handle_dna_and_id,
                "gramps_id": cls.special_id,
                "person_ref_list": [
                    {
                        "_class": "PersonRef",
                        "rel": "DNA",
                        "ref": cls.handle_dna_and_id,
                    }
                ],
            },
            headers=headers,
        )
        assert rv.status_code == 201

    @classmethod
    def tearDownClass(cls):
        headers = fetch_header(cls.client)
        for handle in [cls.handle_dna, cls.handle_no_dna, cls.handle_dna_and_id]:
            cls.client.delete(f"/api/people/{handle}", headers=headers)

    def _get_handles(self, url):
        headers = fetch_header(self.client)
        rv = self.client.get(url, headers=headers)
        assert rv.status_code == 200
        return {obj["handle"] for obj in rv.json}

    def test_or_nested_filter(self):
        """OR sub-filter: handle_dna OR handle_dna_and_id via MatchIdOf OR HasAssociationType."""
        import json as _json

        # Top-level filter: OR of two leaf rules.
        # Rule 1: HasAssociationType=DNA  → matches handle_dna and handle_dna_and_id
        # Rule 2: MatchIdOf=special_id    → matches handle_dna_and_id only
        # OR result should include both DNA handles.
        f = {
            "function": "or",
            "rules": [
                {"name": "HasAssociationType", "values": ["DNA"]},
                {"name": "MatchIdOf", "values": [self.special_id]},
            ],
        }
        url = f"/api/people/?rules={_json.dumps(f)}"
        result = self._get_handles(url)
        assert self.handle_dna in result
        assert self.handle_dna_and_id in result
        assert self.handle_no_dna not in result

    def test_and_nested_filter(self):
        """AND composition: HasAssociationType=DNA AND MatchIdOf=special_id."""
        import json as _json

        f = {
            "function": "and",
            "rules": [
                {"name": "HasAssociationType", "values": ["DNA"]},
                {"name": "MatchIdOf", "values": [self.special_id]},
            ],
        }
        url = f"/api/people/?rules={_json.dumps(f)}"
        result = self._get_handles(url)
        # Only handle_dna_and_id satisfies both
        assert self.handle_dna_and_id in result
        assert self.handle_dna not in result
        assert self.handle_no_dna not in result

    def test_inline_sub_filter(self):
        """Nested sub-filter: outer AND contains an inner OR sub-filter."""
        import json as _json

        # Outer AND:
        #   - leaf: MatchIdOf=special_id         → only handle_dna_and_id
        #   - sub-filter OR: HasAssociationType=DNA → handle_dna and handle_dna_and_id
        # AND of the two → only handle_dna_and_id
        f = {
            "function": "and",
            "rules": [
                {"name": "MatchIdOf", "values": [self.special_id]},
                {
                    "function": "or",
                    "rules": [
                        {"name": "HasAssociationType", "values": ["DNA"]},
                    ],
                },
            ],
        }
        url = f"/api/people/?rules={_json.dumps(f)}"
        result = self._get_handles(url)
        assert self.handle_dna_and_id in result
        assert self.handle_dna not in result
        assert self.handle_no_dna not in result

    def test_invert_on_sub_filter(self):
        """invert on a sub-filter inverts that sub-filter's result."""
        import json as _json

        # Outer AND:
        #   - leaf: HasAssociationType=DNA          → handle_dna, handle_dna_and_id
        #   - sub-filter OR + invert: NOT MatchIdOf=special_id
        #       → everyone except handle_dna_and_id
        # AND → handle_dna only
        f = {
            "function": "and",
            "rules": [
                {"name": "HasAssociationType", "values": ["DNA"]},
                {
                    "function": "or",
                    "invert": True,
                    "rules": [
                        {"name": "MatchIdOf", "values": [self.special_id]},
                    ],
                },
            ],
        }
        url = f"/api/people/?rules={_json.dumps(f)}"
        result = self._get_handles(url)
        assert self.handle_dna in result
        assert self.handle_dna_and_id not in result

    def test_invalid_rule_name_returns_404(self):
        """Unknown rule name in a nested filter returns 404."""
        import json as _json

        headers = fetch_header(self.client)
        f = {"rules": [{"name": "NonExistentRuleXYZ", "values": []}]}
        rv = self.client.get(
            f"/api/people/?rules={_json.dumps(f)}", headers=headers
        )
        assert rv.status_code == 404

    def test_missing_name_and_rules_returns_422(self):
        """A rules item with neither 'name' nor 'rules' fails schema validation."""
        import json as _json

        headers = fetch_header(self.client)
        f = {"rules": [{"values": ["something"]}]}
        rv = self.client.get(
            f"/api/people/?rules={_json.dumps(f)}", headers=headers
        )
        assert rv.status_code == 422
