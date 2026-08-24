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

"""Endpoint for importing a media archive."""

import os
import shutil
import uuid
import zipfile

from flask import Response, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity

from ...auth.const import PERM_IMPORT_FILE
from ..auth import require_permissions
from ..tasks import AsyncResult, import_media_archive, make_task_response, run_task
from ..util import abort_with_message, get_tree_from_jwt
from . import ProtectedResource
from gramps_webapi.types import ResponseReturnValue

# free disk space never to be consumed by an uploaded archive, so that a large
# upload cannot fill up the file system holding EXPORT_DIR
DISK_SPACE_RESERVE = 64 * 1024 * 1024  # 64 MB


def get_free_upload_bytes(export_path: str) -> int:
    """Return the free disk space usable by an uploaded archive."""
    free = shutil.disk_usage(export_path).free
    return max(free - DISK_SPACE_RESERVE, 0)


def get_max_upload_bytes(free_bytes: int) -> int:
    """Return the maximum number of bytes an uploaded archive may have."""
    configured = current_app.config.get("MAX_MEDIA_ARCHIVE_UPLOAD_BYTES")
    if configured is not None:
        return min(free_bytes, configured)
    return free_bytes


def write_upload_to_file(file_path: str, max_bytes: int) -> None:
    """Stream the request body to a file, aborting if it exceeds `max_bytes`."""
    request_stream = request.stream
    size = 0
    with open(file_path, "w+b") as ftmp:
        chunk_size = 4 * 1024  # reading in 4 KB chunks
        while True:
            chunk = request_stream.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                abort_with_message(413, "Uploaded archive is too large")
            ftmp.write(chunk)


class MediaUploadZipResource(ProtectedResource):
    """Resource for uploading an archive of media files."""

    def post(self) -> ResponseReturnValue:
        """Upload an archive of media files."""
        require_permissions([PERM_IMPORT_FILE])

        # we use EXPORT_DIR as location to store the temporary file
        export_path = current_app.config["EXPORT_DIR"]
        os.makedirs(export_path, exist_ok=True)

        free_bytes = get_free_upload_bytes(export_path)
        if not free_bytes:
            abort_with_message(507, "Not enough free space on disk")

        max_bytes = get_max_upload_bytes(free_bytes)
        if request.content_length and request.content_length > max_bytes:
            abort_with_message(413, "Uploaded archive is too large")

        file_name = f"{uuid.uuid4()}.zip"
        file_path = os.path.join(export_path, file_name)

        try:
            write_upload_to_file(file_path, max_bytes=max_bytes)

            if os.path.getsize(file_path) == 0:
                abort_with_message(400, "Imported file is empty")

            try:
                with zipfile.ZipFile(file_path) as zip_file:
                    zip_file.namelist()
            except zipfile.BadZipFile:
                abort_with_message(400, "The uploaded file is not a valid ZIP file.")
        except Exception:
            # don't leave the partial or rejected upload behind
            if os.path.isfile(file_path):
                os.remove(file_path)
            raise

        tree = get_tree_from_jwt()
        user_id = get_jwt_identity()
        task = run_task(
            import_media_archive,
            tree=tree,
            user_id=user_id,
            file_name=file_path,
            delete=True,
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201
