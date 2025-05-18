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

from flask import Response, jsonify, request
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db import DbTxn
from gramps.gen.lib import Family, Person
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject

# from gramps.gen.lib.serialize import from_json
from webargs import fields, validate

from gramps_webapi.types import ResponseReturnValue

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ_BATCH, PERM_EDIT_OBJ
from ...const import GRAMPS_OBJECT_PLURAL
from ..auth import require_permissions
from ..tasks import (
    AsyncResult,
    delete_objects,
    make_task_response,
    run_task,
    update_search_indices_from_transaction,
)
from ..util import (
    abort_with_message,
    check_quota_people,
    get_db_handle,
    get_tree_from_jwt_or_fail,
    gramps_object_from_dict,
    update_usage_people,
    use_args,
)
from . import FreshProtectedResource, ProtectedResource
from .util import add_object, fix_object_dict, transaction_to_json, validate_object_dict


class CreateObjectsResource(ProtectedResource):
    """Resource for creating multiple objects."""

    def _parse_objects(self) -> Sequence[GrampsObject]:
        """Parse the objects."""
        payload = request.json or []
        objects = []
        for obj_dict in payload:
            try:
                obj_dict = fix_object_dict(obj_dict)
            except ValueError:
                abort_with_message(400, "Error processing objects")
            if not validate_object_dict(obj_dict):
                abort_with_message(400, "Validation error while processing objects")
            obj = gramps_object_from_dict(obj_dict)
            objects.append(obj)
        return objects

    def post(self) -> ResponseReturnValue:
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
        with DbTxn("Add multiple objects", db_handle) as trans:
            for obj in objects:
                try:
                    add_object(db_handle, obj, trans, fail_if_exists=True)
                except ValueError:
                    abort_with_message(400, "Error while adding object")
            trans_dict = transaction_to_json(trans)
        if number_new_people:
            update_usage_people()
        # update search indices
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        run_task(
            update_search_indices_from_transaction,
            trans_dict=trans_dict,
            tree=tree,
            user_id=user_id,
        )
        res = Response(
            response=json.dumps(trans_dict),
            status=201,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", str(len(trans_dict)))
        return res


class DeleteObjectsResource(FreshProtectedResource):
    """Resource for deleting multiple objects."""

    @use_args(
        {
            "namespaces": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=list(GRAMPS_OBJECT_PLURAL.values())
                ),
            ),
        },
        location="query",
    )
    def post(self, args) -> ResponseReturnValue:
        """Delete the objects."""
        require_permissions([PERM_DEL_OBJ_BATCH])
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        task = run_task(
            delete_objects,
            tree=tree,
            user_id=user_id,
            namespaces=args.get("namespaces") or None,
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 200
