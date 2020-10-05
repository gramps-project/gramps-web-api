"""Bookmark API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class BookmarkResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmark resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, bookmark_type: str):
        """Get list of bookmarks by type."""
        db = self.db
        if bookmark_type == "bookmarks":
            result = db.get_bookmarks()
        elif bookmark_type == "citation":
            result = db.get_citation_bookmarks()
        elif bookmark_type == "event":
            result = db.get_event_bookmarks()
        elif bookmark_type == "family":
            result = db.get_family_bookmarks()
        elif bookmark_type == "media":
            result = db.get_media_bookmarks()
        elif bookmark_type == "note":
            result = db.get_note_bookmarks()
        elif bookmark_type == "place":
            result = db.get_place_bookmarks()
        elif bookmark_type == "repo":
            result = db.get_repo_bookmarks()
        elif bookmark_type == "source":
            result = db.get_source_bookmarks()

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    def get(self):
        """Get the list of bookmark types."""
        result = [
            "bookmarks",
            "citation",
            "event",
            "family",
            "media",
            "note",
            "place",
            "repo",
            "source",
        ]

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )
