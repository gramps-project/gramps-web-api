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
        set_stored_model_name(
            db_url,
            "mytree",
            "sentence-transformers/distiluse-base-multilingual-cased-v2",
        )
        assert (
            get_stored_model_name(db_url, "mytree")
            == "sentence-transformers/distiluse-base-multilingual-cased-v2"
        )

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

    def test_skip_model_check_bypasses_mismatch_error(self, db_url):
        """skip_model_check=True must not raise even when stored model differs.

        This is the path used by the Celery full-reindex task and the CLI
        ``search --semantic index-full`` command — those are the operations
        that *fix* a mismatch, so they must not be blocked by it.
        """
        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        set_stored_model_name(db_url, "mytree", "old-model")
        # Must not raise:
        indexer = SemanticSearchIndexer(
            tree="mytree",
            db_url=db_url,
            model_name="new-model",
            skip_model_check=True,
        )
        # The new model name must still be stored on the instance so that
        # reindex_full() can write it after rebuilding the index.
        assert indexer.model_name == "new-model"

    def test_skip_model_check_preserves_db_url_for_post_reindex_write(self, db_url):
        """After skip_model_check=True construction, _db_url must be set.

        reindex_full() calls set_stored_model_name(self._db_url, ...) — if
        _db_url were cleared when skipping the check the metadata write after
        a full reindex would silently be skipped, leaving the old model recorded.
        """
        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        set_stored_model_name(db_url, "mytree", "old-model")
        indexer = SemanticSearchIndexer(
            tree="mytree",
            db_url=db_url,
            model_name="new-model",
            skip_model_check=True,
        )
        assert indexer._db_url == db_url

    def test_model_name_written_after_reindex_full(self, db_url):
        """reindex_full() must persist the new model name when done.

        Simulates the Celery / CLI full-reindex path: construct with
        skip_model_check=True, call reindex_full(), then verify the
        metadata reflects the new model so subsequent searches don't
        keep reporting a mismatch.
        """
        from unittest.mock import MagicMock, patch

        from gramps_webapi.api.search.indexer import SemanticSearchIndexer

        set_stored_model_name(db_url, "mytree", "old-model")

        indexer = SemanticSearchIndexer(
            tree="mytree",
            db_url=db_url,
            model_name="new-model",
            skip_model_check=True,
        )

        # Stub out the real indexing work so we don't need a live Gramps DB.
        with patch.object(
            SemanticSearchIndexer.__bases__[0],
            "reindex_full",
            return_value=None,
        ):
            mock_db = MagicMock()
            indexer.reindex_full(mock_db)

        assert get_stored_model_name(db_url, "mytree") == "new-model"


class TestEngineUrlHandling:
    """Verify that the SQLAlchemy engine layer handles edge-case URLs correctly."""

    def test_sqlite_url_with_absolute_path(self):
        """Engine creation must not raise for a standard absolute SQLite URL."""
        from gramps_webapi.api.search.metadata import _get_engine

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            engine = _get_engine(f"sqlite:///{path}")
            # A simple connect/disconnect should succeed.
            with engine.connect():
                pass
        finally:
            os.unlink(path)

    def test_sqlite_roundtrip_with_special_chars_in_values(self):
        """Special characters in stored values (not credentials) are preserved."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
            url = f"sqlite:///{path}"
        try:
            model = "org/model-name_v2.0+special"
            set_stored_model_name(url, "my/tree@id", model)
            assert get_stored_model_name(url, "my/tree@id") == model
        finally:
            os.unlink(path)
