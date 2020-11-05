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

    def get(self, namespace: str) -> Response:
        """Get list of bookmarks by namespace."""
        db_handle = self.db_handle
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
        else:
            abort(404)
        return self.response(200, result)


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    def get(self) -> Response:
        """Get the list of bookmark types."""
        return self.response(
            200,
            {
                "namespaces": [
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
            },
        )
