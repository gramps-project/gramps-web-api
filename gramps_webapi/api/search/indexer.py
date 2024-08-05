#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024      David Straub
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

from typing import Any, Callable, Dict, List, Optional, Set

import sifts
from flask import current_app
from gramps.gen.db.base import DbReadBase

from .text import iter_obj_strings, obj_strings_from_handle
from ..util import get_total_number_of_objects, get_object_timestamps


class SearchIndexer:
    """Full-text search indexer."""

    def __init__(self, tree: str, db_url: Optional[str] = None):
        """Initialize given an index dir path."""
        if not tree:
            raise ValueError("`tree` is required for the search index")
        if tree.endswith("__p"):
            # we can't allow tree IDs ending in __p since it would
            # interfere with our private-aware index
            raise ValueError("Invalid tree ID")
        self.tree = tree
        # index for all objects
        self.engine = sifts.Collection(db_url=db_url, name=tree)
        # index for view with only non-private objects
        self.engine_public = sifts.Collection(db_url=db_url, name=f"{tree}__p")

    def count(self, include_private: bool):
        """Return the number of items in the collection."""
        if include_private:
            return self.engine.count()
        return self.engine_public.count()

    def _object_id(self, handle: str, class_name: str) -> str:
        """Return the object ID for class name and handle."""
        return f"{class_name.lower()}_{handle}_{self.tree}"

    def _object_id_public(self, handle: str, class_name: str) -> str:
        """Return the object ID for class name and handle."""
        return f"{class_name.lower()}_{handle}_{self.tree}__p"

    def _get_object_data(self, obj_dict: Dict[str, Any], public_only: bool = False):
        """Add or update an object to the index."""
        if public_only:
            obj_id = self._object_id_public(
                handle=obj_dict["handle"], class_name=obj_dict["class_name"]
            )
        else:
            obj_id = self._object_id(
                handle=obj_dict["handle"], class_name=obj_dict["class_name"]
            )

        metadata = {
            "type": obj_dict["class_name"].lower(),
            "handle": obj_dict["handle"],
            "change": obj_dict["change"],
        }
        if public_only:
            contents = obj_dict["string"]
        else:
            contents = " ".join([obj_dict["string"], obj_dict["string_private"]])
        return {
            "contents": contents,
            "id": obj_id,
            "metadata": metadata,
        }

    def _add_objects(self, obj_dicts: List[Dict[str, Any]]):
        """Add or update an object to the index."""
        data = [
            self._get_object_data(obj_dict, public_only=False) for obj_dict in obj_dicts
        ]
        contents = [dat["contents"] for dat in data]
        ids = [dat["id"] for dat in data]
        metadatas = [dat["metadata"] for dat in data]
        self.engine.add(contents=contents, ids=ids, metadatas=metadatas)
        data = [
            self._get_object_data(obj_dict, public_only=True) for obj_dict in obj_dicts
        ]
        contents = [dat["contents"] for dat in data]
        ids = [dat["id"] for dat in data]
        metadatas = [dat["metadata"] for dat in data]
        self.engine_public.add(contents=contents, ids=ids, metadatas=metadatas)

    def reindex_full(
        self, db_handle: DbReadBase, progress_cb: Optional[Callable] = None
    ):
        """Reindex the whole database."""
        if progress_cb:
            total = get_total_number_of_objects(db_handle)

        obj_dicts = []
        for i, obj_dict in enumerate(iter_obj_strings(db_handle)):
            obj_dicts.append(obj_dict)
            if progress_cb:
                progress_cb(current=i, total=total)
        self.engine.delete_all()
        self.engine_public.delete_all()
        self._add_objects(obj_dicts)

    def _get_object_timestamps(self):
        """Get a dictionary with the timestamps of all objects in the index."""
        d = {}
        all_docs = self.engine.get()["results"]
        for doc in all_docs:
            meta = doc["metadata"]
            class_name = meta["type"]
            if class_name not in d:
                d[class_name] = set()
            d[class_name].add((meta["handle"], meta["change"]))
        return d

    def _get_update_info(self, db_handle: DbReadBase) -> Dict[str, Dict[str, Set[str]]]:
        """Get a dictionary with info about changed objects in the db."""
        db_timestamps = get_object_timestamps(db_handle)
        ix_timestamps = self._get_object_timestamps()
        deleted = {}
        updated = {}
        new = {}
        for class_name in db_timestamps:
            db_handles = set(handle for handle, _ in db_timestamps[class_name])
            ix_handles = set(
                handle for handle, _ in ix_timestamps.get(class_name.lower(), set())
            )
            # new: not present in index
            new[class_name] = db_handles - ix_handles
            # deleted: not present in db
            deleted[class_name] = ix_handles - db_handles
            # changed: different (new or modified) in db
            changed_timestamps = db_timestamps[class_name] - ix_timestamps.get(
                class_name.lower(), set()
            )
            changed_handles = set(handle for handle, _ in changed_timestamps)
            # updated: changed and present in the index
            updated[class_name] = changed_handles & ix_handles
        return {"deleted": deleted, "updated": updated, "new": new}

    def delete_object(self, handle: str, class_name: str) -> None:
        """Delete an object from the index."""
        obj_id = self._object_id(handle=handle, class_name=class_name)
        self.engine.delete([obj_id])
        obj_id = self._object_id_public(handle=handle, class_name=class_name)
        self.engine_public.delete([obj_id])

    def add_or_update_object(self, handle: str, db_handle: DbReadBase, class_name: str):
        """Add an object to the index or update it if it exists."""
        obj_dict = obj_strings_from_handle(db_handle, class_name, handle)
        self._add_objects([obj_dict])

    def reindex_incremental(
        self, db_handle: DbReadBase, progress_cb: Optional[Callable] = None
    ):
        """Update the index incrementally."""
        update_info = self._get_update_info(db_handle)
        total = sum(
            len(handles)
            for class_dict in update_info.values()
            for handles in class_dict.values()
        )
        i = 0

        def progress(i):
            if progress_cb:
                progress_cb(current=i, total=total)
            i += 1
            return i

        # delete objects
        for class_name, handles in update_info["deleted"].items():
            obj_ids = [
                self._object_id(handle=handle, class_name=class_name)
                for handle in handles
            ]
            self.engine.delete(obj_ids)
            obj_ids = [
                self._object_id_public(handle=handle, class_name=class_name)
                for handle in handles
            ]
            self.engine_public.delete(obj_ids)
            for _ in handles:
                i = progress(i)

        # add objects
        for class_name, handles in update_info["new"].items():
            obj_dicts = []
            for handle in handles:
                obj_dicts.append(obj_strings_from_handle(db_handle, class_name, handle))
                i = progress(i)
            self._add_objects(obj_dicts)
        # update objects
        for class_name, handles in update_info["updated"].items():
            obj_dicts = []
            for handle in handles:
                obj_dicts.append(obj_strings_from_handle(db_handle, class_name, handle))
                i = progress(i)
            self._add_objects(obj_dicts)

    @staticmethod
    def _format_hit(hit, rank) -> Dict[str, Any]:
        """Format a search hit."""
        return {
            "handle": hit["metadata"]["handle"],
            "object_type": hit["metadata"]["type"],
            "score": hit.get("rank"),
            "rank": rank,
        }

    def search(
        self,
        query: str,
        page: int,
        pagesize: int,
        include_private: bool = True,
        sort: Optional[List[str]] = None,
        object_types: Optional[List[str]] = None,
        change_op: Optional[str] = None,
        change_value: Optional[float] = None,
    ):
        """Search the index.

        If `include_private` is true, include also private objects and
        search in private fields.
        """
        search = self.engine if include_private else self.engine_public
        where = {}
        if object_types:
            where["type"] = {"$in": object_types}
        if change_op and change_value is not None:
            if change_op not in {">", "<", ">=", "<="}:
                raise ValueError("Invalid operator for change condition")
            ops = {">": "$gt", "<": "$lt", ">=": "$gte", "<=": "$lte"}
            where["change"] = {ops[change_op]: change_value}
        where = where or None
        offset = (page - 1) * pagesize
        if not query or query.strip() == "*":
            results = search.get(
                limit=pagesize,
                offset=offset,
                order_by=sort,
                where=where,
            )
        else:
            results = search.query(
                query,
                limit=pagesize,
                offset=offset,
                order_by=sort,
                where=where,
            )
        total = results["total"]
        hits = [
            self._format_hit(hit, rank=offset + i)
            for i, hit in enumerate(results["results"])
        ]
        return total, hits
