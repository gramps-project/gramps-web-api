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

import logging
from typing import Any, Optional, Union

from gramps.plugins.db.dbapi.sqlite import SQLite

_LOG = logging.getLogger(__name__)

# collations whose failure was logged already, so it isn't logged on every
# request; creating them is still tried every time
_FAILED_COLLATIONS_LOGGED: set[str] = set()

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


def has_secondary_columns(db: Any) -> bool:
    """Whether `db` is a DB-API backend whose tables have secondary columns.

    Secondary columns (`private`, `change`, `gramps_id`, ...) are kept in sync
    with `json_data` by Gramps on every commit. A `SharedPostgreSQL` backend
    without a tree ID is refused, since its queries couldn't be scoped to the
    tree.
    """
    if not hasattr(db, "dbapi"):
        return False
    if type(db).__name__ == SHARED_POSTGRES_CLASS_NAME:
        return getattr(db.dbapi, "treeid", None) is not None
    return is_sqlite(db) or type(db).__name__ == SINGLE_TREE_POSTGRES_CLASS_NAME


def resolve_collation(basedb: Any, locale: Any) -> Optional[str]:
    """Ensure the requested locale's collation exists, returning its name.

    Mirrors gramps core's own `DBAPI._collation()` (used internally for
    `get_person_handles(sort_handles=True, locale=...)`): call the backend
    connection's `check_collation()`, which creates the collation if needed
    and (on SQLite) returns the sanitized name it was registered under.
    `SharedPostgreSQL`'s `check_collation()` doesn't return a name, so fall
    back to the locale's raw collation name in that case -- Postgres, unlike
    SQLite, needs no sanitization for `CREATE COLLATION`.

    Returns `None` (no `COLLATE` clause; default ordering) if the backend's
    connection object has no `check_collation` at all.
    """
    if not hasattr(basedb.dbapi, "check_collation"):
        return None
    return basedb.dbapi.check_collation(locale) or locale.get_collation()


# Secondary columns that SQL sorts like the raw sort keys in `sort.py`: numbers
# exactly; text with the locale's collation, which on SQLite is Python's own
# and on Postgres the database's, as for Gramps' own sorting by name.
SQL_SORT_COLUMNS = frozenset({"change", "private", "gramps_id"})
TEXT_SORT_COLUMNS = frozenset({"gramps_id"})


def _where(db: Any, condition: str) -> tuple[str, list[Union[str, int]]]:
    """Return the WHERE clause for a condition, scoped to the tree."""
    params: list[Union[str, int]] = []
    sql = f" WHERE {condition}"
    treeid = getattr(db.dbapi, "treeid", None)
    if treeid is not None:
        sql += " AND treeid = ?"
        params.append(treeid)
    return sql, params


def sql_sorted_handles(
    db: Any,
    table: str,
    order: list[tuple[str, bool]],
    condition: str = "1 = 1",
    locale: Any = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Optional[list[str]]:
    """Return handles of a table sorted by secondary columns.

    `order` is a list of (column, descending), most significant first. Ties are
    broken by handle. `condition` restricts the rows, `limit` and `offset`
    select a page, and `db` must have secondary columns (see
    `has_secondary_columns`). Return None if a text column needs a collation
    the backend doesn't provide or can't create.
    """
    terms = []
    for column, descending in order:
        if column not in SQL_SORT_COLUMNS:
            raise ValueError(f"Cannot sort by {column} in SQL")
        term = column
        if column in TEXT_SORT_COLUMNS:
            if locale is None:
                return None
            try:
                collation = resolve_collation(db, locale)
            except Exception:  # pylint: disable=broad-except
                # e.g. the database server has no OS locale for it; the
                # backend has rolled back, so the caller can sort in Python
                name = locale.get_collation()
                if name not in _FAILED_COLLATIONS_LOGGED:
                    _FAILED_COLLATIONS_LOGGED.add(name)
                    _LOG.warning(
                        "Cannot create the database collation for locale %s, "
                        "sorting in Python instead",
                        name,
                    )
                return None
            if collation is None:
                return None
            term += f' COLLATE "{collation}"'
        terms.append(f"{term} {'DESC' if descending else 'ASC'}")
    # handles are compared like Python strings, which Postgres only does with
    # the C collation
    terms.append("handle ASC" if is_sqlite(db) else 'handle COLLATE "C" ASC')
    where, params = _where(db, condition)
    sql = f"SELECT handle FROM {table}{where} ORDER BY {', '.join(terms)}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    db.dbapi.execute(sql, params)
    return [row[0] for row in db.dbapi.fetchall()]


def sql_count(db: Any, table: str, condition: str = "1 = 1") -> int:
    """Return the number of rows of a table that meet a condition."""
    where, params = _where(db, condition)
    db.dbapi.execute(f"SELECT COUNT(*) FROM {table}{where}", params)
    return db.dbapi.fetchone()[0]
