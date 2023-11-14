#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Reports Plugin API resource."""

import json
import mimetypes
import os
import re
import time
from typing import Dict

from flask import Response, abort, current_app, jsonify, send_file
from webargs import fields, validate

from ...auth.const import PERM_EDIT_OBJ, PERM_VIEW_PRIVATE
from ...const import MIME_TYPES
from ..auth import has_permissions
from ..report import check_report_id_exists, get_reports, run_report
from ..tasks import AsyncResult, generate_report, make_task_response, run_task
from ..util import get_buffer_for_file, get_db_handle, get_tree_from_jwt, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import check_fix_default_person


class ReportsResource(ProtectedResource, GrampsJSONEncoder):
    """Reports resource."""

    @use_args({"include_help": fields.Boolean(load_default=False)}, location="query")
    def get(self, args: Dict) -> Response:
        """Get all available report attributes."""
        if has_permissions({PERM_EDIT_OBJ}):
            check_fix_default_person(get_db_handle(readonly=False))
        reports = get_reports(
            get_db_handle(), include_options_help=args["include_help"]
        )
        return self.response(200, reports)


class ReportResource(ProtectedResource, GrampsJSONEncoder):
    """Report resource."""

    @use_args({"include_help": fields.Boolean(load_default=True)}, location="query")
    def get(self, args: Dict, report_id: str) -> Response:
        """Get specific report attributes."""
        if has_permissions({PERM_EDIT_OBJ}):
            check_fix_default_person(get_db_handle(readonly=False))
        reports = get_reports(
            get_db_handle(),
            report_id=report_id,
            include_options_help=args["include_help"],
        )
        if not reports:
            abort(404)
        return self.response(200, reports[0])


class ReportFileResource(ProtectedResource, GrampsJSONEncoder):
    """Report file resource."""

    @use_args(
        {
            "options": fields.Str(validate=validate.Length(min=1)),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "jwt": fields.String(required=False),
        },
        location="query",
    )
    def get(self, args: Dict, report_id: str) -> Response:
        """Get specific report attributes."""
        report_options = {}
        if "options" in args:
            try:
                report_options = json.loads(args["options"])
            except json.JSONDecodeError:
                abort(400)
        if "of" in report_options:
            abort(422)

        if has_permissions({PERM_EDIT_OBJ}):
            check_fix_default_person(get_db_handle(readonly=False))

        file_name, file_type = run_report(
            db_handle=get_db_handle(),
            report_id=report_id,
            report_options=report_options,
            language=args["locale"],
        )
        report_path = current_app.config.get("REPORT_DIR")
        file_path = os.path.join(report_path, file_name)
        buffer = get_buffer_for_file(file_path, not_found=True)
        return send_file(buffer, mimetype=MIME_TYPES[file_type])

    @use_args(
        {
            "options": fields.Str(validate=validate.Length(min=1)),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "jwt": fields.String(required=False),
        },
        location="query",
    )
    def post(self, args: Dict, report_id: str) -> Response:
        """Create the report."""
        report_options = {}
        if "options" in args:
            try:
                report_options = json.loads(args["options"])
            except json.JSONDecodeError:
                abort(400)
        if "of" in report_options:
            abort(422)
        if has_permissions({PERM_EDIT_OBJ}):
            check_fix_default_person(get_db_handle(readonly=False))
        tree = get_tree_from_jwt()
        task = run_task(
            generate_report,
            tree=tree,
            report_id=report_id.lower(),
            options=report_options,
            view_private=has_permissions({PERM_VIEW_PRIVATE}),
            locale=args["locale"],
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201


class ReportFileResultResource(ProtectedResource, GrampsJSONEncoder):
    """Report file result resource."""

    def get(self, report_id: str, filename: str) -> Response:
        """Get the processed file."""
        if not check_report_id_exists(report_id):
            # do not allow a non-existing report ID to be supplied by the user
            abort(404)
        report_path = current_app.config.get("REPORT_DIR")

        # assert the filename is legit
        regex = re.compile(
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(\.[\w\.]*)"
        )
        match = regex.match(filename)
        if not match:
            abort(422)

        file_type = match.group(2)
        file_path = os.path.join(report_path, filename)
        if not os.path.isfile(file_path):
            abort(404)
        date_lastmod = time.localtime(os.path.getmtime(file_path))
        buffer = get_buffer_for_file(file_path, delete=True)
        mime_type = "application/octet-stream"
        if file_type != ".pl" and file_type in mimetypes.types_map:
            mime_type = mimetypes.types_map[file_type]
        date_str = time.strftime("%Y%m%d%H%M%S", date_lastmod)
        download_name = f"gramps-web-{report_id}-{date_str}{file_type}"
        return send_file(buffer, mimetype=mime_type, download_name=download_name)
