#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Full-text search utilities."""

from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple

from flask import current_app
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Name, Place
from unidecode import unidecode
from whoosh import index
from whoosh.fields import BOOLEAN, DATETIME, ID, TEXT, Schema
from whoosh.qparser import FieldsPlugin, MultifieldParser, QueryParser
from whoosh.qparser.dateparse import DateParserPlugin
from whoosh.query import Term
from whoosh.searching import Hit
from whoosh.sorting import FieldFacet
from whoosh.writing import AsyncWriter

from ..const import PRIMARY_GRAMPS_OBJECTS
from ..types import FilenameOrPath


def object_to_strings(obj) -> Tuple[str, str]:
    """Create strings from a Gramps object's textual pieces.

    This function returns a tuple of two strings: the first one contains
    the concatenated string of the object and the strings of all
    non-private child objects. The second contains the concatenated
    strings of all private child objects."""
    strings = obj.get_text_data_list()
    private_strings = []
    if hasattr(obj, "gramps_id") and obj.gramps_id not in strings:
        # repositories and notes currently don't have gramps_id on their
        # text_data_list, so it is added here explicitly if missing
        strings.append(obj.gramps_id)
    text_data_child_list = obj.get_text_data_child_list()
    if isinstance(obj, Place) and obj.name not in text_data_child_list:
        # fix necessary for Gramps 5.1
        # (see https://github.com/gramps-project/gramps-webapi/issues/245)
        text_data_child_list.append(obj.name)
    for child_obj in text_data_child_list:
        if hasattr(child_obj, "get_text_data_list"):
            if hasattr(child_obj, "private") and child_obj.private:
                private_strings += child_obj.get_text_data_list()
            else:
                strings += child_obj.get_text_data_list()
            if isinstance(child_obj, Name):
                # for names, need to iterate one level deeper to also find surnames
                for grandchild_obj in child_obj.get_text_data_child_list():
                    if hasattr(grandchild_obj, "get_text_data_list"):
                        if hasattr(child_obj, "private") and child_obj.private:
                            private_strings += grandchild_obj.get_text_data_list()
                        else:
                            strings += grandchild_obj.get_text_data_list()
    return process_strings(strings), process_strings(private_strings)


def process_strings(strings: Sequence[str]) -> str:
    """Process a list of strings to a joined string.

    Removes duplicates and adds transliterated strings for strings containing
    unicode characters.
    """

    def generator():
        all_strings = set()
        for string in strings:
            if string not in all_strings:
                all_strings.add(string)
                yield string
                decoded_string = unidecode(string)
                if decoded_string != string and decoded_string not in all_strings:
                    all_strings.add(decoded_string)
                    yield decoded_string

    return " ".join(generator())


def obj_strings_from_handle(
    db_handle: DbReadBase, class_name: str, handle
) -> Optional[Dict[str, Any]]:
    """Return object strings from a handle and Gramps class name."""
    query_method = db_handle.method("get_%s_from_handle", class_name)
    obj = query_method(handle)
    obj_string, obj_string_private = object_to_strings(obj)
    private = hasattr(obj, "private") and obj.private
    if obj_string:
        return {
            "class_name": class_name,
            "handle": obj.handle,
            "private": private,
            "string": obj_string,
            "string_private": obj_string_private,
            "change": datetime.fromtimestamp(obj.change),
        }
    return None


def iter_obj_strings(
    db_handle: DbReadBase,
) -> Generator[Dict[str, Any], None, None]:
    """Iterate over object strings in the whole database."""
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        iter_method = db_handle.method("iter_%s_handles", class_name)
        for handle in iter_method():
            obj_strings = obj_strings_from_handle(db_handle, class_name, handle)
            if obj_strings:
                yield obj_strings


def get_object_timestamps(db_handle: DbReadBase):
    """Get a dictionary with change timestamps of all objects in the DB."""
    d = {}
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        d[class_name] = set()
        iter_method = db_handle.method("iter_%s_handles", class_name)
        for handle in iter_method():
            query_method = db_handle.method("get_%s_from_handle", class_name)
            obj = query_method(handle)
            d[class_name].add((handle, datetime.fromtimestamp(obj.change)))
    return d


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

    def reindex_full(self, db_handle: DbReadBase):
        """Reindex the whole database."""
        with self.index(overwrite=True).writer() as writer:
            for obj_dict in iter_obj_strings(db_handle):
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

    def _get_update_info(self, db_handle: DbReadBase):
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

    def reindex_incremental(self, db_handle: DbReadBase):
        """Update the index incrementally."""
        update_info = self._get_update_info(db_handle)
        with self.index(overwrite=False).writer() as writer:
            # delete objects
            for class_name, handles in update_info["deleted"].items():
                for handle in handles:
                    self.delete_object(writer, handle)
            # add objects
            for class_name, handles in update_info["new"].items():
                for handle in handles:
                    self.add_or_update_object(writer, handle, db_handle, class_name)
            # update objects
            for class_name, handles in update_info["updated"].items():
                for handle in handles:
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
