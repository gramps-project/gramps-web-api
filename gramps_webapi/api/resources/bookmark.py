"""Bookmark API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class BookmarkResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmark resource."""

    gramps_class_name = None

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, bookmark_type: str) -> Response:
        """Get list of bookmarks by type."""
        db = self.db
        if bookmark_type == "person":
            return self.response(db.get_bookmarks())
        if bookmark_type == "family":
            return self.response(db.get_family_bookmarks())
        if bookmark_type == "media":
            return self.response(db.get_media_bookmarks())
        if bookmark_type == "event":
            return self.response(db.get_event_bookmarks())
        if bookmark_type == "citation":
            return self.response(db.get_citation_bookmarks())
        if bookmark_type == "note":
            return self.response(db.get_note_bookmarks())
        if bookmark_type == "place":
            return self.response(db.get_place_bookmarks())
        if bookmark_type == "source":
            return self.response(db.get_source_bookmarks())
        if bookmark_type == "repository":
            return self.response(db.get_repo_bookmarks())
        return abort(404)


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
