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

"""Semantic search index metadata store.

Tracks which embedding model was used to build each tree's semantic index,
so that a model change can be detected and users warned before search results
become silently incorrect.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Optional
from urllib.parse import urlparse


def _is_postgres(db_url: str) -> bool:
    return db_url.startswith("postgresql") or db_url.startswith("postgres")


@contextmanager
def _get_sqlite_conn(db_path: str):
    """Open a SQLite connection."""
    conn = sqlite3.connect(db_path)
    conn.execute("begin")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _get_pg_cursor(db_url: str):
    """Open a PostgreSQL cursor."""
    import psycopg2  # pylint: disable=import-outside-toplevel

    conn = psycopg2.connect(dsn=_pg_dsn(db_url))
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def _sqlite_path(db_url: str) -> str:
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    return db_url


def _pg_dsn(db_url: str) -> str:
    url = urlparse(db_url)
    dbname = url.path[1:]
    user = url.username
    password = url.password
    host = url.hostname
    port = url.port
    return f"dbname={dbname} user={user} password={password} host={host} port={port}"


def ensure_metadata_table(db_url: str) -> None:
    """Create the semantic index metadata table if it doesn't exist."""
    sql = """
        CREATE TABLE IF NOT EXISTS semantic_index_metadata (
            tree TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    if _is_postgres(db_url):
        with _get_pg_cursor(db_url) as cursor:
            cursor.execute(sql)
    else:
        with _get_sqlite_conn(_sqlite_path(db_url)) as conn:
            conn.execute(sql)


def get_stored_model_name(db_url: str, tree: str) -> Optional[str]:
    """Return the model name stored for this tree, or None if not set."""
    ensure_metadata_table(db_url)
    if _is_postgres(db_url):
        with _get_pg_cursor(db_url) as cursor:
            cursor.execute(
                "SELECT model_name FROM semantic_index_metadata WHERE tree = %s",
                (tree,),
            )
            row = cursor.fetchone()
    else:
        with _get_sqlite_conn(_sqlite_path(db_url)) as conn:
            row = conn.execute(
                "SELECT model_name FROM semantic_index_metadata WHERE tree = ?",
                (tree,),
            ).fetchone()
    return row[0] if row else None


def set_stored_model_name(db_url: str, tree: str, model_name: str) -> None:
    """Persist the model name used to build the index for this tree."""
    ensure_metadata_table(db_url)
    if _is_postgres(db_url):
        with _get_pg_cursor(db_url) as cursor:
            cursor.execute(
                """
                INSERT INTO semantic_index_metadata (tree, model_name, indexed_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tree) DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    indexed_at = CURRENT_TIMESTAMP
                """,
                (tree, model_name),
            )
    else:
        with _get_sqlite_conn(_sqlite_path(db_url)) as conn:
            conn.execute(
                """
                INSERT INTO semantic_index_metadata (tree, model_name, indexed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (tree) DO UPDATE SET
                    model_name = excluded.model_name,
                    indexed_at = CURRENT_TIMESTAMP
                """,
                (tree, model_name),
            )
