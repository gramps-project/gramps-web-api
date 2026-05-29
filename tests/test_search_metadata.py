"""Tests for semantic search index metadata store."""

import os
import tempfile

import pytest

from gramps_webapi.api.search.metadata import (
    get_stored_model_name,
    set_stored_model_name,
)


@pytest.fixture
def db_url():
    """Provide a temporary SQLite DB URL, cleaned up after the test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    url = f"sqlite:///{path}"
    yield url
    os.unlink(path)


class TestGetStoredModelName:
    def test_returns_none_when_no_row(self, db_url):
        assert get_stored_model_name(db_url, "mytree") is None

    def test_returns_none_for_unknown_tree(self, db_url):
        set_stored_model_name(db_url, "tree1", "model-a")
        assert get_stored_model_name(db_url, "tree2") is None

    def test_returns_stored_model(self, db_url):
        set_stored_model_name(db_url, "mytree", "sentence-transformers/distiluse-base-multilingual-cased-v2")
        assert get_stored_model_name(db_url, "mytree") == "sentence-transformers/distiluse-base-multilingual-cased-v2"

    def test_trees_are_independent(self, db_url):
        set_stored_model_name(db_url, "tree1", "model-a")
        set_stored_model_name(db_url, "tree2", "model-b")
        assert get_stored_model_name(db_url, "tree1") == "model-a"
        assert get_stored_model_name(db_url, "tree2") == "model-b"


class TestSetStoredModelName:
    def test_write_and_read_back(self, db_url):
        set_stored_model_name(db_url, "mytree", "model-v1")
        assert get_stored_model_name(db_url, "mytree") == "model-v1"

    def test_update_overwrites_previous_model(self, db_url):
        set_stored_model_name(db_url, "mytree", "model-v1")
        set_stored_model_name(db_url, "mytree", "model-v2")
        assert get_stored_model_name(db_url, "mytree") == "model-v2"

    def test_idempotent_same_model(self, db_url):
        set_stored_model_name(db_url, "mytree", "model-v1")
        set_stored_model_name(db_url, "mytree", "model-v1")
        assert get_stored_model_name(db_url, "mytree") == "model-v1"

    def test_table_created_on_first_call(self, db_url):
        """Calling set before any ensure_metadata_table should not raise."""
        set_stored_model_name(db_url, "mytree", "model-v1")
        assert get_stored_model_name(db_url, "mytree") == "model-v1"


class TestSemanticIndexerModelCheck:
    """Test that SemanticSearchIndexer raises on model mismatch."""

    def test_raises_on_model_mismatch(self, db_url):
        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        set_stored_model_name(db_url, "mytree", "old-model")
        with pytest.raises(ValueError, match="old-model"):
            SemanticSearchIndexer(
                tree="mytree",
                db_url=db_url,
                model_name="new-model",
            )

    def test_no_error_when_no_stored_model(self, db_url):
        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        # Should not raise — existing deployment with no metadata yet
        SemanticSearchIndexer(
            tree="mytree",
            db_url=db_url,
            model_name="any-model",
        )

    def test_no_error_when_model_matches(self, db_url):
        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        set_stored_model_name(db_url, "mytree", "same-model")
        SemanticSearchIndexer(
            tree="mytree",
            db_url=db_url,
            model_name="same-model",
        )
