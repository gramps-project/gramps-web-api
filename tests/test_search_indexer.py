"""Tests for the search indexers."""

import os
import tempfile
from unittest.mock import patch

import pytest

from gramps_webapi.api.search.indexer import SearchIndexer


@pytest.fixture
def db_url():
    """Provide a temporary SQLite DB URL, cleaned up after the test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    url = f"sqlite:///{path}"
    yield url
    os.unlink(path)


def obj_dict(handle, string_all, string_public, private=False):
    return {
        "class_name": "Note",
        "handle": handle,
        "private": private,
        "change": 0,
        "string_all": string_all,
        "string_public": string_public,
    }


def test_private_object_not_in_public_index(db_url):
    indexer = SearchIndexer(tree="mytree", db_url=db_url)
    indexer._add_objects(
        [
            obj_dict("h1", "secret text", "secret text", private=True),
            obj_dict("h2", "open text", "open text"),
        ]
    )
    assert indexer.count(include_private=True) == 2
    assert indexer.count(include_private=False) == 1
    total, hits = indexer.search("secret", page=1, pagesize=10)
    assert total == 1
    assert [hit["handle"] for hit in hits] == ["h1"]
    total, hits = indexer.search("secret", page=1, pagesize=10, include_private=False)
    assert total == 0
    assert hits == []


def test_object_made_private_is_removed_from_public_index(db_url):
    indexer = SearchIndexer(tree="mytree", db_url=db_url)
    indexer._add_objects([obj_dict("h1", "some text", "some text")])
    assert indexer.count(include_private=False) == 1
    indexer._add_objects([obj_dict("h1", "some text", "some text", private=True)])
    assert indexer.count(include_private=True) == 1
    assert indexer.count(include_private=False) == 0
    total, _ = indexer.search("some", page=1, pagesize=10, include_private=False)
    assert total == 0


def test_reindex_incremental_removes_stale_private_object(db_url):
    indexer = SearchIndexer(tree="mytree", db_url=db_url)
    indexer._add_objects([obj_dict("h1", "some text", "some text")])
    # simulate an index built before private objects were excluded
    # from the public index: object is private, but unchanged since
    db_info = ({"Note": {("h1", 0)}}, {"Note": {"h1"}})
    with (
        patch(
            "gramps_webapi.api.search.indexer.get_object_timestamps",
            return_value=db_info,
        ),
        patch(
            "gramps_webapi.api.search.indexer.obj_strings_from_handle"
        ) as obj_strings,
    ):
        indexer.reindex_incremental(db_handle=None)
    obj_strings.assert_not_called()
    assert indexer.count(include_private=True) == 1
    assert indexer.count(include_private=False) == 0
