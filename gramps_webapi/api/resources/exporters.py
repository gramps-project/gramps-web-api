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
from marshmallow import Schema
from webargs import fields, validate

from ...auth.const import PERM_EDIT_OBJ, PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..blueprint import api_blueprint
from ..export import get_exporters, prepare_options, run_export
from ..tasks import AsyncResult, export_db, make_task_response, run_task
from ..util import (
    abort_with_message,
    get_buffer_for_file,
    get_db_handle,
    get_tree_from_jwt,
)
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .schemas import ExporterSchema
from gramps_webapi.types import ResponseReturnValue


class ExportersResource(ProtectedResource, GrampsJSONEncoder):
    """Exporters resource."""

    @api_blueprint.response(200, ExporterSchema(many=True))
    @api_blueprint.arguments(Schema(), location="query")
    def get(self, args) -> ResponseReturnValue:
        """Get all available exporter attributes."""
        get_db_handle()  # needed to load plugins
        return self.response(200, get_exporters())


class ExporterResource(ProtectedResource, GrampsJSONEncoder):
    """Export resource."""

    @api_blueprint.response(200, ExporterSchema())
    @api_blueprint.arguments(Schema(), location="query")
    def get(self, args, extension: str) -> ResponseReturnValue:
        """Get specific report attributes."""
        get_db_handle()  # needed to load plugins
        exporters = get_exporters(extension)
        if not exporters:
            abort(404)
        return self.response(200, exporters[0])


class ExporterFileQueryArgs(Schema):
    """Query arguments for GET/POST /exporters/<extension>/file."""

    compress = fields.Boolean(
        load_default=True,
        metadata={
            "description": "If true (default), use compression if supported by the exporter."
        },
    )
    current_year = fields.Integer(
        load_default=None,
        metadata={
            "description": "Year to treat as 'current' when evaluating whether someone may still be alive. Defaults to the actual current year."
        },
    )
    event = fields.Str(
        load_default=None,
        metadata={
            "description": "Name of a custom event filter to apply during export."
        },
    )
    gramps_id = fields.Str(
        load_default=None,
        metadata={"description": "Gramps ID of the person for built-in person filter."},
    )
    handle = fields.Str(
        load_default=None,
        metadata={
            "description": "Handle of the person for built-in person filter. Ignored if gramps_id is provided."
        },
    )
    include_children = fields.Boolean(
        load_default=True,
        metadata={"description": "If true (default), include children in CSV export."},
    )
    include_individuals = fields.Boolean(
        load_default=True,
        metadata={
            "description": "If true (default), include individuals in CSV export."
        },
    )
    include_marriages = fields.Boolean(
        load_default=True,
        metadata={"description": "If true (default), include marriages in CSV export."},
    )
    include_media = fields.Boolean(
        load_default=True,
        metadata={"description": "If true (default), include media in GED2 export."},
    )
    include_places = fields.Boolean(
        load_default=True,
        metadata={"description": "If true (default), include places in CSV export."},
    )
    include_witnesses = fields.Boolean(
        load_default=True,
        metadata={
            "description": "If true (default), include witnesses in GED2 export."
        },
    )
    living = fields.Str(
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
        metadata={
            "description": "Built-in proxy controlling how living people are handled. Values: IncludeAll, FullNameOnly, LastNameOnly, ReplaceCompleteName, ExcludeAll."
        },
    )
    locale = fields.Str(
        load_default=None,
        metadata={
            "description": "Language code for translation of living-person name filters."
        },
    )
    note = fields.Str(
        load_default=None,
        metadata={
            "description": "Name of a custom note filter to apply during export."
        },
    )
    person = fields.Str(
        load_default=None,
        metadata={
            "description": "Name of a built-in or custom person filter. Built-in values: Descendants, DescendantFamilies, Ancestors, CommonAncestor."
        },
    )
    private = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, exclude records marked as private from the export."
        },
    )
    reference = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include records not directly linked to the selected person."
        },
    )
    sequence = fields.Str(
        load_default="privacy,living,person,event,note,reference",
        metadata={
            "description": "Comma-delimited order in which filters are applied (default: privacy,living,person,event,note,reference)."
        },
    )
    translate_headers = fields.Boolean(
        load_default=True,
        metadata={
            "description": "If true (default), translate CSV headers to the current locale."
        },
    )
    years_after_death = fields.Integer(
        load_default=0,
        metadata={
            "description": "Number of years after death during which a person is still treated as living (default 0)."
        },
    )
    jwt = fields.String(
        required=False,
        metadata={"description": "JWT token for download authentication."},
    )


class ExporterFileResource(ProtectedResource, GrampsJSONEncoder):
    """Export file resource."""

    @api_blueprint.arguments(ExporterFileQueryArgs, location="query")
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

    @api_blueprint.arguments(ExporterFileQueryArgs, location="query")
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
