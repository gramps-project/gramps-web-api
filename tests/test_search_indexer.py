"""Tests for the semantic search indexer."""

import os
import tempfile

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
    """Embedding function that records every text it is asked to embed."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return [[float(len(text)), 1.0] for text in texts]


def obj_dict(handle, string_all, string_public):
    return {
        "class_name": "Note",
        "handle": handle,
        "change": 0,
        "string_all": string_all,
        "string_public": string_public,
    }


def test_identical_public_text_is_embedded_once(db_url):
    embed = FakeEmbedding()
    indexer = SemanticSearchIndexer(
        tree="mytree", db_url=db_url, embedding_function=embed
    )
    indexer._add_objects(
        [
            obj_dict("h1", "same text", "same text"),
            obj_dict("h2", "full text", "redacted text"),
        ]
    )
    embedded = [text for call in embed.calls for text in call]
    assert sorted(embedded) == ["full text", "redacted text", "same text"]
    assert indexer.count(include_private=True) == 2
    assert indexer.count(include_private=False) == 2


def test_reused_vectors_are_stored_in_both_collections(db_url):
    embed = FakeEmbedding()
    indexer = SemanticSearchIndexer(
        tree="mytree", db_url=db_url, embedding_function=embed
    )
    indexer._add_objects([obj_dict("h1", "abc", "abc")])
    for include_private in [True, False]:
        _, hits = indexer.search(
            "abc", page=1, pagesize=10, include_private=include_private
        )
        assert [hit["handle"] for hit in hits] == ["h1"]
        assert hits[0]["score"] == pytest.approx(1.0)
