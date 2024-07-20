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

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from flask import current_app
from gramps.gen.db.base import DbReadBase
from whoosh import index
from whoosh.fields import BOOLEAN, DATETIME, ID, TEXT, Schema
from whoosh.qparser import MultifieldParser, QueryParser
from whoosh.qparser.dateparse import DateParserPlugin
from whoosh.query import Term
from whoosh.searching import Hit
from whoosh.sorting import FieldFacet
from whoosh.writing import AsyncWriter

from ...types import FilenameOrPath
from .text import iter_obj_strings, get_object_timestamps, obj_strings_from_handle
from .util import get_total_number_of_objects


class SearchIndexer:
    """Full-text search indexer."""

    # schema for searches of all (public + private) info
    SCHEMA = Schema(
        type=ID(stored=True, sortable=True),
        handle=ID(stored=True, unique=True),
        private=BOOLEAN(stored=True),
        text=TEXT(),
        text_private=TEXT(),
        change=DATETIME(sortable=True, stored=True),
    )

    # schema for searches of public info only
    SCHEMA_PUBLIC = Schema(
        type=ID(stored=True, sortable=True),
        handle=ID(stored=True, unique=True),
        private=BOOLEAN(stored=True),
        text=TEXT(),
        change=DATETIME(sortable=True, stored=True),
    )

    def __init__(self, index_dir=FilenameOrPath):
        """Initialize given an index dir path."""
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        # query parser for all (public + private) content
        self.query_parser_all = MultifieldParser(
            ["text", "text_private"], schema=self.SCHEMA
        )
        # query parser for public content only
        self.query_parser_public = QueryParser("text", schema=self.SCHEMA_PUBLIC)

    def index(self, overwrite=False):
        """Return the index; create if doesn't exist."""
        index_dir = str(self.index_dir)
        if overwrite or not index.exists_in(index_dir):
            return index.create_in(index_dir, self.SCHEMA)
        return index.open_dir(index_dir)

    def _add_obj_strings(self, writer, obj_dict):
        """Add or update an object to the index."""
        try:
            writer.update_document(
                type=obj_dict["class_name"].lower(),
                handle=obj_dict["handle"],
                private=obj_dict["private"],
                text=obj_dict["string"],
                text_private=obj_dict["string_private"],
                change=obj_dict["change"],
            )
        except:
            current_app.logger.error(
                "Failed adding object {}".format(obj_dict["handle"])
            )

    def reindex_full(
        self, db_handle: DbReadBase, progress_cb: Optional[Callable] = None
    ):
        """Reindex the whole database."""
        if progress_cb:
            total = get_total_number_of_objects(db_handle)
        with self.index(overwrite=True).writer() as writer:
            for i, obj_dict in enumerate(iter_obj_strings(db_handle)):
                if progress_cb:
                    progress_cb(current=i, total=total)
                self._add_obj_strings(writer, obj_dict)

    def _get_object_timestamps(self):
        """Get a dictionary with the timestamps of all objects in the index."""
        d = {}
        with self.index().searcher() as searcher:
            for fields in searcher.all_stored_fields():
                class_name = fields["type"]
                if class_name not in d:
                    d[class_name] = set()
                d[class_name].add((fields["handle"], fields["change"]))
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

    def delete_object(self, writer, handle: str):
        """Delete an object from the index."""
        writer.delete_by_term("handle", handle)

    def add_or_update_object(
        self, writer, handle: str, db_handle: DbReadBase, class_name: str
    ):
        """Add an object to the index or update it if it exists."""
        obj_dict = obj_strings_from_handle(db_handle, class_name, handle)
        self._add_obj_strings(writer, obj_dict)

    def get_writer(self, overwrite: bool = False, use_async: bool = False):
        """Get a writer instance.

        If `use_async` is true, use an `AsyncWriter`.
        """
        idx = self.index(overwrite=overwrite)
        if use_async:
            return AsyncWriter(idx, delay=0.1)
        return idx.writer()

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

        with self.index(overwrite=False).writer() as writer:
            # delete objects
            for class_name, handles in update_info["deleted"].items():
                for handle in handles:
                    i = progress(i)
                    self.delete_object(writer, handle)
            # add objects
            for class_name, handles in update_info["new"].items():
                for handle in handles:
                    i = progress(i)
                    self.add_or_update_object(writer, handle, db_handle, class_name)
            # update objects
            for class_name, handles in update_info["updated"].items():
                for handle in handles:
                    i = progress(i)
                    self.add_or_update_object(writer, handle, db_handle, class_name)

    @staticmethod
    def format_hit(hit: Hit) -> Dict[str, Any]:
        """Format a search hit."""
        return {
            "handle": hit["handle"],
            "object_type": hit["type"],
            "rank": hit.rank,
            "score": hit.score,
        }

    def _get_sorting(
        self,
        sort: Optional[List[str]] = None,
    ) -> Optional[List[FieldFacet]]:
        """Get the appropriate field facets for sorting."""
        if not sort:
            return None
        facets = []
        allowed_sorters = {"type", "change"}
        for sorter in sort:
            _field = sorter.lstrip("+-")
            if _field not in allowed_sorters:
                continue
            reverse = sorter.startswith("-")
            facets.append(FieldFacet(_field, reverse=reverse))
        return facets

    def search(
        self,
        query: str,
        page: int,
        pagesize: int,
        include_private: bool = True,
        extend: bool = False,
        sort: Optional[List[str]] = None,
    ):
        """Search the index.

        If `include_private` is true, include also private objects and
        search in private fields.
        """
        query_parser = (
            self.query_parser_all if include_private else self.query_parser_public
        )
        query_parser.add_plugin(DateParserPlugin())
        # if private objects should not be shown, add a mask
        mask = None if include_private else Term("private", True)
        parsed_query = query_parser.parse(query)
        with self.index().searcher() as searcher:
            sortedby = self._get_sorting(sort)
            results = searcher.search_page(
                parsed_query, page, pagesize, mask=mask, sortedby=sortedby
            )
            return results.total, [self.format_hit(hit) for hit in results]
