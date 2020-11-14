"""Bookmark API resource."""

from typing import List, Optional

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder

_BOOKMARK_TYPES = [
    "citations",
    "events",
    "families",
    "media",
    "notes",
    "people",
    "places",
    "repositories",
    "sources",
]


def get_bookmarks(db_handle: DbReadBase, namespace: str) -> Optional[List]:
    """Return bookmarks for a namespace."""
    result = None
    if namespace == "people":
        result = db_handle.get_bookmarks()
    elif namespace == "families":
        result = db_handle.get_family_bookmarks()
    elif namespace == "media":
        result = db_handle.get_media_bookmarks()
    elif namespace == "events":
        result = db_handle.get_event_bookmarks()
    elif namespace == "citations":
        result = db_handle.get_citation_bookmarks()
    elif namespace == "notes":
        result = db_handle.get_note_bookmarks()
    elif namespace == "places":
        result = db_handle.get_place_bookmarks()
    elif namespace == "sources":
        result = db_handle.get_source_bookmarks()
    elif namespace == "repositories":
        result = db_handle.get_repo_bookmarks()
    if result is None:
        abort(404)
    return result.get()


class BookmarkResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmark resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, namespace: str) -> Response:
        """Get list of bookmarks by namespace."""
        return self.response(200, get_bookmarks(self.db_handle, namespace))


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self) -> Response:
        """Get the list of bookmark types."""
        result = {}
        for bookmark in _BOOKMARK_TYPES:
            result.update({bookmark: get_bookmarks(self.db_handle, bookmark)})
        return self.response(200, result)
