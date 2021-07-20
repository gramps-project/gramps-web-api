#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021      David Straub
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

"""Object creation API resource."""

import json
from typing import Any, Dict, Sequence

import gramps
import jsonschema
from flask import Response, abort, request
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbWriteBase
from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
    Tag,
)
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.lib.serialize import from_json

from ...auth.const import PERM_ADD_OBJ
from ..auth import require_permissions
from ..util import get_db_handle
from . import ProtectedResource
from .util import add_object, validate_object_dict


class CreateObjectsResource(ProtectedResource):
    """Resource for creating multiple objects."""

    def _parse_objects(self) -> Sequence[GrampsObject]:
        """Parse the objects."""
        payload = request.json
        objects = []
        for obj_dict in payload:
            if not validate_object_dict(obj_dict):
                abort(400)
            obj = from_json(json.dumps(obj_dict))
            objects.append(obj)
        return objects

    def post(self) -> Response:
        """Post the objects."""
        require_permissions([PERM_ADD_OBJ])
        objects = self._parse_objects()
        if not objects:
            abort(400)
        db_handle = get_db_handle(readonly=False)
        with DbTxn("Add objects", db_handle) as trans:
            for obj in objects:
                try:
                    add_object(db_handle, obj, trans, fail_if_exists=True)
                except ValueError:
                    abort(400)
        return Response(status=201)
