#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Tests for the `gramps_webapi.dbmanager` module."""

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState

from gramps_webapi.dbmanager import WebDbManager

import pytest


@pytest.fixture
def db():
    name = "Test Web Db Manager"
    dbman = CLIDbManager(DbState())
    dirpath, _name = dbman.create_new_db_cli(name, dbid="sqlite")
    make_database("sharedpostgresql")
    yield name
    dbman.remove_database(name)


def test_lock(db):
    """Test if db is locked while open."""
    dbmgr = WebDbManager(db)
    assert not dbmgr.is_locked()
    dbstate = dbmgr.get_db()
    assert not dbmgr.is_locked()
    dbstate.db.close()
    assert not dbmgr.is_locked()
    dbstate = dbmgr.get_db()
    assert not dbmgr.is_locked()
    dbstate.db.close()
    assert not dbmgr.is_locked()
