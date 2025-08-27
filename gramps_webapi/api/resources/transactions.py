#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021-2024      David Straub
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

"""Raw database transaction API resource."""

import json

from flask import Response, request
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from webargs import fields

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ...types import ResponseReturnValue
from ..auth import require_permissions
from ..tasks import AsyncResult, make_task_response, process_transactions, run_task
from ..util import abort_with_message, use_args, get_tree_from_jwt_or_fail
from . import ProtectedResource
from .util import reverse_transaction

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsResource(ProtectedResource):
    """Resource for raw database transactions."""

    @use_args(
        {
            "undo": fields.Boolean(load_default=False),
            "force": fields.Boolean(load_default=False),
            "background": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def post(self, args) -> ResponseReturnValue:
        """Post the transaction."""
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ, PERM_DEL_OBJ])
        payload = request.json
        if not payload:
            abort_with_message(400, "Empty payload")
        is_undo = args["undo"]
        if is_undo:
            payload = reverse_transaction(payload)
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        if args["background"]:
            task = run_task(
                process_transactions,
                tree=tree,
                user_id=user_id,
                payload=payload,
                force=args["force"],
            )
            if isinstance(task, AsyncResult):
                return make_task_response(task)
            return task, 200
        try:
            trans_dict = process_transactions(
                tree=tree, user_id=user_id, payload=payload, force=args["force"]
            )
        except ValueError as exc:
            abort_with_message(400, str(exc))
        res = Response(
            response=json.dumps(trans_dict),
            status=200,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", str(len(trans_dict)))
        return res
