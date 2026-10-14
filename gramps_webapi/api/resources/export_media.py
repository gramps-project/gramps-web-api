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

import os
import re

from flask import abort, current_app, jsonify, redirect, send_file
from flask_jwt_extended import get_jwt_identity

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..media import (
    MediaHandlerS3,
    get_archive_download_name,
    get_archive_name,
    get_local_archive_dir,
    get_media_handler,
    is_archive_expired,
    is_archive_reusable,
)
from ..ratelimiter import limiter_per_user
from ..tasks import AsyncResult, export_media, make_task_response, run_task
from ..util import (
    abort_with_message,
    get_db_handle,
    get_tree_from_jwt_or_fail,
)
from . import ProtectedResource
from gramps_webapi.types import ResponseReturnValue


def get_limit() -> str:
    """Get the rate limit string."""
    return current_app.config["RATE_LIMIT_MEDIA_ARCHIVE"]


class MediaArchiveResource(ProtectedResource):
    """Resource for downloading an archive of media files."""

    def post(self) -> ResponseReturnValue:
        """Create an archive of media files.

        If an archive of the same media exists and can still be downloaded for
        a while, it is returned instead. Only creating a new archive counts
        towards the rate limit.
        """
        # like downloading it, which needs the tree
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        view_private = has_permissions({PERM_VIEW_PRIVATE})
        db_handle = get_db_handle()
        file_name = get_archive_name(db_handle, include_private=view_private)
        media_handler = get_media_handler(db_handle, tree=tree)
        info = media_handler.get_file_archive_info(tree, file_name)
        retention = current_app.config["EXPORT_RETENTION_SECONDS"]
        if info is not None and is_archive_reusable(info[0], retention):
            return (
                jsonify(
                    {
                        "file_name": file_name,
                        "url": f"/api/media/archive/{file_name}",
                        "file_size": info[1],
                    }
                ),
                201,
            )
        with limiter_per_user.limit(get_limit):
            task = run_task(
                export_media,
                tree=tree,
                user_id=user_id,
                view_private=view_private,
                file_name=file_name,
            )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201


class MediaArchiveFileResource(ProtectedResource):
    """Resource for downloading an archive of media files."""

    def get(self, filename: str) -> ResponseReturnValue:
        """Download an archive of media files."""
        # assert the filename is legit
        # named after their contents, or by a UUID if created before that
        regex = re.compile(
            r"([a-f0-9]{64}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
            r"(\.zip)"
        )
        match = regex.fullmatch(filename)
        if not match:
            abort_with_message(422, "Invalid filename")

        tree = get_tree_from_jwt_or_fail()
        retention = current_app.config["EXPORT_RETENTION_SECONDS"]
        media_handler = get_media_handler(get_db_handle(), tree=tree)
        if isinstance(media_handler, MediaHandlerS3):
            url = media_handler.get_file_archive_url(
                tree=tree, file_name=filename, retention=retention
            )
            if url is None:
                abort(404)
            return redirect(url, 307)

        file_path = os.path.join(get_local_archive_dir(tree), filename)
        try:
            created = os.path.getmtime(file_path)
        except FileNotFoundError:
            abort(404)
        if is_archive_expired(created, retention):
            abort(404)
        # streamed from disk, with support for resuming via range requests
        return send_file(
            file_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=get_archive_download_name(created),
        )
