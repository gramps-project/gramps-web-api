#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023    David Straub
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

"""Endpoint for creating and downloading media archives."""

import contextlib
import io
import os
import re
import uuid

from flask import abort, current_app, jsonify, redirect, send_file
from flask_jwt_extended import get_jwt_identity

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..media import MediaHandlerS3, get_archive_download_name, get_media_handler
from ..ratelimiter import limiter_per_user
from ..tasks import AsyncResult, export_media, make_task_response, run_task
from ..util import (
    abort_with_message,
    get_db_handle,
    get_tree_from_jwt,
    get_tree_from_jwt_or_fail,
)
from . import ProtectedResource
from gramps_webapi.types import ResponseReturnValue


def get_limit() -> str:
    """Get the rate limit string."""
    return current_app.config["RATE_LIMIT_MEDIA_ARCHIVE"]


class MediaArchiveResource(ProtectedResource):
    """Resource for downloading an archive of media files."""

    @limiter_per_user.limit(get_limit)
    def post(self) -> ResponseReturnValue:
        """Create an archive of media files."""
        tree = get_tree_from_jwt()
        user_id = get_jwt_identity()
        task = run_task(
            export_media,
            tree=tree,
            user_id=user_id,
            view_private=has_permissions({PERM_VIEW_PRIVATE}),
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201


class _DeleteOnCloseFile(io.FileIO):
    """Binary file that is deleted once the WSGI server has sent and closed it.

    `Response.call_on_close` cannot be used for this, since Werkzeug hands file
    responses directly to the server, bypassing the response's close callbacks.
    """

    def close(self) -> None:
        try:
            super().close()
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(self.name)


class MediaArchiveFileResource(ProtectedResource):
    """Resource for downloading an archive of media files."""

    def get(self, filename: str) -> ResponseReturnValue:
        """Download an archive of media files."""
        export_path = current_app.config["EXPORT_DIR"]
        # assert the filename is legit
        regex = re.compile(
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(\.zip)"
        )
        match = regex.match(filename)
        if not match:
            abort_with_message(422, "Invalid filename")

        tree = get_tree_from_jwt_or_fail()
        media_handler = get_media_handler(get_db_handle(), tree=tree)
        if isinstance(media_handler, MediaHandlerS3):
            url = media_handler.get_file_archive_url(tree=tree, file_name=filename)
            if url is None:
                abort(404)
            return redirect(url, 307)

        # absolute, since send_file resolves relative paths against the app root
        file_path = os.path.abspath(os.path.join(export_path, filename))
        # claim the archive by renaming it, so a concurrent request for the
        # same file gets a 404 instead of reading a file that is being deleted
        sending_path = f"{file_path}.{uuid.uuid4()}.sending"
        try:
            os.rename(file_path, sending_path)
        except FileNotFoundError:
            abort(404)
        download_name = get_archive_download_name(os.path.getmtime(sending_path))
        # stream from disk rather than buffering archives of several GB in memory
        file_obj = _DeleteOnCloseFile(sending_path)
        response = send_file(
            file_obj,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
            conditional=False,
        )
        response.content_length = os.fstat(file_obj.fileno()).st_size
        return response
