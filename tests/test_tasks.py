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
from unittest.mock import MagicMock

from gramps_webapi.api.tasks import _index_objects

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

    with caplog.at_level(logging.ERROR):
        _index_objects(indexer, TRANS_DICT, MagicMock())

    assert indexer.add_or_update_object.call_count == len(TRANS_DICT)
    # the failure is reported rather than swallowed, and names the object
    assert "Event bbbb2222" in caplog.text


def test_index_objects_indexes_every_object():
    """The normal case must be unaffected."""
    indexer = MagicMock()

    _index_objects(indexer, TRANS_DICT, MagicMock())

    assert [call.args[0] for call in indexer.add_or_update_object.call_args_list] == [
        obj["handle"] for obj in TRANS_DICT
    ]
