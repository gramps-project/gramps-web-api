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
from typing import Sequence

from flask import Response, abort, current_app, request
from gramps.gen.db import DbTxn
from gramps.gen.lib import Family, Person
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.lib.serialize import from_json

from ...auth.const import PERM_ADD_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from ..search import SearchIndexer
from ..util import (
    abort_with_message,
    check_quota_people,
    get_db_handle,
    get_search_indexer,
    get_tree_from_jwt,
    update_usage_people,
)
from . import ProtectedResource
from .util import add_object, fix_object_dict, transaction_to_json, validate_object_dict


class CreateObjectsResource(ProtectedResource):
    """Resource for creating multiple objects."""

    def _parse_objects(self) -> Sequence[GrampsObject]:
        """Parse the objects."""
        payload = request.json
        objects = []
        for obj_dict in payload:
            try:
                obj_dict = fix_object_dict(obj_dict)
            except ValueError:
                abort_with_message(400, "Error processing objects")
            if not validate_object_dict(obj_dict):
                abort_with_message(400, "Validation error while processing objects")
            obj = from_json(json.dumps(obj_dict))
            objects.append(obj)
        return objects

    def post(self) -> Response:
        """Post the objects."""
        require_permissions([PERM_ADD_OBJ])
        objects = self._parse_objects()
        if any(isinstance(obj, Family) for obj in objects):
            # If any of the objects to add is a Family object,
            # require EDIT permissions in addition to ADD
            # since creating a Family object modifies the family
            # members' Person objects as well
            require_permissions([PERM_EDIT_OBJ])
        if not objects:
            abort_with_message(400, "Empty payload")
        number_new_people = sum(isinstance(obj, Person) for obj in objects)
        check_quota_people(to_add=number_new_people)
        db_handle = get_db_handle(readonly=False)
        with DbTxn("Add objects", db_handle) as trans:
            for obj in objects:
                try:
                    add_object(db_handle, obj, trans, fail_if_exists=True)
                except ValueError:
                    abort_with_message(400, "Error while adding object")
            trans_dict = transaction_to_json(trans)
        if number_new_people:
            update_usage_people()
        # update search index
        tree = get_tree_from_jwt()
        indexer: SearchIndexer = get_search_indexer(tree)
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer.add_or_update_object(writer, handle, db_handle, class_name)
        res = Response(
            response=json.dumps(trans_dict),
            status=201,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", len(trans_dict))
        return res
