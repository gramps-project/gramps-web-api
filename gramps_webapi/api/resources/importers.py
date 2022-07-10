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

import os
import tempfile
import uuid
from http import HTTPStatus
from typing import IO, Any, Dict

from flask import Response, abort, request
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.plug import BasePluginManager
from gramps.gen.user import User
from webargs import fields

from ...auth.const import PERM_IMPORT_FILE
from ..auth import require_permissions
from ..tasks import search_reindex_full
from ..util import get_db_handle, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder


# list of importers (by file extension) that are not allowed
DISABLED_IMPORTERS = ["gpkg"]


def get_importers(extension: str = None):
    """Extract and return list of importers."""
    importers = []
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_import_plugins():
        if extension is not None and extension != plugin.get_extension():
            continue
        if extension in DISABLED_IMPORTERS:
            continue
        importer = {
            "name": plugin.get_name(),
            "description": plugin.get_description(),
            "extension": plugin.get_extension(),
            "module": plugin.get_module_name(),
        }
        importers.append(importer)
    return importers


def run_import(db_handle: DbReadBase, file_obj: IO[bytes], extension: str) -> None:
    """Generate the import."""
    tmp_dir = tempfile.gettempdir()
    file_name = os.path.join(tmp_dir, f"{uuid.uuid4()}.{extension}")
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_import_plugins():
        if extension == plugin.get_extension():
            import_function = plugin.get_import_function()
            with open(file_name, "wb") as f:
                f.write(file_obj.read())
            result = import_function(db_handle, file_name, User())
            os.remove(file_name)
            if not result:
                abort(500)
            return


class ImportersResource(ProtectedResource, GrampsJSONEncoder):
    """Importers resource."""

    @use_args({}, location="query")
    def get(self, args: Dict[str, Any]) -> Response:
        """Get all available importer attributes."""
        get_db_handle()
        return self.response(200, get_importers())


class ImporterResource(ProtectedResource, GrampsJSONEncoder):
    """Import resource."""

    @use_args({}, location="query")
    def get(self, args: Dict[str, Any], extension: str) -> Response:
        """Get specific report attributes."""
        get_db_handle()
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
        db_handle = get_db_handle()
        importers = get_importers(extension.lower())
        if not importers:
            abort(HTTPStatus.NOT_FOUND)
        run_import(db_handle, request.stream, extension.lower())
        search_reindex_full()
        return Response(status=201)
