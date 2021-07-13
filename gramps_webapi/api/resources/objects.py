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


def add_object(db_handle: DbWriteBase, obj: GrampsObject, trans: DbTxn):
    """Commit a Gramps object to the database."""
    try:
        if isinstance(obj, Person):
            return db_handle.add_person(obj, trans)
        if isinstance(obj, Family):
            return db_handle.add_family(obj, trans)
        if isinstance(obj, Event):
            return db_handle.add_event(obj, trans)
        if isinstance(obj, Place):
            return db_handle.add_place(obj, trans)
        if isinstance(obj, Repository):
            return db_handle.add_repository(obj, trans)
        if isinstance(obj, Source):
            return db_handle.add_source(obj, trans)
        if isinstance(obj, Citation):
            return db_handle.add_citation(obj, trans)
        if isinstance(obj, Media):
            return db_handle.add_media(obj, trans)
        if isinstance(obj, Note):
            return db_handle.add_note(obj, trans)
        if isinstance(obj, Tag):
            return db_handle.add_tag(obj, trans)
    except AttributeError:
        raise ValueError("Database does not support writing.")
    raise ValueError("Unexpected object type.")


def validate_object_dict(obj_dict: Dict[str, Any]) -> bool:
    """Validate a dict representation of a Gramps object vs. its schema."""
    try:
        obj_cls = getattr(gramps.gen.lib, obj_dict["_class"])
    except (KeyError, AttributeError):
        return False
    schema = obj_cls.get_schema()
    try:
        jsonschema.validate(obj_dict, schema)
    except jsonschema.exceptions.ValidationError:
        return False
    return True


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
        db_handle = get_db_handle()
        with DbTxn("Add objects", db_handle) as trans:
            for obj in objects:
                add_object(db_handle, obj, trans)
        return Response(status=201)
