#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2008 Donald N. Allingham
# Copyright (C) 2008      Gary Burton
# Copyright (C) 2008      Robert Cheramy <robert@cheramy.net>
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2023      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Exporters Plugin API resource."""

import mimetypes
import os
import re
import time
from typing import Dict

from flask import Response, abort, current_app, jsonify, send_file
from flask_jwt_extended import get_jwt_identity
from webargs import fields, validate

from ...auth.const import PERM_EDIT_OBJ, PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..export import get_exporters, prepare_options, run_export
from ..tasks import AsyncResult, export_db, make_task_response, run_task
from ..util import (
    abort_with_message,
    get_buffer_for_file,
    get_db_handle,
    get_tree_from_jwt,
    use_args,
)
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from gramps_webapi.types import ResponseReturnValue


class ExportersResource(ProtectedResource, GrampsJSONEncoder):
    """Exporters resource."""

    @use_args({}, location="query")
    def get(self, args: Dict) -> ResponseReturnValue:
        """Get all available exporter attributes."""
        get_db_handle()  # needed to load plugins
        return self.response(200, get_exporters())


class ExporterResource(ProtectedResource, GrampsJSONEncoder):
    """Export resource."""

    @use_args({}, location="query")
    def get(self, args: Dict, extension: str) -> ResponseReturnValue:
        """Get specific report attributes."""
        get_db_handle()  # needed to load plugins
        exporters = get_exporters(extension)
        if not exporters:
            abort(404)
        return self.response(200, exporters[0])


class ExporterFileResource(ProtectedResource, GrampsJSONEncoder):
    """Export file resource."""

    @use_args(
        {
            "compress": fields.Boolean(load_default=True),
            "current_year": fields.Integer(load_default=None),
            "event": fields.Str(load_default=None),
            "gramps_id": fields.Str(load_default=None),
            "handle": fields.Str(load_default=None),
            "include_children": fields.Boolean(load_default=True),
            "include_individuals": fields.Boolean(load_default=True),
            "include_marriages": fields.Boolean(load_default=True),
            "include_media": fields.Boolean(load_default=True),
            "include_places": fields.Boolean(load_default=True),
            "include_witnesses": fields.Boolean(load_default=True),
            "living": fields.Str(
                load_default="IncludeAll",
                validate=validate.OneOf(
                    [
                        "IncludeAll",
                        "FullNameOnly",
                        "LastNameOnly",
                        "ReplaceCompleteName",
                        "ExcludeAll",
                    ]
                ),
            ),
            "locale": fields.Str(load_default=None),
            "note": fields.Str(load_default=None),
            "person": fields.Str(load_default=None),
            "private": fields.Boolean(load_default=False),
            "reference": fields.Boolean(load_default=False),
            "sequence": fields.Str(
                load_default="privacy,living,person,event,note,reference"
            ),
            "translate_headers": fields.Boolean(load_default=True),
            "years_after_death": fields.Integer(load_default=0),
        },
        location="query",
    )
    def post(self, args: Dict, extension: str) -> ResponseReturnValue:
        """Create the export."""
        get_db_handle()  # to load plugins
        exporters = get_exporters(extension)
        if not exporters:
            abort(404)
        tree = get_tree_from_jwt()
        user_id = get_jwt_identity()
        # remove JWT from args
        options = {k: v for k, v in args.items() if k != "jwt"}
        task = run_task(
            export_db,
            tree=tree,
            user_id=user_id,
            extension=extension.lower(),
            options=options,
            view_private=has_permissions({PERM_VIEW_PRIVATE}),
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201

    @use_args(
        {
            "compress": fields.Boolean(load_default=True),
            "current_year": fields.Integer(load_default=None),
            "event": fields.Str(load_default=None),
            "gramps_id": fields.Str(load_default=None),
            "handle": fields.Str(load_default=None),
            "include_children": fields.Boolean(load_default=True),
            "include_individuals": fields.Boolean(load_default=True),
            "include_marriages": fields.Boolean(load_default=True),
            "include_media": fields.Boolean(load_default=True),
            "include_places": fields.Boolean(load_default=True),
            "include_witnesses": fields.Boolean(load_default=True),
            "living": fields.Str(
                load_default="IncludeAll",
                validate=validate.OneOf(
                    [
                        "IncludeAll",
                        "FullNameOnly",
                        "LastNameOnly",
                        "ReplaceCompleteName",
                        "ExcludeAll",
                    ]
                ),
            ),
            "locale": fields.Str(load_default=None),
            "note": fields.Str(load_default=None),
            "person": fields.Str(load_default=None),
            "private": fields.Boolean(load_default=False),
            "reference": fields.Boolean(load_default=False),
            "sequence": fields.Str(
                load_default="privacy,living,person,event,note,reference"
            ),
            "translate_headers": fields.Boolean(load_default=True),
            "years_after_death": fields.Integer(load_default=0),
            "jwt": fields.String(required=False),
        },
        location="query",
    )
    def get(self, args: Dict, extension: str) -> ResponseReturnValue:
        """Get export file."""
        db_handle = get_db_handle()
        exporters = get_exporters(extension)
        if not exporters:
            abort(404)
        options = prepare_options(db_handle, args)
        file_name, file_type = run_export(db_handle, extension, options)
        export_path = current_app.config.get("EXPORT_DIR")
        assert export_path is not None, "EXPORT_DIR not set"  # mypy
        os.makedirs(export_path, exist_ok=True)
        file_path = os.path.join(export_path, file_name)
        buffer = get_buffer_for_file(file_path, delete=True)
        mime_type = "application/octet-stream"
        if file_type != ".pl" and file_type in mimetypes.types_map:
            mime_type = mimetypes.types_map[file_type]
        return send_file(buffer, mimetype=mime_type)


class ExporterFileResultResource(ProtectedResource, GrampsJSONEncoder):
    """Export file result resource."""

    def get(self, extension: str, filename: str) -> ResponseReturnValue:
        """Get the processed file."""
        export_path = current_app.config.get("EXPORT_DIR")
        assert export_path is not None, "EXPORT_DIR not set"  # mypy

        # assert the filename is legit
        regex = re.compile(
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(\.[\w\.]*)"
        )
        match = regex.match(filename)
        if not match:
            abort_with_message(422, "Invalid filename")
        assert match is not None  # mypy

        file_type = match.group(2)
        file_path = os.path.join(export_path, filename)
        if not os.path.isfile(file_path):
            abort(404)
        date_lastmod = time.localtime(os.path.getmtime(file_path))
        buffer = get_buffer_for_file(file_path, delete=True)
        mime_type = "application/octet-stream"
        if file_type != ".pl" and file_type in mimetypes.types_map:
            mime_type = mimetypes.types_map[file_type]
        date_str = time.strftime("%Y%m%d%H%M%S", date_lastmod)
        download_name = f"gramps-web-export-{date_str}{file_type}"
        return send_file(buffer, mimetype=mime_type, download_name=download_name)
