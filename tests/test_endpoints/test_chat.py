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
from unittest.mock import patch, MagicMock
from urllib.parse import quote


from . import BASE_URL, get_test_client
from .util import fetch_header

from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_OWNER

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
        assert rv.json[0]["object"]["gramps_id"] == "N02"  # Pizza!
        assert rv.json[1]["object"]["gramps_id"] == "N01"

    @patch("gramps_webapi.api.llm.get_client")
    def test_chat(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        def mock_reply(system_prompt, user_prompt):
            if "Pizza" in system_prompt and "dinner" in user_prompt:
                return "Pizza of course!"
            else:
                return "I don't know."

        def mock_chat_completion_create(messages, model):
            return MagicMock(
                to_dict=lambda: {
                    "choices": [
                        {
                            "message": {
                                "content": mock_reply(
                                    messages[0]["content"], messages[1]["content"]
                                )
                            }
                        }
                    ]
                }
            )

        mock_client.chat.completions.create.side_effect = mock_chat_completion_create
        header = fetch_header(self.client, empty_db=True)
        header_editor = fetch_header(self.client, empty_db=True, role=ROLE_EDITOR)
        rv = self.client.get("/api/trees/", headers=header)
        assert rv.status_code == 200
        tree_id = rv.json[0]["id"]
        assert rv.status_code == 200
        rv = self.client.put(
            f"/api/trees/{tree_id}", json={"min_role_ai": ROLE_OWNER}, headers=header
        )
        assert rv.status_code == 200
        header = fetch_header(self.client, empty_db=True)
        header_editor = fetch_header(self.client, empty_db=True, role=ROLE_EDITOR)
        query = "What should I have for dinner tonight?"
        rv = self.client.post(
            "/api/chat/", json={"query": query}, headers=header_editor
        )
        assert rv.status_code == 403
        rv = self.client.post("/api/chat/", json={"query": query}, headers=header)
        assert rv.status_code == 200
        assert "response" in rv.json
        assert rv.json["response"] == "Pizza of course!"
