#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Tests for the /api/relations endpoints using example_gramps."""

import unittest

from gramps_webapi.api import family_link_cache
from gramps_webapi.api.family_link_cache import clear_family_link_graphs
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/relations/"


class TestRelations(unittest.TestCase):
    """Test cases for the /api/relations/{handle1}/{handle2} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_relations_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L")

    def test_get_relations_expected_result(self):
        """Test request produces expected result."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L")
        self.assertEqual(
            rv,
            {
                "distance_common_origin": 5,
                "distance_common_other": 1,
                "relationship_string": "second great stepgrandaunt",
            },
        )

    def test_get_relations_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6IX")
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR1")
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6I/ORFKQC4KLWEGTGR19L")

    def test_get_relations_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?junk=1"
        )

    def test_get_relations_parameter_depth_validate_semantics(self):
        """Test invalid depth parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth",
            check="number",
        )

    def test_get_relations_parameter_depth_expected_result(self):
        """Test depth parameter working as expected."""
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth=5"
        )
        self.assertEqual(rv["relationship_string"], "")
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?depth=6"
        )
        self.assertEqual(rv["relationship_string"], "second great stepgrandaunt")

    def test_get_relations_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?locale",
            check="base",
        )

    def test_get_relations_parameter_locale_expected_result(self):
        """Test locale parameter working as expected."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L")
        self.assertEqual(rv["relationship_string"], "second great stepgrandaunt")
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L?locale=de"
        )
        self.assertEqual(rv["relationship_string"], "Stief-/Adoptivalttante")

    def test_get_relations_parameter_locale_expected_result_partner(self):
        """Test locale parameter working as expected."""
        rv = check_success(self, TEST_URL + "cc8205d87831c772e87/cc8205d872f532ab14e")
        self.assertEqual(rv["relationship_string"], "husband")
        rv = check_success(
            self, TEST_URL + "cc8205d87831c772e87/cc8205d872f532ab14e?locale=it"
        )
        self.assertEqual(rv["relationship_string"], "marito")


class TestRelationsAll(unittest.TestCase):
    """Test cases for the /api/relations/{handle1}/{handle2}/all endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_relations_all_requires_token(self):
        """Test authorization required."""
        check_requires_token(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all"
        )

    def test_get_relations_all_expected_result(self):
        """Test response for valid request."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all")
        self.assertIn("common_ancestors", rv[0])
        self.assertEqual(rv[0]["relationship_string"], "second great stepgrandaunt")

    def test_get_relations_all_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/all")
        check_resource_missing(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR1/all"
        )
        check_resource_missing(
            self, TEST_URL + "9BXKQC1PVLPYFMD6I/ORFKQC4KLWEGTGR19L/all"
        )

    def test_get_relations_all_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?junk=1"
        )

    def test_get_relations_all_parameter_depth_validate_semantics(self):
        """Test invalid depth parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth",
            check="number",
        )

    def test_get_relations_all_parameter_depth_expected_result(self):
        """Test depth parameter working as expected."""
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth=5"
        )
        self.assertEqual(rv, [{}])
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?depth=6"
        )
        self.assertEqual(rv[0]["relationship_string"], "second great stepgrandaunt")

    def test_get_relations_all_parameter_locale_validate_semantics(self):
        """Test invalid locale parameter and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?locale",
            check="base",
        )

    def test_get_relations_all_parameter_locale_expected_result(self):
        """Test locale parameter working as expected."""
        rv = check_success(self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all")
        self.assertEqual(rv[0]["relationship_string"], "second great stepgrandaunt")
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/all?locale=de"
        )
        self.assertEqual(rv[0]["relationship_string"], "Stief-/Adoptivalttante")


class TestRelationsPrivatePerson(unittest.TestCase):
    """Test relation endpoints with a person hidden by the private proxy."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_private_person_not_found_without_permission(self):
        """Without ViewPrivate, a private person must give 404, not 500."""
        header_owner = fetch_header(self.client, role=ROLE_OWNER)
        handle = "test_relations_private_person"
        rv = self.client.post(
            BASE_URL + "/people/",
            json={"_class": "Person", "handle": handle, "private": True},
            headers=header_owner,
        )
        self.assertEqual(rv.status_code, 201)
        try:
            for url in [
                f"{TEST_URL}9BXKQC1PVLPYFMD6IX/{handle}",
                f"{TEST_URL}{handle}/9BXKQC1PVLPYFMD6IX",
                f"{TEST_URL}9BXKQC1PVLPYFMD6IX/{handle}/all",
                f"{TEST_URL}{handle}/9BXKQC1PVLPYFMD6IX/all",
            ]:
                check_resource_missing(self, url, role=ROLE_GUEST)
        finally:
            self.client.delete(BASE_URL + f"/people/{handle}", headers=header_owner)


class TestRelationPaths(unittest.TestCase):
    """Test cases for the /api/relations/{handle1}/{handle2}/paths endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.url = TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L/paths"

    def test_get_relation_paths_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, self.url)

    def test_get_relation_paths_expected_result(self):
        """Test the shortest path and its labels."""
        rv = check_success(self, self.url)
        self.assertEqual(len(rv), 5)
        self.assertEqual(
            rv[0]["steps"],
            [
                {
                    "handle": "9BXKQC1PVLPYFMD6IX",
                    "link": None,
                    "relationship_string": "",
                },
                {
                    "handle": "HKTJQCIJD8RK9RJFO1",
                    "link": "parent",
                    "relationship_string": "father",
                },
                {
                    "handle": "TDTJQCGYRS2RCCGQN3",
                    "link": "parent",
                    "relationship_string": "grandfather",
                },
                {
                    "handle": "DPUJQCUYKKDPT78JJV",
                    "link": "parent",
                    "relationship_string": "great grandfather",
                },
                {
                    "handle": "GNUJQCL9MD64AM56OH",
                    "link": "parent",
                    "relationship_string": "second great grandfather",
                },
                {
                    "handle": "ORFKQC4KLWEGTGR19L",
                    "link": "sibling",
                    "relationship_string": "second great stepgrandaunt",
                },
            ],
        )
        lengths = [len(path["steps"]) for path in rv]
        self.assertEqual(lengths, sorted(lengths))
        for path in rv:
            self.assertEqual(path["steps"][0]["handle"], "9BXKQC1PVLPYFMD6IX")
            self.assertEqual(path["steps"][-1]["handle"], "ORFKQC4KLWEGTGR19L")

    def test_get_relation_paths_agrees_with_relation(self):
        """Test the last label of the shortest path is the relationship."""
        relation = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR19L"
        )
        rv = check_success(self, self.url)
        self.assertEqual(
            rv[0]["steps"][-1]["relationship_string"],
            relation["relationship_string"],
        )

    def test_get_relation_paths_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/ORFKQC4KLWEGTGR1/paths"
        )
        check_resource_missing(
            self, TEST_URL + "9BXKQC1PVLPYFMD6I/ORFKQC4KLWEGTGR19L/paths"
        )

    def test_get_relation_paths_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, self.url + "?junk=1")
        check_invalid_semantics(self, self.url + "?depth", check="number")
        check_invalid_semantics(self, self.url + "?depth=0")
        check_invalid_semantics(self, self.url + "?depth=31")
        check_invalid_semantics(self, self.url + "?max", check="number")
        check_invalid_semantics(self, self.url + "?max=0")
        check_invalid_semantics(self, self.url + "?max=51")
        check_invalid_semantics(self, self.url + "?blood_only=maybe")
        check_invalid_semantics(self, self.url + "?locale", check="list")

    def test_get_relation_paths_parameter_max(self):
        """Test the number of paths is limited."""
        self.assertEqual(len(check_success(self, self.url + "?max=2")), 2)

    def test_get_relation_paths_parameter_depth(self):
        """Test paths longer than depth are left out."""
        self.assertEqual(check_success(self, self.url + "?depth=4"), [])
        rv = check_success(self, self.url + "?depth=5")
        self.assertTrue(rv)
        for path in rv:
            self.assertLessEqual(len(path["steps"]), 6)

    def test_get_relation_paths_parameter_blood_only(self):
        """Test blood-only paths go up, at most once sideways, then down."""
        rv = check_success(self, self.url + "?blood_only=true&max=10")
        self.assertTrue(rv)
        for path in rv:
            links = "".join(step["link"][0] for step in path["steps"][1:])
            self.assertRegex(links, r"^p*s?c*$")

    def test_get_relation_paths_parameter_locale(self):
        """Test labels are translated."""
        rv = check_success(self, self.url + "?locale=de")
        self.assertEqual(rv[0]["steps"][1]["relationship_string"], "Vater")

    def test_get_relation_paths_same_person(self):
        """Test the path from a person to themselves."""
        rv = check_success(
            self, TEST_URL + "9BXKQC1PVLPYFMD6IX/9BXKQC1PVLPYFMD6IX/paths"
        )
        self.assertEqual(
            rv,
            [
                {
                    "steps": [
                        {
                            "handle": "9BXKQC1PVLPYFMD6IX",
                            "link": None,
                            "relationship_string": "",
                        }
                    ]
                }
            ],
        )

    def test_get_relation_paths_graph_per_permission(self):
        """Test owners and guests get their own cached graph."""
        clear_family_link_graphs()
        # an argument no other test uses, so the responses are not cached
        check_success(self, self.url + "?max=7")
        check_success(self, self.url + "?max=7", role=ROLE_GUEST)
        self.assertEqual(
            sorted(key[2] for key in family_link_cache._graphs), [False, True]
        )

    def test_get_relation_paths_private_person(self):
        """Without ViewPrivate, a private person must give 404."""
        header_owner = fetch_header(self.client, role=ROLE_OWNER)
        handle = "test_relation_paths_private_person"
        rv = self.client.post(
            BASE_URL + "/people/",
            json={"_class": "Person", "handle": handle, "private": True},
            headers=header_owner,
        )
        self.assertEqual(rv.status_code, 201)
        try:
            check_resource_missing(
                self, f"{TEST_URL}9BXKQC1PVLPYFMD6IX/{handle}/paths", role=ROLE_GUEST
            )
            rv = check_success(self, f"{TEST_URL}9BXKQC1PVLPYFMD6IX/{handle}/paths")
            self.assertEqual(rv, [])
        finally:
            self.client.delete(BASE_URL + f"/people/{handle}", headers=header_owner)
