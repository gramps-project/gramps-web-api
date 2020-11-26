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

"""Tests for the /api/media endpoints using example_gramps."""

import unittest
from typing import List

from jsonschema import RefResolver, validate

from tests.test_endpoints import API_SCHEMA, get_object_count, get_test_client
from tests.test_endpoints.runners import (
    run_test_endpoint_extend,
    run_test_endpoint_gramps_id,
    run_test_endpoint_keys,
    run_test_endpoint_rules,
    run_test_endpoint_skipkeys,
    run_test_endpoint_strip,
)


class TestMedia(unittest.TestCase):
    """Test cases for the /api/media endpoint for a list of media."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_media_endpoint(self):
        """Test reponse for media."""
        # check expected number of media found
        result = self.client.get("/api/media/")
        self.assertEqual(len(result.json), get_object_count("media"))
        # check first record is expected media
        self.assertEqual(result.json[0]["gramps_id"], "O0000")
        self.assertEqual(result.json[0]["handle"], "b39fe1cfc1305ac4a21")
        self.assertEqual(result.json[0]["path"], "scanned_microfilm.png")
        # check last record is expected media
        last = len(result.json) - 1
        self.assertEqual(result.json[last]["gramps_id"], "O0009")
        self.assertEqual(result.json[last]["handle"], "78V2GQX2FKNSYQ3OHE")
        self.assertEqual(result.json[last]["path"], "Gunnlaugur_Larusson_-_Yawn.jpg")

    def test_media_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/media/?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_media_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        driver = {
            "gramps_id": "O0006",
            "handle": "F0QIGQFT275JFJ75E8",
            "path": "Alimehemet.jpg",
        }
        run_test_endpoint_gramps_id(self, "/api/media/", driver)

    def test_media_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/media/")

    def test_media_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(self, "/api/media/", ["checksum", "path", "mime"])

    def test_media_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self, "/api/media/", ["citation_list", "desc", "tag_list"]
        )

    def test_media_endpoint_rules(self):
        """Test some responses for the rules parm."""
        driver = {
            400: ['{"rules"[{"name":"MediaPrivate"}]}'],
            422: [
                '{"some":"where","rules":[{"name":"MediaPrivate"}]}',
                '{"function":"none","rules":[{"name":"MediaPrivate"}]}',
            ],
            404: ['{"rules":[{"name":"PigsInSpace"}]}'],
            200: [
                '{"rules":[{"name":"MediaPrivate"}]}',
                '{"rules":[{"name":"HasTag","values":["ToDo"]},'
                + '{"name":"MediaPrivate"}]}',
                '{"function":"or","rules":[{"name":"HasTag","values":["ToDo"]},'
                + '{"name":"MediaPrivate"}]}',
                '{"function":"xor","rules":[{"name":"HasTag","values":["ToDo"]},'
                + '{"name":"MediaPrivate"}]}',
                '{"function":"one","rules":[{"name":"HasTag","values":["ToDo"]},'
                + '{"name":"MediaPrivate"}]}',
                '{"invert":true,"rules":[{"name":"MediaPrivate"}]}',
            ],
        }
        run_test_endpoint_rules(self, "/api/media/", driver)

    def test_media_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/media/", driver, ["O0006"])

    def test_media_endpoint_schema(self):
        """Test all media against the media schema."""
        result = self.client.get("/api/media/?extend=all")
        # check expected number of media found
        self.assertEqual(len(result.json), get_object_count("media"))
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for media in result.json:
            validate(
                instance=media,
                schema=API_SCHEMA["definitions"]["Media"],
                resolver=resolver,
            )


class TestMediaHandle(unittest.TestCase):
    """Test cases for the /api/media/{handle} endpoint for specific media."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_media_handle_endpoint_404(self):
        """Test response for a bad handle."""
        # check 404 returned for non-existent media
        result = self.client.get("/api/media/does_not_exist")
        self.assertEqual(result.status_code, 404)

    def test_media_handle_endpoint(self):
        """Test response for specific media."""
        # check expected media returned
        result = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM")
        self.assertEqual(result.json["gramps_id"], "O0008")
        self.assertEqual(result.json["path"], "654px-Aksel_Andersson.jpg")

    def test_media_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned for bad parm
        result = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_media_handle_endpoint_strip(self):
        """Test response for strip parm."""
        run_test_endpoint_strip(self, "/api/media/B1AUFQV7H8R9NR4SZM")

    def test_media_handle_endpoint_keys(self):
        """Test response for keys parm."""
        run_test_endpoint_keys(
            self,
            "/api/media/B1AUFQV7H8R9NR4SZM",
            ["handle", "attribute_list", "path"],
        )

    def test_media_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        run_test_endpoint_skipkeys(
            self,
            "/api/media/B1AUFQV7H8R9NR4SZM",
            ["handle", "note_list", "private"],
        )

    def test_media_handle_endpoint_extend(self):
        """Test response for extend parm."""
        driver = [
            {"arg": "citation_list", "key": "citations", "type": List},
            {"arg": "note_list", "key": "notes", "type": List},
            {"arg": "tag_list", "key": "tags", "type": List},
        ]
        run_test_endpoint_extend(self, "/api/media/B1AUFQV7H8R9NR4SZM", driver)

    def test_media_handle_endpoint_schema(self):
        """Test the media schema with extensions."""
        # check media record conforms to expected schema
        result = self.client.get("/api/media/B1AUFQV7H8R9NR4SZM?extend=all")
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Media"],
            resolver=resolver,
        )
