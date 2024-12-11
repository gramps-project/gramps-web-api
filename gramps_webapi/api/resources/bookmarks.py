#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Bookmark API resource."""

from typing import Dict, List, Optional

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.bookmarks import DbBookmarks

from ...auth.const import PERM_EDIT_OBJ
from ..auth import require_permissions
from ..util import get_db_handle, use_args, abort_with_message
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


def _get_bookmarks_object(db_handle: DbReadBase, namespace: str) -> DbBookmarks:
    """Return bookmarks object for a namespace."""
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
    return result


def get_bookmarks(db_handle: DbReadBase, namespace: str) -> list:
    """Return bookmarks for a namespace."""
    bookmarks = _get_bookmarks_object(db_handle, namespace)
    return bookmarks.get() or []


def create_bookmark(db_handle: DbReadBase, namespace: str, handle: str) -> None:
    """Create a bookmark if it doesn't exist yet."""
    bookmarks = _get_bookmarks_object(db_handle, namespace)
    if handle not in bookmarks.get():
        has_handle_func = {
            "people": db_handle.has_person_handle,
            "families": db_handle.has_family_handle,
            "events": db_handle.has_event_handle,
            "places": db_handle.has_place_handle,
            "sources": db_handle.has_source_handle,
            "citations": db_handle.has_citation_handle,
            "repositories": db_handle.has_repository_handle,
            "media": db_handle.has_media_handle,
            "notes": db_handle.has_note_handle,
        }[namespace]
        if not has_handle_func(handle):
            abort_with_message(404, "Object does not exist")
        bookmarks.append(handle)


def delete_bookmark(db_handle: DbReadBase, namespace: str, handle: str) -> None:
    """Delete a bookmark."""
    bookmarks = _get_bookmarks_object(db_handle, namespace)
    if handle not in bookmarks.get():
        abort_with_message(404, "Bookmark does not exist")
    bookmarks.remove(handle)


class BookmarkResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmark resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    @use_args({}, location="query")
    def get(self, args: Dict, namespace: str) -> Response:
        """Get list of bookmarks by namespace."""
        return self.response(200, get_bookmarks(self.db_handle, namespace))


class BookmarksResource(ProtectedResource, GrampsJSONEncoder):
    """Bookmarks resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    @use_args({}, location="query")
    def get(self, args: Dict) -> Response:
        """Get the list of bookmark types."""
        result = {}
        for bookmark in _BOOKMARK_TYPES:
            result.update({bookmark: get_bookmarks(self.db_handle, bookmark)})
        return self.response(200, result)


class BookmarkEditResource(ProtectedResource):
    """Resource for editing and creating bookmarks."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle(readonly=False)

    def put(self, namespace: str, handle: str) -> Response:
        """Create a bookmark."""
        require_permissions([PERM_EDIT_OBJ])
        if handle not in get_bookmarks(self.db_handle, namespace):
            create_bookmark(self.db_handle, namespace, handle)
        return Response("", 200)

    def delete(self, namespace: str, handle: str) -> Response:
        require_permissions([PERM_EDIT_OBJ])
        """Delete a bookmark."""
        delete_bookmark(self.db_handle, namespace, handle)
        return Response("", 200)
