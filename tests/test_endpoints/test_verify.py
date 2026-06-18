#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for the /api/verify/ endpoint."""

import unittest

from gramps_webapi.auth.const import ROLE_GUEST, ROLE_MEMBER, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/trees/-/verify"


class TestVerify(unittest.TestCase):
    """Test cases for the /api/verify/ endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()

    def test_requires_token(self):
        """Unauthenticated request is rejected."""
        rv = self.client.post(TEST_URL)
        self.assertEqual(rv.status_code, 401)

    def test_returns_list(self):
        """Response body is a JSON array."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(TEST_URL, headers=header)
        self.assertEqual(rv.status_code, 201)
        self.assertIsInstance(rv.json, list)

    def test_results_nonempty(self):
        """Example DB produces at least one finding."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(TEST_URL, headers=header)
        self.assertEqual(rv.status_code, 201)
        self.assertIsInstance(rv.json, list)
        self.assertGreater(len(rv.json), 0)

    def test_result_fields(self):
        """Every item has the required fields with correct types."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(TEST_URL, headers=header)
        required = {
            "message", "object_type", "object_id", "object_handle",
            "name", "rule_id", "rule_params", "severity",
        }
        for item in rv.json:
            self.assertEqual(set(item.keys()), required)
            self.assertIn(item["severity"], ("error", "warning"))
            self.assertIn(item["object_type"], ("Person", "Family"))
            self.assertIsInstance(item["rule_id"], int)
            self.assertIsInstance(item["rule_params"], list)

    def test_threshold_param_changes_results(self):
        """Tightening the oldage threshold produces more OldAge findings."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv_strict = self.client.post(TEST_URL + "?oldage=50", headers=header)
        rv_lenient = self.client.post(TEST_URL + "?oldage=200", headers=header)
        self.assertEqual(rv_strict.status_code, 201)
        self.assertEqual(rv_lenient.status_code, 201)
        strict_old = [r for r in rv_strict.json if r["rule_id"] == 7]
        lenient_old = [r for r in rv_lenient.json if r["rule_id"] == 7]
        self.assertGreaterEqual(len(strict_old), len(lenient_old))

    def test_invalid_param_rejected(self):
        """Non-integer value for an integer param is rejected with 422."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(TEST_URL + "?oldage=notanumber", headers=header)
        self.assertEqual(rv.status_code, 422)

    def test_guest_forbidden(self):
        """Guest role lacks PERM_VIEW_PRIVATE and is denied."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        rv = self.client.post(TEST_URL, headers=header)
        self.assertEqual(rv.status_code, 403)

    def test_member_allowed(self):
        """Member role has PERM_VIEW_PRIVATE and is allowed."""
        header = fetch_header(self.client, role=ROLE_MEMBER)
        rv = self.client.post(TEST_URL, headers=header)
        self.assertEqual(rv.status_code, 201)


if __name__ == "__main__":
    unittest.main()
