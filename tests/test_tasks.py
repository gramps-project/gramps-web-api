#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for background tasks."""

import logging
from unittest.mock import MagicMock, patch

from celery.result import AsyncResult

from gramps_webapi.api.tasks import (
    _index_objects,
    progress_callback_count,
    search_reindex_incremental,
    search_reindex_incremental_semantic,
    update_search_indices_after_import,
)

TRANS_DICT = [
    {"handle": "aaaa1111", "_class": "Person"},
    {"handle": "bbbb2222", "_class": "Event"},
    {"handle": "cccc3333", "_class": "Family"},
]


def test_index_objects_keeps_going_after_a_failure(caplog):
    """One object that cannot be indexed must not drop the rest of the batch.

    Nothing retries this task, so aborting the loop would leave every object
    after the failing one out of the search index indefinitely.
    """
    indexer = MagicMock()
    indexer.add_or_update_object.side_effect = [
        None,
        IndexError("tuple index out of range"),
        None,
    ]

    with caplog.at_level(logging.WARNING):
        _index_objects(indexer, TRANS_DICT, MagicMock())

    assert indexer.add_or_update_object.call_count == len(TRANS_DICT)
    # the failure is reported rather than swallowed, and names the object
    assert "Event bbbb2222" in caplog.text
    # ... below error level, so it is not reported as a defect
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert caplog.records[0].exc_info is not None


def test_index_objects_follows_the_database_not_the_record_type():
    """Whether an object exists now decides between indexing and removal, so
    stale or reordered records still leave the index matching the database."""
    indexer = MagicMock()
    db_handle = MagicMock()
    existing = {("bbbb2222", "event"), ("cccc3333", "family"), ("dddd4444", "note")}
    db_handle.method.side_effect = lambda fmt, class_name: (
        lambda handle: (handle, class_name.lower()) in existing
    )

    _index_objects(
        indexer,
        [
            # deleted, but a later task already saw it as updated
            {"handle": "aaaa1111", "_class": "Person", "type": "update"},
            # deleted and added back within the same transaction
            {"handle": "bbbb2222", "_class": "Event", "type": "delete"},
            {"handle": "bbbb2222", "_class": "Event", "type": "add"},
            # the entry a merge builds by hand carries no type at all
            {"handle": "cccc3333", "_class": "Family"},
            # a stale delete record for an object that exists again
            {"handle": "dddd4444", "_class": "Note", "type": "delete"},
        ],
        db_handle,
    )

    indexer.delete_object.assert_called_once_with("aaaa1111", "Person")
    # each object once, in order of first appearance
    assert [call.args for call in indexer.add_or_update_object.call_args_list] == [
        ("bbbb2222", db_handle, "Event"),
        ("cccc3333", db_handle, "Family"),
        ("dddd4444", db_handle, "Note"),
    ]


def test_index_objects_indexes_every_object():
    """The normal case must be unaffected."""
    indexer = MagicMock()

    _index_objects(indexer, TRANS_DICT, MagicMock())

    assert [call.args[0] for call in indexer.add_or_update_object.call_args_list] == [
        obj["handle"] for obj in TRANS_DICT
    ]


def _progress_callback(**kwargs):
    """Build a progress callback whose reports are collected in a mock."""
    report = MagicMock()
    with patch("gramps_webapi.api.tasks.progress_reporter", return_value=report):
        callback = progress_callback_count(**kwargs)
    return callback, report


def test_progress_callback_count_throttles_per_object_calls():
    """A producer that calls back once per object with no `prev` (every
    producer feeding this callback except reindex_full: check_database,
    the media/media_importer/delete/restore tasks, and reindex_incremental's
    own per-object loop) must still collapse to about one report per
    integer percentage point, not one database write per object."""
    callback, report = _progress_callback(title="Reindexing")

    total = 10_000
    for current in range(total):
        callback(current=current, total=total)

    assert report.call_count < 150
    assert report.call_count == len(
        {int(100 * current / total) for current in range(total)}
    )


def test_progress_callback_count_throttles_explicit_prev():
    """A producer that passes real `prev` values (reindex_full, batched by
    chunk_size) is throttled from those strides instead."""
    callback, report = _progress_callback()

    callback(current=0, total=1000, prev=None)
    assert report.call_count == 1
    callback(current=5, total=1000, prev=0)  # still inside the 0% bucket
    assert report.call_count == 1
    callback(current=10, total=1000, prev=5)  # crosses into the 1% bucket
    assert report.call_count == 2


def _dispatch_reindex(semantic_indexer):
    """Run `update_search_indices_after_import` as if a task queue were set up."""
    with (
        patch(
            "gramps_webapi.api.tasks.get_current_semantic_search_indexer",
            return_value=semantic_indexer,
        ),
        patch(
            "gramps_webapi.api.tasks.run_task",
            side_effect=lambda task, **kwargs: AsyncResult(f"id-{task.__name__}"),
        ) as run_task,
    ):
        result = update_search_indices_after_import(tree="tree", user_id="user")
    return result, run_task


def test_reindex_after_import_runs_as_separate_tasks():
    """The import result must not wait for the reindex, but point to it."""
    result, run_task = _dispatch_reindex(semantic_indexer=None)

    run_task.assert_called_once_with(
        search_reindex_incremental, tree="tree", user_id="user"
    )
    assert result == [
        {
            "href": "/api/tasks/id-search_reindex_incremental",
            "id": "id-search_reindex_incremental",
        }
    ]


def test_reindex_after_import_includes_semantic_index_when_enabled():
    result, run_task = _dispatch_reindex(semantic_indexer=MagicMock())

    assert [call.args[0] for call in run_task.call_args_list] == [
        search_reindex_incremental,
        search_reindex_incremental_semantic,
    ]
    assert [ref["id"] for ref in result] == [
        "id-search_reindex_incremental",
        "id-search_reindex_incremental_semantic",
    ]


def test_reindex_after_import_without_task_queue_returns_no_tasks():
    """Without a task queue `run_task` reindexes inline and returns its result."""
    with (
        patch(
            "gramps_webapi.api.tasks.get_current_semantic_search_indexer",
            return_value=None,
        ),
        patch("gramps_webapi.api.tasks.run_task", return_value=None) as run_task,
    ):
        assert update_search_indices_after_import(tree="tree", user_id="user") == []
    run_task.assert_called_once()
