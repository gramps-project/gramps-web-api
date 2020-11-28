"""Full-text search utilities."""

from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Generator, Tuple

from gramps.gen.db.base import DbReadBase
from whoosh import index
from whoosh.fields import ID, TEXT, Schema
from whoosh.qparser import QueryParser
from whoosh.searching import Hit

from ..const import PRIMARY_GRAMPS_OBJECTS
from ..types import FilenameOrPath, Handle


def object_to_string(obj):
    """Create a string from a Gramps object's textual pieces."""
    strings = obj.get_text_data_list()
    for child_obj in obj.get_text_data_child_list():
        if hasattr(child_obj, "get_text_data_list"):
            strings += child_obj.get_text_data_list()
    # discard duplicate strings but keep order
    strings = OrderedDict.fromkeys(strings)
    return " ".join(strings)


def iter_obj_strings(
    db_handle: DbReadBase,
) -> Generator[Tuple[str, Handle, str], None, None]:
    """Iterate over object strings in the whole database."""
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        query_method = db_handle.method("get_%s_from_handle", class_name)
        iter_method = db_handle.method("iter_%s_handles", class_name)
        for handle in iter_method():
            obj = query_method(handle)
            obj_string = object_to_string(obj)
            if obj_string:
                yield class_name, obj.handle, obj_string


class SearchIndexer:
    """Full-text search indexer."""

    SCHEMA = Schema(
        class_name=ID(stored=True),
        handle=ID(stored=True, unique=True),
        text=TEXT(stored=True),
    )

    def __init__(self, index_dir=FilenameOrPath):
        """Initialize given an index dir path."""
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(exist_ok=True)
        self.query_parser = QueryParser("text", schema=self.SCHEMA)

    def index(self, overwrite=False):
        """Return the index; create if doesn't exist."""
        index_dir = str(self.index_dir)
        if overwrite or not index.exists_in(index_dir):
            return index.create_in(index_dir, self.SCHEMA)
        return index.open_dir(index_dir)

    def reindex_full(self, db_handle: DbReadBase):
        """Reindex the whole database."""
        with self.index(overwrite=True).writer() as writer:
            for class_name, handle, obj_string in iter_obj_strings(db_handle):
                writer.add_document(
                    class_name=class_name.lower(), handle=handle, text=obj_string
                )

    @staticmethod
    def format_hit(hit: Hit) -> Dict[str, Any]:
        """Format a search hit."""
        return {
            "handle": hit["handle"],
            "object_type": hit["class_name"],
            "rank": hit.rank,
            "score": hit.score,
        }

    def search(self, query: str, extend: bool = False):
        """Search the index."""
        parsed_query = self.query_parser.parse(query)
        with self.index().searcher() as searcher:
            results = searcher.search(parsed_query)
            return [self.format_hit(hit) for hit in results]
