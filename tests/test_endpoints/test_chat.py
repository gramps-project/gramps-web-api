#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024 David Straub
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

"""Test chat endpoint."""

import unittest
from unittest.mock import patch
from urllib.parse import quote

from gramps_webapi.auth import user_db
from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG

from . import BASE_URL, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/chat/"


class TestChat(unittest.TestCase):
    """Test cases for semantic search."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        # add objects
        header = fetch_header(cls.client, empty_db=True)
        obj = {
            "_class": "Note",
            "gramps_id": "N01",
            "text": {"_class": "StyledText", "string": "The sky is blue."},
        }
        rv = cls.client.post("/api/notes/", json=obj, headers=header)
        obj = {
            "_class": "Note",
            "gramps_id": "N02",
            "text": {"_class": "StyledText", "string": "Everyone loves Pizza."},
        }
        rv = cls.client.post("/api/notes/", json=obj, headers=header)
        assert rv.status_code == 201
        rv = cls.client.get("/api/metadata/", json=obj, headers=header)
        assert rv.status_code == 200
        assert rv.json["search"]["sifts"]["count_semantic"] == 2

    def test_search(self):
        header = fetch_header(self.client, empty_db=True)
        query = "What should I have for dinner tonight?"
        rv = self.client.get(
            f"/api/search/?semantic=1&query={quote(query)}", headers=header
        )
        assert rv.status_code == 200
        assert len(rv.json) == 2
