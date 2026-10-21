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

"""Database engine and tables of the full-text search index.

The index is derived data, so it is rebuilt rather than migrated: when what
is indexed or how it is stored changes, SCHEMA_VERSION is increased. A
database with another version then has its search tables dropped and created
anew, and every tree's index is built again in the background (see
`queue_search_index_build`). Changes that don't affect the content, such as
a new index, are made with `IF NOT EXISTS` and need no new version.
"""

from __future__ import annotations

import logging
import threading

import sqlalchemy as sa
from sqlalchemy import event

from ...util import pin_postgres_driver

# increase after any change of what is indexed or of the tables
SCHEMA_VERSION = 1

_engines: dict[str, sa.Engine] = {}
_lock = threading.Lock()

# for inserts only, which SQLAlchemy batches for Core tables but not for
# text statements; the tables are created by the scripts below
_metadata = sa.MetaData()
search_obj = sa.Table(
    "search_obj",
    _metadata,
    sa.Column("tree", sa.Text),
    sa.Column("handle", sa.Text),
    sa.Column("obj_type", sa.Text),
    sa.Column("private", sa.Boolean),
    sa.Column("change", sa.Float),
)
search_doc = sa.Table(
    "search_doc",
    _metadata,
    sa.Column("tree", sa.Text),
    sa.Column("handle", sa.Text),
    sa.Column("kind", sa.Text),
    sa.Column("variant", sa.Text),
    sa.Column("private", sa.Boolean),
    sa.Column("content", sa.Text),
)
search_ref = sa.Table(
    "search_ref",
    _metadata,
    sa.Column("tree", sa.Text),
    sa.Column("from_handle", sa.Text),
    sa.Column("to_handle", sa.Text),
    sa.Column("kind", sa.Text),
    sa.Column("private", sa.Boolean),
)

_TABLES = """
CREATE TABLE IF NOT EXISTS search_schema (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS search_meta (
    tree TEXT PRIMARY KEY,
    built_at {float} NOT NULL
);
CREATE TABLE IF NOT EXISTS search_obj (
    tree TEXT NOT NULL,
    handle TEXT NOT NULL,
    obj_type TEXT NOT NULL,
    private BOOLEAN NOT NULL,
    change {float} NOT NULL,
    PRIMARY KEY (tree, handle)
);
CREATE INDEX IF NOT EXISTS search_obj_change ON search_obj (tree, change);
CREATE TABLE IF NOT EXISTS search_ref (
    tree TEXT NOT NULL,
    from_handle TEXT NOT NULL,
    to_handle TEXT NOT NULL,
    kind TEXT NOT NULL,
    private BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS search_ref_from ON search_ref (tree, from_handle, kind);
CREATE INDEX IF NOT EXISTS search_ref_to ON search_ref (tree, to_handle, kind);
"""

_SQLITE = """
CREATE TABLE IF NOT EXISTS search_doc (
    id INTEGER PRIMARY KEY,
    tree TEXT NOT NULL,
    handle TEXT NOT NULL,
    kind TEXT NOT NULL,
    variant TEXT NOT NULL,
    private BOOLEAN NOT NULL,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS search_doc_handle ON search_doc (tree, handle);
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    content, content='search_doc', content_rowid='id',
    tokenize='unicode61 remove_diacritics 0'
);
CREATE TRIGGER IF NOT EXISTS search_doc_insert AFTER INSERT ON search_doc BEGIN
    INSERT INTO search_fts (rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS search_doc_delete AFTER DELETE ON search_doc BEGIN
    INSERT INTO search_fts (search_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;
"""

_POSTGRES = """
CREATE TABLE IF NOT EXISTS search_doc (
    id BIGSERIAL PRIMARY KEY,
    tree TEXT NOT NULL,
    handle TEXT NOT NULL,
    kind TEXT NOT NULL,
    variant TEXT NOT NULL,
    private BOOLEAN NOT NULL,
    content TEXT NOT NULL,
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);
CREATE INDEX IF NOT EXISTS search_doc_handle ON search_doc (tree, handle);
"""

# all tables of the index, in the order they can be dropped
_ALL_TABLES = (
    "search_fts",
    "search_doc",
    "search_obj",
    "search_ref",
    "search_meta",
    "search_schema",
)

# columns of the `documents` table of sifts, the former search library
_SIFTS_COLUMNS = {"id", "name", "metadata", "content"}


def _statements(script: str) -> list[str]:
    """Split a script into statements, keeping trigger bodies together."""
    statements, current = [], ""
    for line in script.strip().splitlines():
        current += line + "\n"
        stripped = line.strip()
        if stripped.endswith(";") and (
            not current.lstrip().upper().startswith("CREATE TRIGGER")
            or stripped == "END;"
        ):
            statements.append(current.strip())
            current = ""
    return statements


def _drop_sifts_tables(conn: sa.Connection) -> None:
    """Drop the tables of the former search library, sifts."""
    inspector = sa.inspect(conn)
    if not inspector.has_table("documents"):
        return
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if not _SIFTS_COLUMNS <= columns:
        return
    logging.getLogger(__name__).info("Dropping the search index of sifts")
    if conn.dialect.name == "sqlite" and inspector.has_table("documents_fts"):
        conn.exec_driver_sql("DROP TABLE documents_fts")
    conn.exec_driver_sql("DROP TABLE documents")


def _create_gin_index(conn: sa.Connection) -> None:
    """Index the text of PostgreSQL documents, by tree if possible.

    With the btree_gin extension, the tree is part of the full-text index, so
    a search reads only one tree's entries for a word. Creating the extension
    needs privileges a managed database may not grant; the plain index works,
    only slower in a database with many trees.
    """
    try:
        with conn.begin_nested():
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS btree_gin")
            columns = "tree, tsv"
    except sa.exc.DBAPIError:
        logging.getLogger(__name__).warning(
            "Could not create the btree_gin extension; searches in a"
            " database with many trees will be slower"
        )
        columns = "tsv"
    conn.exec_driver_sql(
        f"CREATE INDEX IF NOT EXISTS search_doc_tsv ON search_doc USING gin ({columns})"
    )


def _drop_outdated_tables(conn: sa.Connection) -> None:
    """Drop the search tables if they were created with another version."""
    inspector = sa.inspect(conn)
    existing = [table for table in _ALL_TABLES if inspector.has_table(table)]
    if not existing:
        return
    version = None
    if "search_schema" in existing:
        version = conn.exec_driver_sql("SELECT version FROM search_schema").scalar()
    if version == SCHEMA_VERSION:
        return
    logging.getLogger(__name__).info(
        "Search index version %s is outdated, rebuilding with version %s",
        version,
        SCHEMA_VERSION,
    )
    for table in existing:
        conn.exec_driver_sql(f"DROP TABLE {table}")


def _create_schema(engine: sa.Engine) -> None:
    sqlite = engine.dialect.name == "sqlite"
    script = (_SQLITE if sqlite else _POSTGRES) + _TABLES.format(
        float="REAL" if sqlite else "DOUBLE PRECISION"
    )
    with engine.connect().execution_options(write=True) as conn:
        with conn.begin():
            if not sqlite:
                # one process at a time; SQLite's BEGIN IMMEDIATE does the same
                conn.exec_driver_sql("SELECT pg_advisory_xact_lock(4146016735)")
            _drop_sifts_tables(conn)
            _drop_outdated_tables(conn)
            for statement in _statements(script):
                conn.exec_driver_sql(statement)
            if not sqlite:
                _create_gin_index(conn)
            conn.exec_driver_sql("DELETE FROM search_schema")
            conn.exec_driver_sql(
                f"INSERT INTO search_schema (version) VALUES ({SCHEMA_VERSION})"
            )


def _sqlite_transactions(engine: sa.Engine) -> None:
    """Begin SQLite write transactions with BEGIN IMMEDIATE.

    With a deferred BEGIN, a write transaction that reads first (FTS5 reads
    its configuration when a statement is prepared) fails with "database is
    locked" right away when another process writes, instead of waiting.
    """

    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin(conn):
        write = conn.get_execution_options().get("write")
        conn.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")


def get_engine(db_url: str) -> sa.Engine:
    """Return the engine of a search index database, creating its tables."""
    with _lock:
        if db_url not in _engines:
            url = pin_postgres_driver(db_url)
            if url.startswith("sqlite"):
                engine = sa.create_engine(url, connect_args={"timeout": 60})
                _sqlite_transactions(engine)
            else:
                engine = sa.create_engine(url, pool_pre_ping=True)
            _create_schema(engine)
            _engines[db_url] = engine
        return _engines[db_url]
