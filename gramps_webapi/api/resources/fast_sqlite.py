"""SQLite backend subclass with gramps-web-api's own copies of the
empty-tree bulk-import speedups (see util.py's bulk_copy()/run_import()).

gramps-core has an uncommitted, unreleased branch adding
get_secondary_columns()/drop_bulk_import_indexes()/
rebuild_bulk_import_indexes() to DBAPI, and bulk_insert() to sqlite's
Connection -- but we have no control over if or when that lands in an
actual release. This module reimplements the same behavior directly on
a small subclass that gramps-web-api instantiates itself, bypassing
gramps' plugin registry entirely (gramps.gen.db.utils.make_database()
just does `database_class()` with no arguments, so constructing a
subclass directly is equally valid, and doesn't require registering a
new plugin id).

If/when gramps-core ships the real thing, this stays correct either way
(our own methods simply win the MRO on this class), and can be deleted
once the minimum supported gramps-core version has it.
"""

from __future__ import annotations

import os

from gramps.plugins.db.dbapi.sqlite import Connection as _CoreConnection
from gramps.plugins.db.dbapi.sqlite import SQLite as _CoreSQLite


class _FastSQLiteConnection(_CoreConnection):
    """Adds bulk_insert(), built only on Connection's own public
    execute() -- no access to gramps-core's private, name-mangled
    cursor attribute, so this keeps working even if that internal is
    ever renamed.
    """

    def bulk_insert(self, table: str, columns: list[str], rows) -> None:
        """Insert many rows into `table` in as few statements as
        possible, batching multiple rows into one multi-row INSERT.

        `rows` is an iterable of tuples matching `columns`' order.
        Batch size is derived from SQLite's own per-statement bound
        parameter limit (SQLITE_MAX_VARIABLE_NUMBER) rather than a
        fixed constant: that limit has defaulted to 32766 since SQLite
        3.32.0 (2020) but was 999 before that, and can be recompiled to
        something else entirely -- a fixed page size sized for a
        modern build could silently exceed it on an older or
        custom-built one. 900 is a conservative ceiling comfortably
        under even the historical 999 default, regardless of `columns`
        width.
        """
        rows = list(rows)
        if not rows:
            return
        page_size = max(1, 900 // max(1, len(columns)))
        column_list = ", ".join(columns)
        one_row = "(" + ", ".join("?" for _ in columns) + ")"
        for start in range(0, len(rows), page_size):
            chunk = rows[start : start + page_size]
            values_sql = ", ".join(one_row for _ in chunk)
            flat_params = [value for row in chunk for value in row]
            self.execute(
                f"INSERT INTO {table} ({column_list}) VALUES {values_sql}",
                flat_params,
            )


# Same set gramps-core's own (uncommitted) DBAPI._BULK_IMPORT_DROPPABLE_INDEXES
# uses. The index names/columns produced by the currently-released
# _create_schema() are unchanged either way (that hook only extracted the
# same CREATE INDEX statements into a list, it didn't rename anything), so
# dropping/recreating these by name is safe against any installed
# gramps-core version.
_BULK_IMPORT_DROPPABLE_INDEXES = (
    ("person_surname", "person", "surname"),
    ("person_given_name", "person", "given_name"),
    ("source_title", "source", "title"),
    ("citation_page", "citation", "page"),
    ("media_desc", "media", "desc"),
    ("place_title", "place", "title"),
    ("place_enclosed_by", "place", "enclosed_by"),
    ("reference_ref_handle", "reference", "ref_handle"),
)


class FastSQLite(_CoreSQLite):
    """SQLite backend with gramps-web-api's own copies of the empty-tree
    import speedups, so they're available regardless of whether or when
    gramps-core ships its own version. See module docstring.
    """

    def _initialize(self, directory, username, password) -> None:
        path_to_db = (
            ":memory:"
            if directory == ":memory:"
            else os.path.join(directory, "sqlite.db")
        )
        self.dbapi = _FastSQLiteConnection(path_to_db)

    def get_secondary_columns(self, obj) -> dict:
        """See gramps.gen.db.base.DbWriteBase.get_secondary_columns.
        Plain sqlite has no reserved-word column renaming, so (unlike
        the SharedPostgreSQL/PostgreSQL addons' own copies of this
        method) no quoting step is needed here.
        """
        columns = {
            field: getattr(obj, field)
            for field, _schema_type, _max_len in obj.get_secondary_fields()
            # "handle" is one of get_secondary_fields()'s scalar fields,
            # but every caller (bulk INSERT, single-row UPDATE) already
            # addresses the row by handle separately -- including it
            # here would either duplicate the INSERT column list (a
            # real INSERT ... (handle, ..., handle, ...) error) or, for
            # UPDATE, just redundantly set handle to its own value.
            if field != "handle"
        }
        table = obj.__class__.__name__
        if table == "Person":
            given_name, surname = self._get_person_data(obj)
            columns["given_name"] = given_name
            columns["surname"] = surname
        if table == "Place":
            columns["enclosed_by"] = self._get_place_data(obj)
        return columns

    def drop_bulk_import_indexes(self) -> None:
        """See gramps.gen.db.base.DbWriteBase.drop_bulk_import_indexes."""
        self._txn_begin()
        for name, _table, _column in _BULK_IMPORT_DROPPABLE_INDEXES:
            self.dbapi.execute(f"DROP INDEX IF EXISTS {name}")
        self._txn_commit()

    def rebuild_bulk_import_indexes(self) -> None:
        """See gramps.gen.db.base.DbWriteBase.rebuild_bulk_import_indexes."""
        self._txn_begin()
        for name, table, column in _BULK_IMPORT_DROPPABLE_INDEXES:
            self.dbapi.execute(f"CREATE INDEX {name} ON {table}({column})")
        self._txn_commit()
