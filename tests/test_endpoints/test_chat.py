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

    @patch("gramps_webapi.api.llm.create_agent")
    def test_chat(self, mock_create_agent):
        from datetime import datetime
        from pydantic_ai import RunUsage

        # Mock the agent and its response
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        # Create a proper mock result that matches AgentRunResult API
        mock_result = MagicMock()
        mock_result.response.text = "Pizza of course!"
        mock_result.run_id = "test_run_123"
        # timestamp() is a method that returns datetime
        mock_result.timestamp.return_value = datetime.fromisoformat(
            "2025-12-05T10:00:00+00:00"
        )
        # usage() is a method that returns RunUsage
        mock_usage = RunUsage()
        mock_usage.requests = 1
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.tool_calls = 0
        mock_result.usage.return_value = mock_usage
        mock_result.all_messages.return_value = []
        mock_agent.run_sync.return_value = mock_result
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
        assert "metadata" not in rv.json  # Should not include metadata by default

    @patch("gramps_webapi.api.llm.create_agent")
    def test_chat_background(self, mock_create_agent):
        from datetime import datetime
        from pydantic_ai import RunUsage

        # Mock the agent and its response
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        # Create a proper mock result that matches AgentRunResult API
        mock_result = MagicMock()
        mock_result.response.text = "Pizza of course!"
        mock_result.run_id = "test_run_bg"
        # timestamp() is a method that returns datetime
        mock_result.timestamp.return_value = datetime.fromisoformat(
            "2025-12-05T10:30:00+00:00"
        )
        # usage() is a method that returns RunUsage
        mock_usage = RunUsage()
        mock_usage.requests = 1
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.tool_calls = 0
        mock_result.usage.return_value = mock_usage
        mock_result.all_messages.return_value = []
        mock_agent.run_sync.return_value = mock_result

        header = fetch_header(self.client, empty_db=True)

        # Set up permissions to allow AI chat for owner
        rv = self.client.get("/api/trees/", headers=header)
        assert rv.status_code == 200
        tree_id = rv.json[0]["id"]
        rv = self.client.put(
            f"/api/trees/{tree_id}", json={"min_role_ai": ROLE_OWNER}, headers=header
        )
        assert rv.status_code == 200

        # Refresh header after setting permissions
        header = fetch_header(self.client, empty_db=True)

        query = "What should I have for dinner tonight?"

        # Test with background=true query param (should return immediately with 200 since no Celery)
        rv = self.client.post(
            "/api/chat/?background=true", json={"query": query}, headers=header
        )
        # When CELERY_CONFIG is not set, the task runs synchronously and returns 200
        assert rv.status_code == 200
        assert "response" in rv.json
        assert rv.json["response"] == "Pizza of course!"

    @patch("gramps_webapi.api.llm.create_agent")
    def test_chat_verbose(self, mock_create_agent):
        """Test chat with verbose=true to include metadata."""
        from pydantic_ai import Agent
        from dataclasses import dataclass

        # Create a REAL agent with a real tool to get real result structure
        @dataclass
        class TestDeps:
            value: str = "test"

        real_agent = Agent("test", deps_type=TestDeps)

        @real_agent.tool
        def search_genealogy_database(ctx, query: str, max_results: int = 20) -> str:
            """Mock search tool."""
            return f"Found results for {query}"

        # Mock create_agent to return our real agent
        mock_create_agent.return_value = real_agent

        header = fetch_header(self.client, empty_db=True)

        # Set up permissions
        rv = self.client.get("/api/trees/", headers=header)
        assert rv.status_code == 200
        tree_id = rv.json[0]["id"]
        rv = self.client.put(
            f"/api/trees/{tree_id}", json={"min_role_ai": ROLE_OWNER}, headers=header
        )
        assert rv.status_code == 200

        header = fetch_header(self.client, empty_db=True)
        query = "What should I have for dinner tonight?"

        # Test with verbose=true
        rv = self.client.post(
            "/api/chat/?verbose=true", json={"query": query}, headers=header
        )
        assert rv.status_code == 200
        assert "response" in rv.json
        # The real agent will produce some response
        assert isinstance(rv.json["response"], str)
        assert len(rv.json["response"]) > 0

        # Check metadata is included
        assert "metadata" in rv.json
        metadata = rv.json["metadata"]
        assert "run_id" in metadata
        assert isinstance(metadata["run_id"], str)
        assert "timestamp" in metadata
        assert "usage" in metadata
        assert isinstance(metadata["usage"]["requests"], int)
        assert metadata["usage"]["requests"] >= 1
        assert isinstance(metadata["usage"]["total_tokens"], int)
        assert "tools_used" in metadata
        assert isinstance(metadata["tools_used"], list)
        # The agent will call the search tool
        if len(metadata["tools_used"]) > 0:
            assert metadata["tools_used"][0]["name"] == "search_genealogy_database"
            assert "step" in metadata["tools_used"][0]
            assert "args" in metadata["tools_used"][0]
