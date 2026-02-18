"""Tests for remote embedding function."""

from unittest.mock import patch

import pytest

from gramps_webapi.api.search.embeddings import create_remote_embedding_function


@pytest.fixture
def mock_response_data():
    """Sample embedding API response with out-of-order indices."""
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"object": "embedding", "index": 2, "embedding": [0.7, 0.8, 0.9]},
        ],
        "model": "test-model",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }


class TestCreateRemoteEmbeddingFunction:
    """Tests for create_remote_embedding_function."""

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_returns_embeddings_in_order(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="test-model",
        )
        result = embed(["hello", "world", "foo"])

        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_posts_to_correct_url(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="test-model",
        )
        embed(["hello"])

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:11434/v1/embeddings"

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_strips_trailing_slash_from_base_url(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434/",
            model_name="test-model",
        )
        embed(["hello"])

        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:11434/v1/embeddings"

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_sends_model_and_input(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="nomic-embed-text",
        )
        embed(["hello", "world"])

        call_args = mock_post.call_args
        assert call_args[1]["json"] == {
            "model": "nomic-embed-text",
            "input": ["hello", "world"],
        }

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_sends_api_key_header(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="test-model",
            api_key="sk-test-key-123",
        )
        embed(["hello"])

        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-test-key-123"

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_no_auth_header_without_api_key(self, mock_post, mock_response_data):
        mock_post.return_value.json.return_value = mock_response_data
        mock_post.return_value.raise_for_status.return_value = None

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="test-model",
        )
        embed(["hello"])

        call_args = mock_post.call_args
        headers = call_args[1]["headers"]
        assert "Authorization" not in headers

    @patch("gramps_webapi.api.search.embeddings.requests.post")
    def test_raises_on_http_error(self, mock_post):
        from requests.exceptions import HTTPError

        mock_post.return_value.raise_for_status.side_effect = HTTPError("500 Server Error")

        embed = create_remote_embedding_function(
            base_url="http://localhost:11434",
            model_name="test-model",
        )

        with pytest.raises(HTTPError):
            embed(["hello"])
