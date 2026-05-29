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

from typing import Optional

from sqlalchemy import create_engine, text


def _is_postgres(db_url: str) -> bool:
    return db_url.startswith("postgresql") or db_url.startswith("postgres")


def _get_engine(db_url: str):
    """Return a SQLAlchemy engine for the given URL."""
    return create_engine(db_url)


def ensure_metadata_table(db_url: str) -> None:
    """Create the semantic index metadata table if it doesn't exist."""
    sql = text("""
        CREATE TABLE IF NOT EXISTS semantic_index_metadata (
            tree TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    engine = _get_engine(db_url)
    with engine.begin() as conn:
        conn.execute(sql)


def get_stored_model_name(db_url: str, tree: str) -> Optional[str]:
    """Return the model name stored for this tree, or None if not set."""
    ensure_metadata_table(db_url)
    engine = _get_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT model_name FROM semantic_index_metadata WHERE tree = :tree"),
            {"tree": tree},
        ).fetchone()
    return row[0] if row else None


def set_stored_model_name(db_url: str, tree: str, model_name: str) -> None:
    """Persist the model name used to build the index for this tree."""
    ensure_metadata_table(db_url)
    engine = _get_engine(db_url)
    if _is_postgres(db_url):
        upsert_sql = text("""
            INSERT INTO semantic_index_metadata (tree, model_name, indexed_at)
            VALUES (:tree, :model, CURRENT_TIMESTAMP)
            ON CONFLICT (tree) DO UPDATE SET
                model_name = EXCLUDED.model_name,
                indexed_at = CURRENT_TIMESTAMP
            """)
    else:
        upsert_sql = text("""
            INSERT OR REPLACE INTO semantic_index_metadata (tree, model_name, indexed_at)
            VALUES (:tree, :model, CURRENT_TIMESTAMP)
            """)
    with engine.begin() as conn:
        conn.execute(upsert_sql, {"tree": tree, "model": model_name})
