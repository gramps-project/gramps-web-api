#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Douglas Blank
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

"""Regression tests for `ModifiedPrivateProxyDb._iter_handles()`'s tree scoping.

On `SharedPostgreSQL`, every tree's rows live in the same physical tables,
discriminated only by a `treeid` column -- nothing applies that filter
automatically, so this raw-SQL fast path must add it explicitly or it leaks
handles across every tree sharing the instance. Called as an unbound method
against a minimal fake `self` (duck-typed `.basedb.dbapi`) rather than a real
`ModifiedPrivateProxyDb`, which needs a live proxied database to construct.
"""

from gramps.gen.db.dbconst import PERSON_KEY

from gramps_webapi.api.util import ModifiedPrivateProxyDb


class _FakeDbapi:
    def __init__(self, treeid=None):
        if treeid is not None:
            self.treeid = treeid
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return [("h1",), ("h2",)]


class _FakeBasedb:
    def __init__(self, treeid=None):
        self.dbapi = _FakeDbapi(treeid)


class _FakeSelf:
    def __init__(self, treeid=None):
        self.basedb = _FakeBasedb(treeid)


def test_iter_handles_no_treeid_attr_unchanged_query():
    # Single-tree-per-database backends (SQLite, single-user PostgreSQL)
    # have no `.treeid` at all -- behavior must stay exactly as before this
    # fix: no treeid clause, no extra param.
    fake_self = _FakeSelf(treeid=None)
    handles = list(ModifiedPrivateProxyDb._iter_handles(fake_self, PERSON_KEY))
    assert handles == ["h1", "h2"]
    sql, params = fake_self.basedb.dbapi.calls[0]
    assert sql == "SELECT handle FROM person WHERE private=0"
    assert params is None


def test_iter_handles_scopes_to_treeid_when_present():
    fake_self = _FakeSelf(treeid=7)
    handles = list(ModifiedPrivateProxyDb._iter_handles(fake_self, PERSON_KEY))
    assert handles == ["h1", "h2"]
    sql, params = fake_self.basedb.dbapi.calls[0]
    assert sql == "SELECT handle FROM person WHERE private=0 AND treeid=?"
    assert params == [7]
