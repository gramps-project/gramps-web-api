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

"""Tests for sorting handles by raw object data."""

from gramps.gen.db.dbconst import PERSON_KEY, TAG_KEY
from gramps.gen.lib.json_utils import DataDict
from gramps.gen.proxy.proxybase import ProxyDbBase

from gramps_webapi.api.resources.sort import sort_handles_by_raw_data


class FakeDb:
    """Minimal database only providing raw data."""

    def __init__(self, rows, obj_key=PERSON_KEY):
        self.rows = rows
        self.obj_key = obj_key

    def _iter_raw_data(self, obj_key):
        assert obj_key == self.obj_key
        yield from self.rows


class FakeProxyDb(ProxyDbBase):
    """Minimal proxy database without raw data access of its own."""

    def __init__(self, db):
        self.db = self.basedb = db


def person(handle, change, gramps_id, private=False):
    """Return a raw data row for a person."""
    return handle, DataDict(
        {"handle": handle, "change": change, "gramps_id": gramps_id, "private": private}
    )


ROWS = [
    person("a", 1, "I0003"),
    person("b", 2, "I0001", private=True),
    person("c", 1, "I0002"),
]


def test_sort_by_change_ties_by_handle():
    """Test sorting by change, ordering equal values by handle."""
    db = FakeDb(ROWS)
    assert sort_handles_by_raw_data(db, "Person", ["c", "b", "a"], ["change"]) == [
        "a",
        "c",
        "b",
    ]
    assert sort_handles_by_raw_data(db, "Person", ["c", "b", "a"], ["-change"]) == [
        "b",
        "a",
        "c",
    ]


def test_sort_by_multiple_keys():
    """Test the last sort key is the most significant, as in sort_objects."""
    db = FakeDb(ROWS)
    assert sort_handles_by_raw_data(
        db, "Person", ["a", "b", "c"], ["gramps_id", "change"]
    ) == ["c", "a", "b"]


def test_sort_key_requiring_objects():
    """Test None is returned for sort keys not available from raw data."""
    db = FakeDb(ROWS)
    assert sort_handles_by_raw_data(db, "Person", ["a", "b", "c"], ["surname"]) is None
    tag_db = FakeDb([], obj_key=TAG_KEY)
    assert sort_handles_by_raw_data(tag_db, "Tag", [], ["gramps_id"]) is None


def test_result_only_contains_given_handles():
    """Test raw data rows not in the given handles do not change the result."""
    db = FakeDb(ROWS + [person("z", 0, "I0000")])
    assert sort_handles_by_raw_data(db, "Person", ["a", "c"], ["change"]) == ["a", "c"]


def test_handles_without_raw_data_are_omitted():
    """Test handles of objects deleted in the meantime are omitted."""
    db = FakeDb(ROWS)
    assert sort_handles_by_raw_data(
        db, "Person", ["a", "deleted", "b"], ["-change"]
    ) == ["b", "a"]


def test_non_json_raw_data():
    """Test None is returned if the raw data is not JSON data."""
    db = FakeDb([("a", (1, "I0001")), ("b", (2, "I0002"))])
    assert sort_handles_by_raw_data(db, "Person", ["a", "b"], ["change"]) is None


def test_proxy_reads_raw_data_from_base_database():
    """Test raw data of a proxied database is read from its base database."""
    proxy = FakeProxyDb(FakeDb(ROWS))
    assert sort_handles_by_raw_data(proxy, "Person", ["a", "c"], ["-gramps_id"]) == [
        "a",
        "c",
    ]
