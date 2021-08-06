#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020        Christopher Horn
# Copyright (C) 2020, 2021  David Straub
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

"""Endpoint for up- and downloading media files."""

import json
from http import HTTPStatus

from flask import Response, abort, current_app, request
from gramps.gen.db import DbTxn
from gramps.gen.errors import HandleError

from ...auth.const import PERM_EDIT_OBJ
from ..auth import require_permissions
from ..file import LocalFileHandler, process_file, upload_file
from ..util import get_db_handle
from . import ProtectedResource
from .util import transaction_to_json, update_object


class MediaFileResource(ProtectedResource):
    """Resource for media files."""

    def get(self, handle) -> Response:
        """Download a file."""
        db_handle = get_db_handle()
        try:
            obj = db_handle.get_media_from_handle(handle)
        except HandleError:
            abort(HTTPStatus.NOT_FOUND)
        base_dir = current_app.config.get("MEDIA_BASE_DIR")
        handler = LocalFileHandler(handle, base_dir)
        return handler.send_file(etag=obj.checksum)

    def put(self, handle) -> Response:
        """Upload a file and update the media object."""
        require_permissions([PERM_EDIT_OBJ])
        db_handle = get_db_handle()
        try:
            obj = db_handle.get_media_from_handle(handle)
        except HandleError:
            abort(HTTPStatus.NOT_FOUND)
        checksum_old = obj.checksum
        for etag in request.if_match:
            if etag != checksum_old:
                abort(412)
        mime = request.content_type
        if not mime:
            abort(HTTPStatus.NOT_ACCEPTABLE)
        checksum, f = process_file(request.stream)
        if checksum == obj.checksum:
            # don't allow PUTting if the file didn't change
            abort(HTTPStatus.CONFLICT)
        base_dir = current_app.config.get("MEDIA_BASE_DIR")
        path = upload_file(base_dir, f, checksum, mime)
        obj.set_checksum(checksum)
        obj.set_path(path)
        obj.set_mime_type(mime)
        db_handle_writable = get_db_handle(readonly=False)
        with DbTxn("Update media object", db_handle_writable) as trans:
            update_object(db_handle_writable, obj, trans)
            try:
                pass  # update_object(db_handle_writable, obj, trans)
            except ValueError:
                abort(400)
            trans_dict = transaction_to_json(trans)
        return Response(
            response=json.dumps(trans_dict), status=200, mimetype="application/json"
        )
