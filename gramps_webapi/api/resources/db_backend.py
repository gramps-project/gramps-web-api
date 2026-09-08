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

"""Database backend class names, shared by every module that needs to tell
DBAPI-based backends apart for raw-SQL purposes (`object_query.py`'s
`_resolve_dialect`/`_resolve_treeid`, `util.py`'s `preload_event_backlinks`).

Checked by class *name*, not `isinstance`: Gramps' plugin loader imports
database backend plugins (including core ones) as freestanding modules under
a bare name (`sqlite`, not `gramps.plugins.db.dbapi.sqlite`) rather than via
a normal package import, so a real request's `db_handle`/`basedb` is a
*different* class object than this module's own `from
gramps.plugins.db.dbapi.sqlite import SQLite` -- same name, same behavior,
different identity. `isinstance(basedb, SQLite)` silently returns `False`
for it every time; see `object_query.py`'s `_resolve_dialect` docstring for
the concrete failure this caused. `isinstance` is kept first for `SQLite`
since it's the correct, more specific check when it *does* match (e.g. a
`SQLite()` constructed directly in-process, as tests do).

This module only centralizes the *names* -- each caller keeps its own
failure policy for "unrecognized backend" (silent fallback in
`preload_event_backlinks`, an HTTP 501 in `object_query.py`), since what's
safe to do differs by call site.
"""

from typing import Any

from gramps.plugins.db.dbapi.sqlite import SQLite

SQLITE_CLASS_NAME = "SQLite"
SINGLE_TREE_POSTGRES_CLASS_NAME = "PostgreSQL"
SHARED_POSTGRES_CLASS_NAME = "SharedPostgreSQL"

# Single-tree-per-database backends: no `treeid` column/concept at all, as
# opposed to `SharedPostgreSQL`, which stores every tree in the same tables.
SINGLE_TREE_DBAPI_CLASS_NAMES = frozenset(
    {SQLITE_CLASS_NAME, SINGLE_TREE_POSTGRES_CLASS_NAME}
)


def is_sqlite(basedb: Any) -> bool:
    """Whether `basedb` (or its `.dbapi`) is a core SQLite backend."""
    return isinstance(basedb, SQLite) or type(basedb).__name__ == SQLITE_CLASS_NAME
