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

    def get(self, category: str) -> Response:
        """Get list of bookmarks by category."""
        db_handle = self.db_handle
        if category == "person":
            result = db_handle.get_bookmarks()
        elif category == "family":
            result = db_handle.get_family_bookmarks()
        elif category == "media":
            result = db_handle.get_media_bookmarks()
        elif category == "event":
            result = db_handle.get_event_bookmarks()
        elif category == "citation":
            result = db_handle.get_citation_bookmarks()
        elif category == "note":
            result = db_handle.get_note_bookmarks()
        elif category == "place":
            result = db_handle.get_place_bookmarks()
        elif category == "source":
            result = db_handle.get_source_bookmarks()
        elif category == "repository":
            result = db_handle.get_repo_bookmarks()
        else:
            return abort(404)
        return self.response(result)


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    def get(self) -> Response:
        """Get the list of bookmark types."""
        return self.response(
            {
                "categories": [
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
            }
        )
