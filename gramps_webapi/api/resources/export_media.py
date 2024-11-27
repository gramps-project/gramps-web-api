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
import time

from flask import Response, abort, current_app, jsonify, send_file
from flask_jwt_extended import get_jwt_identity

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..ratelimiter import limiter_per_user
from ..tasks import AsyncResult, export_media, make_task_response, run_task
from ..util import abort_with_message, get_buffer_for_file, get_tree_from_jwt
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


class MediaArchiveFileResource(ProtectedResource):
    """Resource for downloading an archive of media files."""

    def get(self, filename: str) -> Response:
        """Download an archive of media files."""
        export_path = current_app.config["EXPORT_DIR"]
        # assert the filename is legit
        regex = re.compile(
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(\.zip)"
        )
        match = regex.match(filename)
        if not match:
            abort_with_message(422, "Invalid filename")

        file_path = os.path.join(export_path, filename)
        if not os.path.isfile(file_path):
            abort(404)
        date_lastmod = time.localtime(os.path.getmtime(file_path))
        buffer = get_buffer_for_file(file_path, delete=True)
        date_str = time.strftime("%Y%m%d%H%M%S", date_lastmod)
        download_name = f"gramps-web-media-export-{date_str}.zip"
        return send_file(
            buffer, mimetype="application/zip", download_name=download_name
        )
