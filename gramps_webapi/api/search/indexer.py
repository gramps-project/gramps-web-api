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

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

import sifts
from gramps.gen.db.base import DbReadBase

from .text import iter_obj_strings, obj_strings_from_handle
from ..util import get_total_number_of_objects, get_object_timestamps


class SearchIndexerBase:
    """Search indexer base class."""

    SUFFIX = ""
    SUFFIX_PUBLIC = "__p"

    def __init__(
        self,
        tree: str,
        db_url: Optional[str] = None,
        embedding_function: Callable | None = None,
        use_fts: bool = True,
        use_semantic_text: bool = False,
    ):
        """Initialize the indexer."""
        if not tree:
            raise ValueError("`tree` is required for the search index")
        if tree.endswith("__p") or tree.endswith("__s"):
            # we can't allow tree IDs ending in __p or __s since it would
            # interfere with our default collection names
            raise ValueError("Invalid tree ID")
        self.tree = tree
        self.use_semantic_text = use_semantic_text
        # index for all objects
        self.index = sifts.Collection(
            db_url=db_url or "",
            name=f"{tree}{self.SUFFIX}",
            embedding_function=embedding_function,
            use_fts=use_fts,
        )
        # index for view with only non-private objects
        self.index_public = sifts.Collection(
            db_url=db_url or "",
            name=f"{tree}{self.SUFFIX_PUBLIC}",
            embedding_function=embedding_function,
            use_fts=use_fts,
        )

    def count(self, include_private: bool):
        """Return the number of items in the collection."""
        if include_private:
            return self.index.count()
        return self.index_public.count()

    def _object_id(self, handle: str, class_name: str) -> str:
        """Return the object ID for class name and handle."""
        return f"{class_name.lower()}_{handle}_{self.tree}{self.SUFFIX}"

    def _object_id_public(self, handle: str, class_name: str) -> str:
        """Return the object ID for class name and handle."""
        return f"{class_name.lower()}_{handle}_{self.tree}{self.SUFFIX_PUBLIC}"

    def _get_object_data(self, obj_dict: Dict[str, Any], public_only: bool = False):
        """Get the object data (content, ID, metadata) from an object dictioanry."""
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
            contents = obj_dict["string_public"]
        else:
            contents = obj_dict["string_all"]
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
        self.index.add(contents=contents, ids=ids, metadatas=metadatas)
        data = [
            self._get_object_data(obj_dict, public_only=True) for obj_dict in obj_dicts
        ]
        contents = [dat["contents"] for dat in data]
        ids = [dat["id"] for dat in data]
        metadatas = [dat["metadata"] for dat in data]
        self.index_public.add(contents=contents, ids=ids, metadatas=metadatas)

    def reindex_full(
        self, db_handle: DbReadBase, progress_cb: Optional[Callable] = None
    ):
        """Reindex the whole database."""
        total = get_total_number_of_objects(db_handle)

        self.index.delete_all()
        self.index_public.delete_all()
        obj_dicts = []
        if self.use_semantic_text:
            # semantic search indexing is slow and uses lots of memory, so we use
            # a small chunk size: at most 100. If we have less than 1000 objects,
            # use 1/10th as chunk size.
            chunk_size = min(100, total // 10 + 1)
        else:
            # full-text search indexing is fast, so we use a large chunk size:
            # at least 100 (but at most 10%).
            chunk_size = max(100, total // 10)
        prev: int | None = None
        for i, obj_dict in enumerate(
            iter_obj_strings(db_handle, semantic=self.use_semantic_text)
        ):
            obj_dicts.append(obj_dict)
            if i % chunk_size == 0 and i != 0:
                self._add_objects(obj_dicts)
                obj_dicts = []
            if progress_cb:
                progress_cb(current=i, total=total, prev=prev)
            prev = i
        self._add_objects(obj_dicts)
        if progress_cb:
            progress_cb(current=total - 1, total=total)

    def _get_object_timestamps(self):
        """Get a dictionary with the timestamps of all objects in the index."""
        d = {}
        all_docs = self.index.get()["results"]
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
        self.index.delete([obj_id])
        obj_id = self._object_id_public(handle=handle, class_name=class_name)
        self.index_public.delete([obj_id])

    def add_or_update_object(
        self, handle: str, db_handle: DbReadBase, class_name: str
    ) -> None:
        """Add an object to the index or update it if it exists."""
        obj_dict = obj_strings_from_handle(
            db_handle, class_name, handle, semantic=self.use_semantic_text
        )
        if obj_dict is not None:
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
            self.index.delete(obj_ids)
            obj_ids = [
                self._object_id_public(handle=handle, class_name=class_name)
                for handle in handles
            ]
            self.index_public.delete(obj_ids)
            for _ in handles:
                i = progress(i)

        # add objects
        for class_name, handles in update_info["new"].items():
            obj_dicts = []
            for handle in handles:
                obj_strings = obj_strings_from_handle(
                    db_handle, class_name, handle, semantic=self.use_semantic_text
                )
                if obj_strings is not None:
                    obj_dicts.append(obj_strings)
                i = progress(i)
            self._add_objects(obj_dicts)
        # update objects
        for class_name, handles in update_info["updated"].items():
            obj_dicts = []
            for handle in handles:
                obj_strings = obj_strings_from_handle(
                    db_handle, class_name, handle, semantic=self.use_semantic_text
                )
                if obj_strings is not None:
                    obj_dicts.append(obj_strings)
                i = progress(i)
            self._add_objects(obj_dicts)

    @staticmethod
    def _format_hit(hit, rank, include_content: bool) -> Dict[str, Any]:
        """Format a search hit."""
        formatted_hit = {
            "handle": hit["metadata"]["handle"],
            "object_type": hit["metadata"]["type"],
            "score": hit.get("rank"),
            "rank": rank,
        }
        if include_content:
            formatted_hit["content"] = hit["content"]
        return formatted_hit

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
        include_content: bool = False,
    ):
        """Search the index.

        If `include_private` is true, include also private objects and
        search in private fields.
        """
        search = self.index if include_private else self.index_public
        where: dict[str, Any] = {}
        if object_types:
            where["type"] = {"$in": object_types}
        if change_op and change_value is not None:
            if change_op not in {">", "<", ">=", "<="}:
                raise ValueError("Invalid operator for change condition")
            ops = {">": "$gt", "<": "$lt", ">=": "$gte", "<=": "$lte"}
            where["change"] = {ops[change_op]: change_value}
        offset = (page - 1) * pagesize
        if not query or query.strip() == "*":
            results = search.get(
                limit=pagesize,
                offset=offset,
                order_by=sort,
                where=where or None,
            )
        else:
            results = search.query(
                query,
                limit=pagesize,
                offset=offset,
                order_by=sort,
                where=where or None,
                vector_search=self.use_semantic_text,
            )
        total = results["total"]
        hits = [
            self._format_hit(hit, rank=offset + i, include_content=include_content)
            for i, hit in enumerate(results["results"])
        ]
        return total, hits


class SearchIndexer(SearchIndexerBase):
    """Full-text search indexer."""

    def __init__(
        self,
        tree: str,
        db_url: Optional[str] = None,
    ):
        """Initialize the indexer."""
        super().__init__(
            tree=tree, db_url=db_url, embedding_function=None, use_fts=True
        )


class SemanticSearchIndexer(SearchIndexerBase):
    """Semantic (vector embedding) search indexer."""

    SUFFIX = "__s"
    SUFFIX_PUBLIC = "__s__p"

    def __init__(
        self,
        tree: str,
        db_url: Optional[str] = None,
        embedding_function: Callable | None = None,
    ):
        """Initialize the indexer."""
        super().__init__(
            tree=tree,
            db_url=db_url,
            embedding_function=embedding_function,
            use_fts=False,
            use_semantic_text=True,
        )
