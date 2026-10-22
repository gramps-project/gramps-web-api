#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2026      David Straub
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

"""Full-text search indexer."""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List

import sqlalchemy as sa
from gramps.gen.db.base import DbReadBase

from ...types import ProgressCallback
from ..util import get_object_timestamps, get_total_number_of_objects
from .query import build_list, build_search, parse_query
from .schema import get_engine, search_doc, search_obj, search_ref
from .text import ObjectRows, iter_object_rows, object_rows_from_handle

_TABLES = ("search_doc", "search_ref", "search_obj")


class SearchIndexer:
    """Full-text search index of one tree.

    All trees share the tables of one database, told apart by a tree column.
    """

    def __init__(self, tree: str, db_url: str):
        """Initialize the indexer."""
        if not tree:
            raise ValueError("`tree` is required for the search index")
        self.tree = tree
        self.engine = get_engine(db_url)
        self.dialect = self.engine.dialect.name

    def _write(self):
        return self.engine.connect().execution_options(write=True)

    def is_built(self) -> bool:
        """Whether the tree's index was fully built.

        Tables of another schema version were dropped when the engine was
        created, so a built index always has the current version.
        """
        with self.engine.connect() as conn:
            built = conn.execute(
                sa.text("SELECT 1 FROM search_meta WHERE tree = :tree"),
                {"tree": self.tree},
            ).scalar()
        return built is not None

    def count(self, include_private: bool) -> int:
        """Return the number of objects in the index visible to the user."""
        statement, params = build_list(
            self.tree, include_private=include_private, count_only=True
        )
        with self.engine.connect() as conn:
            return conn.execute(statement, params).scalar() or 0

    def _delete(self, conn: sa.Connection, handles: List[str]) -> None:
        if not handles:
            return
        for table, column in (
            ("search_doc", "handle"),
            ("search_ref", "from_handle"),
            ("search_obj", "handle"),
        ):
            conn.execute(
                sa.text(
                    f"DELETE FROM {table} WHERE tree = :tree AND {column} IN :handles"
                ).bindparams(sa.bindparam("handles", expanding=True)),
                {"tree": self.tree, "handles": handles},
            )

    def _add_objects(self, rows: List[ObjectRows]) -> None:
        """Add objects to the index, replacing their previous rows."""
        tree = self.tree
        with self._write() as conn, conn.begin():
            self._delete(conn, [obj.handle for obj in rows])
            objs = [
                {
                    "tree": tree,
                    "handle": obj.handle,
                    "obj_type": obj.obj_type,
                    "private": obj.private,
                    "change": obj.change,
                }
                for obj in rows
            ]
            docs = [
                {
                    "tree": tree,
                    "handle": obj.handle,
                    "kind": kind,
                    "variant": variant,
                    "private": private,
                    "content": content,
                }
                for obj in rows
                for kind, variant, private, content in obj.docs
            ]
            refs = [
                {
                    "tree": tree,
                    "from_handle": obj.handle,
                    "to_handle": to_handle,
                    "kind": kind,
                    "private": private,
                }
                for obj in rows
                for to_handle, kind, private in obj.refs
            ]
            for table, values in (
                (search_obj, objs),
                (search_doc, docs),
                (search_ref, refs),
            ):
                if values:
                    conn.execute(sa.insert(table), values)

    def _add_objects_chunked(self, rows: Iterable[ObjectRows], chunk_size: int) -> None:
        """Add objects to the index in chunks of at most `chunk_size`."""
        chunk = []
        for obj in rows:
            chunk.append(obj)
            if len(chunk) >= chunk_size:
                self._add_objects(chunk)
                chunk = []
        if chunk:
            self._add_objects(chunk)

    @staticmethod
    def _chunk_size(total: int) -> int:
        """Return the number of objects to add to the index at once."""
        # indexing is fast, so we use a large chunk size: at least 100
        # (but at most 10%), so that progress is reported regularly
        return max(100, total // 10)

    def _delete_all(self) -> None:
        with self._write() as conn, conn.begin():
            for table in (*_TABLES, "search_meta"):
                conn.execute(
                    sa.text(f"DELETE FROM {table} WHERE tree = :tree"),
                    {"tree": self.tree},
                )

    def _mark_built(self) -> None:
        with self._write() as conn, conn.begin():
            conn.execute(
                sa.text("DELETE FROM search_meta WHERE tree = :tree"),
                {"tree": self.tree},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO search_meta (tree, built_at) VALUES (:tree, :built_at)"
                ),
                {"tree": self.tree, "built_at": time.time()},
            )

    def reindex_full(
        self, db_handle: DbReadBase, progress_cb: ProgressCallback | None = None
    ):
        """Reindex the whole database."""
        total = get_total_number_of_objects(db_handle)
        self._delete_all()

        def all_objects():
            prev: int | None = None
            for i, rows in enumerate(iter_object_rows(db_handle)):
                yield rows
                if progress_cb:
                    progress_cb(current=i, total=total, prev=prev)
                prev = i

        self._add_objects_chunked(all_objects(), self._chunk_size(total))
        self._mark_built()
        self.analyze()
        if progress_cb:
            progress_cb(current=total - 1, total=total)

    def analyze(self) -> None:
        """Let SQLite update its statistics where they are out of date.

        SQLite never collects them by itself, and without them its query
        planner picks slower plans; its documentation asks applications to
        run `PRAGMA optimize`, which only analyzes tables that changed a lot
        since. The mask 0x10002 checks all tables, not only those queried by
        this connection. PostgreSQL's autovacuum does this by itself.
        """
        if self.dialect != "sqlite":
            return
        with self._write() as conn, conn.begin():
            conn.exec_driver_sql("PRAGMA optimize=0x10002")

    def _indexed_timestamps(self) -> Dict[str, set[tuple[str, float]]]:
        """Return the (handle, change) pairs in the index by object type."""
        result: Dict[str, set[tuple[str, float]]] = {}
        with self.engine.connect() as conn:
            for handle, obj_type, change in conn.execute(
                sa.text(
                    "SELECT handle, obj_type, change FROM search_obj WHERE tree = :tree"
                ),
                {"tree": self.tree},
            ):
                result.setdefault(obj_type, set()).add((handle, change))
        return result

    def reindex_incremental(
        self, db_handle: DbReadBase, progress_cb: ProgressCallback | None = None
    ):
        """Update the index incrementally.

        Every row belongs to the object it was made from, so only objects
        that changed since they were indexed need to be indexed again.
        """
        if not self.is_built():
            # never built, or built with an older schema: also the case right
            # after a bulk import into an empty tree, where indexing objects
            # one by one would mean one query per object
            self.reindex_full(db_handle, progress_cb=progress_cb)
            return
        db_timestamps = get_object_timestamps(db_handle)
        ix_timestamps = self._indexed_timestamps()
        deleted: List[str] = []
        changed: list[tuple[str, str]] = []
        for class_name, db_items in db_timestamps.items():
            ix_items = ix_timestamps.get(class_name.lower(), set())
            db_handles = {handle for handle, _ in db_items}
            deleted += [handle for handle, _ in ix_items if handle not in db_handles]
            changed += [
                (class_name, handle) for handle, _ in sorted(db_items - ix_items)
            ]
        total = len(deleted) + len(changed)
        with self._write() as conn, conn.begin():
            self._delete(conn, deleted)
        if progress_cb:
            for i in range(len(deleted)):
                progress_cb(current=i, total=total)

        def changed_objects():
            for i, (class_name, handle) in enumerate(changed, start=len(deleted)):
                rows = object_rows_from_handle(db_handle, class_name, handle)
                if progress_cb:
                    progress_cb(current=i, total=total)
                if rows is not None:
                    yield rows

        self._add_objects_chunked(changed_objects(), self._chunk_size(total))

    def delete_object(self, handle: str, class_name: str) -> None:
        """Delete an object from the index.

        References to it from other objects stay, but lead nowhere: a
        reference only counts if its target is in the index.
        """
        with self._write() as conn, conn.begin():
            self._delete(conn, [handle])

    def add_or_update_object(
        self, handle: str, db_handle: DbReadBase, class_name: str
    ) -> None:
        """Add an object to the index or update it if it exists."""
        rows = object_rows_from_handle(db_handle, class_name, handle)
        if rows is None:
            self.delete_object(handle, class_name)
        else:
            self._add_objects([rows])

    def search(
        self,
        query: str,
        page: int,
        pagesize: int,
        include_private: bool = True,
        sort: List[str] | None = None,
        object_types: List[str] | None = None,
        change_op: str | None = None,
        change_value: float | None = None,
    ):
        """Search the index.

        If `include_private` is true, include also private objects and
        search in private fields.
        """
        offset = (page - 1) * pagesize
        options: Dict[str, Any] = {
            "include_private": include_private,
            "object_types": object_types,
            "change_op": change_op,
            "change_value": change_value,
        }
        if not query or query.strip() == "*":

            def build(**kwargs):
                return build_list(self.tree, **options, **kwargs)

        else:
            clauses = parse_query(query)
            if not clauses:
                return 0, []

            def build(**kwargs):
                return build_search(
                    self.dialect, self.tree, clauses, **options, **kwargs
                )

        statement, params = build(sort=sort, limit=pagesize, offset=offset)
        with self.engine.connect() as conn:
            rows = conn.execute(statement, params).all()
            if rows:
                total = rows[0][3]
            elif offset:
                # past the last page: no row to carry the total
                statement, params = build(count_only=True)
                total = conn.execute(statement, params).scalar() or 0
            else:
                total = 0
        hits = [
            {
                "handle": handle,
                "object_type": obj_type,
                "score": float(score) if score is not None else None,
                "rank": offset + i,
            }
            for i, (handle, obj_type, score, _) in enumerate(rows)
        ]
        return total, hits
