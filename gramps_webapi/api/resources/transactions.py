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

from marshmallow import Schema
from flask import Response, request
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from webargs import fields

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ...types import ResponseReturnValue
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..tasks import (
    AsyncResult,
    apply_transactions,
    make_task_response,
    process_transactions,
    run_task,
    update_search_indices_from_transaction,
)
from ..util import abort_with_message, get_tree_from_jwt_or_fail
from . import ProtectedResource
from .schemas import TransactionSchema
from .util import reverse_transaction

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsQueryArgs(Schema):
    """Query arguments for POST /transactions/."""

    undo = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, apply the inverse of the transaction."},
    )
    message = fields.String(
        load_default="Raw transaction",
        metadata={"description": "Message to use for the transaction in the undo log."},
    )
    force = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, force applying the transaction even if objects have been modified."
        },
    )
    background = fields.Boolean(
        load_default=False,
        metadata={
        "description": "If true and Celery is configured, apply the transactions in the background and return HTTP 202. Use this for anything but a few objects.",
        },
    )


class TransactionsResource(ProtectedResource):
    """Resource for raw database transactions."""

    @api_blueprint.response(200, TransactionSchema(many=True))
    @api_blueprint.arguments(TransactionsQueryArgs, location="query")
    def post(self, args) -> ResponseReturnValue:
        """Replay a raw database transaction.

        Low-level endpoint for replaying transactions that are already
        internally consistent: those recorded by Gramps itself (e.g. when
        synchronizing a desktop database) or returned by this API (e.g. to undo
        a change). Objects are written as given: they are not validated against
        the schema, references between objects are not maintained (e.g. a
        family's members are not updated), and derived data such as a person's
        birth and death indices is not recomputed. A malformed or inconsistent
        transaction can therefore corrupt the tree.

        To create, modify, or delete individual records, use the object
        endpoints (e.g. `POST /people/`) instead. Unless `force` is set, the
        transaction is rejected if any object's `old` state no longer matches
        the database. Set `background` for anything but a few objects.
        """
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
                message=args["message"],
            )
            if isinstance(task, AsyncResult):
                return make_task_response(task)
            return task, 200
        try:
            trans_dict = apply_transactions(
                tree=tree,
                user_id=user_id,
                payload=payload,
                force=args["force"],
                message=args["message"],
            )
        except ValueError as exc:
            abort_with_message(400, str(exc))
        # index updates can take minutes, so defer them to the task queue (if
        # configured), as the object endpoints do
        run_task(
            update_search_indices_from_transaction,
            trans_dict=trans_dict,
            tree=tree,
            user_id=user_id,
        )
        res = Response(
            response=json.dumps(trans_dict),
            status=200,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", str(len(trans_dict)))
        return res
