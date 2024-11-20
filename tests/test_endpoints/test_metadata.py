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

"""Tests for the /api/metadata endpoint using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import check_conforms_to_schema, check_requires_token

TEST_URL = BASE_URL + "/metadata/"


class TestMetadata(unittest.TestCase):
    """Test cases for the /api/metadata endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_metadata_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_metadata_conforms_to_schema(self):
        """Test conforms to schema."""
        res = check_conforms_to_schema(self, TEST_URL, "Metadata")
        assert res["database"]["type"] == "sqlite"
        assert "search" in res
        assert "sifts" in res["search"]
        assert "version" in res["search"]["sifts"]
        assert "count" in res["search"]["sifts"]
        assert res["search"]["sifts"]["count"] > 1
