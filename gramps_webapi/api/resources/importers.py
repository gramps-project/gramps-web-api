#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2022      David Straub
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

"""Importers Plugin API resource."""

import tempfile
from http import HTTPStatus
from typing import Any, Dict

from flask import Response, abort, request
from webargs import fields

from ...auth.const import PERM_IMPORT_FILE
from ..auth import require_permissions
from ..tasks import AsyncResult, import_file, make_task_response, run_task
from ..util import get_db_handle, get_tree_from_jwt, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_importers


class ImportersResource(ProtectedResource, GrampsJSONEncoder):
    """Importers resource."""

    @use_args({}, location="query")
    def get(self, args: Dict[str, Any]) -> Response:
        """Get all available importer attributes."""
        get_db_handle()  # needed to load plugins
        return self.response(200, get_importers())


class ImporterResource(ProtectedResource, GrampsJSONEncoder):
    """Import resource."""

    @use_args({}, location="query")
    def get(self, args: Dict[str, Any], extension: str) -> Response:
        """Get specific report attributes."""
        get_db_handle()  # needed to load plugins
        importers = get_importers(extension)
        if not importers:
            abort(404)
        return self.response(200, importers[0])


class ImporterFileResource(ProtectedResource):
    """Import file resource."""

    @use_args(
        {
            "jwt": fields.String(required=False),
        },
        location="query",
    )
    def post(self, args: Dict, extension: str) -> Response:
        """Import file."""
        require_permissions([PERM_IMPORT_FILE])
        get_db_handle()  # needed to load plugins
        request_stream = request.stream
        with tempfile.NamedTemporaryFile(delete=False) as ftmp:
            ftmp.write(request_stream.read())
            tmp_file_name = ftmp.name
        importers = get_importers(extension.lower())
        if not importers:
            abort(HTTPStatus.NOT_FOUND)
        tree = get_tree_from_jwt()
        task = run_task(
            import_file,
            tree=tree,
            file_name=tmp_file_name,
            extension=extension.lower(),
            delete=True,
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return Response(status=201)
