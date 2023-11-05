#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David Straub
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

"""Endpoint for text recognition (OCR)."""

from http import HTTPStatus
from typing import Dict

from flask import Response, abort, jsonify
from gramps.gen.errors import HandleError
from webargs import fields, validate

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..tasks import AsyncResult, make_task_response, media_ocr, run_task
from ..util import get_db_handle, get_tree_from_jwt, use_args
from . import ProtectedResource


class MediaOcrResource(ProtectedResource):
    """Resource for media files."""

    @use_args(
        {
            "lang": fields.Str(required=True, validate=validate.Length(min=1)),
            "format": fields.Str(load_default="string"),
        },
        location="query",
    )
    def post(self, args: Dict, handle) -> Response:
        """Execute OCR on a file."""
        db_handle = get_db_handle()
        try:
            db_handle.get_media_from_handle(handle)
        except HandleError:
            abort(HTTPStatus.NOT_FOUND)
        tree = get_tree_from_jwt()
        task = run_task(
            media_ocr,
            tree=tree,
            handle=handle,
            view_private=has_permissions({PERM_VIEW_PRIVATE}),
            lang=args["lang"],
            output_format=args["format"],
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        if isinstance(task, (str, bytes)):
            return task, 201
        return jsonify(task), 201
