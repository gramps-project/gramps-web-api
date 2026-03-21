#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021      David Straub
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

"""Test consistent version numbers."""

import unittest

from gramps_webapi import __version__
from gramps_webapi.app import create_app


class TestVersion(unittest.TestCase):
    """Test the version specifiers are consistent."""

    @classmethod
    def setUpClass(cls):
        """Set up a minimal app and fetch the live OpenAPI spec."""
        app = create_app(
            {"TREE": "test", "SECRET_KEY": "test", "USER_DB_URI": "sqlite://"},
            config_from_env=False,
        )
        with app.test_client() as client:
            response = client.get("/api/openapi.json")
            assert (
                response.status_code == 200
            ), f"Failed to fetch OpenAPI spec: {response.status_code}"
            cls.spec = response.get_json()
            assert cls.spec is not None, "OpenAPI spec returned non-JSON response"

    def test_version(self):
        """Test version in package and live OpenAPI spec are equal."""
        self.assertEqual(__version__, self.spec["info"]["version"])

    def test_openapi_version(self):
        """Test the spec is valid OpenAPI 3.0.x."""
        self.assertTrue(self.spec.get("openapi", "").startswith("3.0"))
