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

"""Sorting in SQL must give the same order as sorting by raw data."""

from unittest.mock import patch

import pytest
from gramps.gen.db.utils import open_database

from gramps_webapi.api.access import AccessPolicy, RestrictedDb
from gramps_webapi.api.resources import db_backend, sort
from tests import ExampleDbSQLite
from tests.test_privacy_canary import _plant

TREE_NAME = "sort_sql"
CLASSES = ["Person", "Family", "Event", "Place", "Citation", "Note", "Tag"]
SORTS = [
    ["change"],
    ["-change"],
    ["private"],
    ["-private", "change"],
    ["change", "-private"],
    ["gramps_id"],
    ["-gramps_id"],
    ["gramps_id", "-change"],
]


@pytest.fixture(scope="module")
def db():
    """The example tree, where many objects share a change time, with canaries."""
    ExampleDbSQLite(name=TREE_NAME)
    database = open_database(TREE_NAME, force_unlock=True)
    _plant(database)
    yield database
    database.close()


@pytest.mark.parametrize("restricted", [False, True])
@pytest.mark.parametrize("class_name", CLASSES)
@pytest.mark.parametrize("args", SORTS)
def test_same_order(db, restricted, class_name, args):
    database = RestrictedDb(db, AccessPolicy(view_private=False)) if restricted else db
    handles = database.method("get_%s_handles", class_name)()
    in_sql = sort.sort_handles_by_raw_data(database, class_name, handles, args)
    by_raw_data = sort.sort_handles_by_raw_data(
        database, class_name, handles, args, try_sql=False
    )
    if class_name == "Tag" and args not in (["change"], ["-change"]):
        # tags can only be sorted by change
        assert in_sql is None and by_raw_data is None
        return
    assert in_sql is not None
    assert in_sql == by_raw_data


@pytest.mark.parametrize("restricted", [False, True])
@pytest.mark.parametrize("class_name", CLASSES)
@pytest.mark.parametrize("args", [["-change"], ["gramps_id"]])
def test_same_pages(db, restricted, class_name, args):
    if class_name == "Tag" and args == ["gramps_id"]:
        return
    database = RestrictedDb(db, AccessPolicy(view_private=False)) if restricted else db
    handles = database.method("get_%s_handles", class_name)()
    expected = sort.sort_handles_by_raw_data(database, class_name, handles, args)
    for offset, limit in [(0, 20), (20, 20), (len(expected) - 5, 20), (10**6, 20)]:
        page = sort.page_handles_in_sql(
            database, class_name, args, max(offset, 0), limit
        )
        assert page == (
            expected[max(offset, 0) : max(offset, 0) + limit],
            len(expected),
        )


def test_uses_sql(db):
    """The default sort of the frontend doesn't read the objects."""
    restricted = RestrictedDb(db, AccessPolicy(view_private=False))
    handles = restricted.get_person_handles()
    with patch.object(
        RestrictedDb, "_iter_raw_data", side_effect=AssertionError("read objects")
    ):
        sort.sort_handles_by_raw_data(restricted, "Person", handles, ["-change"])


@pytest.mark.parametrize("restricted", [False, True])
def test_collation_failure_falls_back(db, restricted):
    """If the collation can't be created, Gramps IDs are sorted in Python."""
    database = RestrictedDb(db, AccessPolicy(view_private=False)) if restricted else db
    handles = database.get_person_handles()
    expected = sort.sort_handles_by_raw_data(
        database, "Person", handles, ["gramps_id"], try_sql=False
    )
    with patch.object(
        db_backend, "resolve_collation", side_effect=RuntimeError("no locale")
    ):
        assert (
            sort.page_handles_in_sql(database, "Person", ["gramps_id"], 0, 10) is None
        )
        assert (
            sort.sort_handles_by_raw_data(database, "Person", handles, ["gramps_id"])
            == expected
        )
        # sorting by numbers needs no collation
        assert sort.page_handles_in_sql(database, "Person", ["-change"], 0, 10)


def test_shared_postgres_needs_treeid():
    """A shared backend whose tree can't be told apart isn't queried in SQL."""

    class Dbapi:
        pass

    class SharedPostgreSQL:
        def __init__(self, dbapi):
            self.dbapi = dbapi

    dbapi = Dbapi()
    assert not db_backend.has_secondary_columns(SharedPostgreSQL(dbapi))
    dbapi.treeid = 1
    assert db_backend.has_secondary_columns(SharedPostgreSQL(dbapi))


def test_collation_failure_logged_once(db, caplog, monkeypatch):
    """The fallback is logged once per collation, not on every request."""
    monkeypatch.setattr(db_backend, "_FAILED_COLLATIONS_LOGGED", set())
    with patch.object(
        db_backend, "resolve_collation", side_effect=RuntimeError("no locale")
    ) as resolve:
        for _ in range(3):
            assert sort.page_handles_in_sql(db, "Person", ["gramps_id"], 0, 10) is None
    # creating the collation is still tried every time
    assert resolve.call_count == 3
    assert len([r for r in caplog.records if "collation" in r.getMessage()]) == 1
