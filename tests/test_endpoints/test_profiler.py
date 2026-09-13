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
#

"""Smoke test for the endpoints used by the API profiler."""

import unittest

from gramps_webapi.profiler import (
    fetch_installation_info,
    get_default_endpoints,
    get_default_person_gramps_id,
    get_latest_transaction_id,
    get_query_endpoints,
)

from . import get_test_client
from .util import fetch_header


class TestProfilerEndpoints(unittest.TestCase):
    """Check that every profiled endpoint still succeeds."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_profiled_endpoints_succeed(self):
        """Every default and query endpoint returns 200."""
        headers = fetch_header(self.client)
        info = fetch_installation_info(self.client, headers, None)
        self.assertNotIn("error", info)
        person_handle = info["default_person_handle"]
        gramps_id = get_default_person_gramps_id(
            self.client, headers, None, person_handle
        )
        latest_transaction_id = get_latest_transaction_id(self.client, headers, None)
        # Without these, the person and history endpoints would be skipped
        self.assertIsNotNone(gramps_id)
        self.assertIsNotNone(latest_transaction_id)

        endpoints = get_default_endpoints(
            gramps_id, person_handle, latest_transaction_id
        )
        endpoints.extend(get_query_endpoints())
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint["name"]):
                rv = self.client.open(
                    endpoint["path"],
                    method=endpoint["method"],
                    headers=headers,
                    json=endpoint.get("json"),
                )
                self.assertEqual(rv.status_code, 200)
