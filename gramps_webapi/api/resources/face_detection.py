#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2022      David Straub
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

"""Face detection API resource."""


from http import HTTPStatus

from flask import Response, abort
from gramps.gen.errors import HandleError

from ..cache import request_cache_decorator
from ..media import get_media_handler
from ..util import get_db_handle, get_tree_from_jwt
from . import ProtectedResource


class MediaFaceDetectionResource(ProtectedResource):
    """Resource for face detection in media files."""

    @request_cache_decorator
    def get(self, handle) -> Response:
        """Get detected face regions."""
        db_handle = get_db_handle()
        try:
            obj = db_handle.get_media_from_handle(handle)
        except HandleError:
            abort(HTTPStatus.NOT_FOUND)
        tree = get_tree_from_jwt()
        handler = get_media_handler(db_handle, tree).get_file_handler(
            handle, db_handle=db_handle
        )
        return handler.get_face_regions(etag=obj.checksum)
