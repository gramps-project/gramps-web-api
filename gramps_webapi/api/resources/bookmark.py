"""Bookmark API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class BookmarkResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmark resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, bookmark_type: str) -> Response:
        """Get list of bookmarks by type."""
        db_handle = self.db_handle
        if bookmark_type == "person":
            result = db_handle.get_bookmarks()
        elif bookmark_type == "family":
            result = db_handle.get_family_bookmarks()
        elif bookmark_type == "media":
            result = db_handle.get_media_bookmarks()
        elif bookmark_type == "event":
            result = db_handle.get_event_bookmarks()
        elif bookmark_type == "citation":
            result = db_handle.get_citation_bookmarks()
        elif bookmark_type == "note":
            result = db_handle.get_note_bookmarks()
        elif bookmark_type == "place":
            result = db_handle.get_place_bookmarks()
        elif bookmark_type == "source":
            result = db_handle.get_source_bookmarks()
        elif bookmark_type == "repository":
            result = db_handle.get_repo_bookmarks()
        else:
            return abort(404)
        return self.response(result)


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    def get(self) -> Response:
        """Get the list of bookmark types."""
        return self.response(
            [
                "citation",
                "event",
                "family",
                "media",
                "note",
                "person",
                "place",
                "repository",
                "source",
            ]
        )
