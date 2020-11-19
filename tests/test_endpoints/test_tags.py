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

"""Tests for the /api/tags endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from tests.test_endpoints import API_SCHEMA, get_object_count, get_test_client


class TestTags(unittest.TestCase):
    """Test cases for the /api/tags endpoint for a list of tags."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tags_endpoint(self):
        """Test response for tags."""
        # check expected number of tags found
        result = self.client.get("/api/tags/")
        self.assertEqual(len(result.json), get_object_count("tags"))
        # check first record is expected tag
        self.assertEqual(result.json[0]["name"], "complete")
        # check last record is expected tag
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["name"], "ToDo")

    def test_tags_endpoint_schema(self):
        """Test all tags against the tag schema."""
        # check all records found conform to expected schema
        result = self.client.get("/api/tags/")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for tag in result.json:
            validate(
                instance=tag, schema=API_SCHEMA["definitions"]["Tag"], resolver=resolver
            )


class TestTagsHandle(unittest.TestCase):
    """Test cases for the /api/tags/{handle} endpoint for a tag."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_tags_handle_endpoint_404(self):
        """Test non-existent tag response."""
        # check 404 returned for non-existent tag
        result = self.client.get("/api/tags/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_tags_handle_endpoint(self):
        """Test tag response."""
        # check expected tag returned
        result = self.client.get("/api/tags/bb80c2b235b0a1b3f49")
        self.assertEqual(result.json["name"], "ToDo")

    def test_tag_handle_endpoint_schema(self):
        """Test the tag schema with extensions."""
        # check tag record conforms to expected schema
        result = self.client.get("/api/tags/bb80c2b235b0a1b3f49")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Tag"],
            resolver=resolver,
        )
