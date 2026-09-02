#
# Gramps Web API - A RESTful API for the Gramps genealogical database.
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

"""Gramps Web API's adapter onto `gramps_sql_extensions.RelationshipGraph`.

The actual fast-relationship-lookup implementation (the SQL-derived
ancestry graph, the breadth-first search, privacy filtering, the
pedigree-collapse tie-break, sibling/spouse resolution) lives in the
standalone `gramps_sql_extensions` package now, not here -- see that
package's `relationship.py` for the full design notes. This module is
just the glue specific to gramps-web-api: turning a (possibly
privacy-proxied) `db_handle` into the one thing `RelationshipGraph`
actually needs, an `execute(sql, params) -> rows` callable, and resolving
which backend dialect and (for Postgres) integer treeid apply.

DEPENDENCY NOTE: `gramps-sql-extensions` is not published yet, so it is
deliberately NOT listed in pyproject.toml's `dependencies` (that would
break `pip install .` and CI, since nothing could resolve it). For now
it's installed locally as an editable sibling checkout
(`pip install -e ../gramps-sql-extensions`). Move it into pyproject.toml's
real dependency list once it has a published release.
"""

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps_sql_extensions import RelationshipGraph


def get_relationship_graph(db_handle, dbid: str, locale=glocale) -> RelationshipGraph:
    """Build a RelationshipGraph for the given (possibly privacy-proxied)
    db handle. Unwraps a `ProxyDbBase` (e.g. `ModifiedPrivateProxyDb`) to
    reach the underlying `.dbapi` -- the fast path does its own live SQL
    privacy filtering (see `RelationshipGraph.ancestor_map`'s `restricted`
    flag) rather than going through the proxy's object-level filtering.

    Resolves the SharedPostgreSQL-internal integer `treeid` (the
    `family.treeid` / `person.treeid` column value) via the addon's own
    `Connection.treeid` property, rather than deriving it independently --
    this is NOT the same string as gramps-web-api's own tree id (a UUID
    from `get_tree_from_jwt_or_fail()`); the two identifier spaces don't
    correspond in any derivable way, only the addon's own `trees` table
    maps one to the other. SQLite has no such column at all (one tree per
    file), hence `None` there."""
    raw = getattr(db_handle, "db", db_handle)

    def execute(sql: str, params: list) -> list[tuple]:
        raw.dbapi.execute(sql, params)
        try:
            return raw.dbapi.fetchall()
        except Exception:
            return []  # DDL statements (CREATE/DROP/CREATE INDEX) have no rows

    treeid = raw.dbapi.treeid if dbid in ("postgresql", "sharedpostgresql") else None
    return RelationshipGraph(execute, dbid, treeid, locale=locale)
