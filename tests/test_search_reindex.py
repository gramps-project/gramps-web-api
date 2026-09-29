"""Tests for chunking when reindexing the semantic search index."""

import os
import tempfile
from unittest.mock import patch

import pytest

from gramps_webapi.api.search.indexer import SemanticSearchIndexer


@pytest.fixture
def db_url():
    """Provide a temporary SQLite DB URL, cleaned up after the test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    url = f"sqlite:///{path}"
    yield url
    os.unlink(path)


class FakeEmbedding:
    """Embedding function that records the size of every call."""

    def __init__(self):
        self.call_sizes: list[int] = []

    def __call__(self, texts):
        self.call_sizes.append(len(texts))
        return [[float(len(text)), 1.0] for text in texts]


def obj_dict(class_name, handle):
    text = f"{class_name} {handle}"
    return {
        "class_name": class_name,
        "handle": handle,
        "change": 0,
        "string_all": text,
        "string_public": text,
    }


def test_add_objects_chunked_respects_chunk_size(db_url):
    embed = FakeEmbedding()
    indexer = SemanticSearchIndexer(
        tree="mytree", db_url=db_url, embedding_function=embed
    )
    indexer._add_objects_chunked(
        (obj_dict("Note", f"h{i}") for i in range(25)), chunk_size=10
    )
    assert max(embed.call_sizes) == 10
    assert indexer.count(include_private=True) == 25


def test_reindex_incremental_is_chunked(db_url):
    embed = FakeEmbedding()
    indexer = SemanticSearchIndexer(
        tree="mytree", db_url=db_url, embedding_function=embed
    )
    # non-empty index, so reindex_incremental does not fall back to reindex_full
    indexer._add_objects([obj_dict("Note", "existing")])
    embed.call_sizes.clear()

    new = {"Person": {f"p{i}" for i in range(150)}}
    updated = {"Note": {"existing"} | {f"n{i}" for i in range(100)}}
    update_info = {"deleted": {}, "new": new, "updated": updated}
    total = 251
    chunk_size = indexer._chunk_size(total)

    with (
        patch.object(indexer, "_get_update_info", return_value=update_info),
        patch(
            "gramps_webapi.api.search.indexer.obj_strings_from_handle",
            side_effect=lambda db, class_name, handle, semantic: obj_dict(
                class_name, handle
            ),
        ),
    ):
        indexer.reindex_incremental(db_handle=None)

    assert max(embed.call_sizes) <= chunk_size < total
    assert indexer.count(include_private=True) == total
