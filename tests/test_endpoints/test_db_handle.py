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

"""Tests for the database handle used by endpoints."""

import unittest
from unittest.mock import patch

from gramps.gen.proxy.proxybase import ProxyDbBase

from gramps_webapi.api.util import ModifiedPrivateProxyDb, get_db_handle
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header


class TestDbHandle(unittest.TestCase):
    """Test the database handle returned by get_db_handle."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def _get_db_handle_for_request(self, role):
        """Return the database handles an endpoint gets during a request."""
        db_handles = []

        def recording_get_db_handle(readonly=True):
            db_handle = get_db_handle(readonly=readonly)
            db_handles.append(db_handle)
            return db_handle

        header = fetch_header(self.client, role=role)
        with patch(
            "gramps_webapi.api.resources.base.get_db_handle",
            side_effect=recording_get_db_handle,
        ):
            rv = self.client.get(
                f"{BASE_URL}/people/?keys=handle&page=1&pagesize=1", headers=header
            )
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(db_handles)
        return db_handles

    def test_private_proxy_applied_once(self):
        """Test a user without access to private records gets a single proxy."""
        for db_handle in self._get_db_handle_for_request(ROLE_GUEST):
            self.assertIsInstance(db_handle, ModifiedPrivateProxyDb)
            self.assertNotIsInstance(db_handle.db, ProxyDbBase)

    def test_no_proxy_with_private_access(self):
        """Test a user with access to private records gets the unproxied db."""
        for db_handle in self._get_db_handle_for_request(ROLE_OWNER):
            self.assertNotIsInstance(db_handle, ProxyDbBase)
