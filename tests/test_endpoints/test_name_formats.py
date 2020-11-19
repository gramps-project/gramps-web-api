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

"""Tests for the /api/name-formats endpoint using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestNameFormats(unittest.TestCase):
    """Test cases for the /api/name-formats endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_name_formats_endpoint_schema(self):
        """Test name formats against the name format schema."""
        # check record conforms to expected schema
        result = self.client.get("/api/name-formats/")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for name_format in result.json:
            validate(
                instance=name_format,
                schema=API_SCHEMA["definitions"]["NameFormat"],
                resolver=resolver,
            )
