#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Media API resource."""

import uuid
from http import HTTPStatus
from typing import Dict

from flask import Response, abort, current_app, request
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.lib import Media
from gramps.gen.utils.grampslocale import GrampsLocale

from ...auth.const import PERM_ADD_OBJ
from ..auth import require_permissions
from ..file import process_file
from ..media import MediaHandler
from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    add_object,
    get_extended_attributes,
    get_media_profile_for_object,
    transaction_to_json,
)


class MediaObjectResourceHelper(GrampsObjectResourceHelper):
    """Media resource helper."""

    gramps_class_name = "Media"

    def object_extend(
        self, obj: Media, args: Dict, locale: GrampsLocale = glocale
    ) -> Media:
        """Extend media attributes as needed."""
        if "profile" in args:
            obj.profile = get_media_profile_for_object(
                self.db_handle, obj, args["profile"], locale=locale
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
        return obj


class MediaObjectResource(GrampsObjectProtectedResource, MediaObjectResourceHelper):
    """Media object resource."""


class MediaObjectsResource(GrampsObjectsProtectedResource, MediaObjectResourceHelper):
    """Media objects resource."""

    def post(self) -> Response:
        """Post a new object."""
        require_permissions([PERM_ADD_OBJ])
        mime = request.content_type
        if not mime:
            abort(HTTPStatus.NOT_ACCEPTABLE)
        checksum, f = process_file(request.stream)
        base_dir = current_app.config.get("MEDIA_BASE_DIR", "")
        media_handler = MediaHandler(base_dir)
        media_handler.upload_file(f, checksum, mime)
        path = media_handler.get_default_filename(checksum, mime)
        db_handle = self.db_handle_writable
        obj = Media()
        obj.set_checksum(checksum)
        obj.set_path(path)
        obj.set_mime_type(mime)
        with DbTxn("Add object", db_handle) as trans:
            try:
                add_object(db_handle, obj, trans)
            except ValueError:
                abort(400)
            trans_dict = transaction_to_json(trans)
        return self.response(201, trans_dict, total_items=len(trans_dict))
