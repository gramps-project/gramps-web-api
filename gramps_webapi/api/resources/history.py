#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Database Transaction history endpoints."""

import json
from typing import Dict

from flask import Response, current_app
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db import REFERENCE_KEY
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from webargs import fields, validate

from ...auth import get_all_user_details
from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ, PERM_VIEW_PRIVATE
from ...const import TREE_MULTI
from ...types import ResponseReturnValue
from ..auth import require_permissions
from ..tasks import (
    AsyncResult,
    make_task_response,
    process_transactions,
    run_task,
    old_unchanged,
)
from ..util import (
    abort_with_message,
    get_db_handle,
    get_tree_from_jwt,
    get_tree_from_jwt_or_fail,
    use_args,
)
from . import ProtectedResource
from .util import reverse_transaction

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsHistoryResource(ProtectedResource):
    """Resource for database transaction history."""

    @use_args(
        {
            "old": fields.Boolean(load_default=False),
            "new": fields.Boolean(load_default=False),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
            "sort": fields.Str(validate=validate.Length(min=1)),
            "before": fields.Float(load_default=None),
            "after": fields.Float(load_default=None),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Return a list of transactions."""
        require_permissions([PERM_VIEW_PRIVATE])
        db_handle = get_db_handle()
        transactions = []
        undodb = db_handle.undodb
        ascending = args.get("sort") != "-id"
        transactions, count = undodb.get_transactions(
            page=args["page"],
            pagesize=args["pagesize"],
            old_data=args["old"],
            new_data=args["new"],
            ascending=ascending,
            before=args["before"],
            after=args["after"],
        )

        # replace user IDs by user name
        user_dict = get_user_dict()
        transactions = [
            fix_transaction_user(transaction, user_dict) for transaction in transactions
        ]
        res = Response(
            response=json.dumps(transactions),
            status=200,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", count)
        return res


class TransactionHistoryResource(ProtectedResource):
    """Resource for viewing individual transaction history."""

    @use_args(
        {
            "old": fields.Boolean(load_default=False),
            "new": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict, transaction_id: int) -> Response:
        """Return a single transaction."""
        require_permissions([PERM_VIEW_PRIVATE])
        db_handle = get_db_handle()
        undodb = db_handle.undodb
        transaction = undodb.get_transaction(
            transaction_id=transaction_id,
            old_data=args["old"],
            new_data=args["new"],
        )

        # replace user IDs by user name
        user_dict = get_user_dict()
        transaction = fix_transaction_user(transaction, user_dict)

        return transaction


class TransactionUndoResource(ProtectedResource):
    """Resource for undoing transactions."""

    def get(self, transaction_id: int) -> ResponseReturnValue:
        """Check if a transaction can be undone without conflicts."""
        require_permissions([PERM_VIEW_PRIVATE])

        # Get the transaction to check
        db_handle = get_db_handle()
        undodb = db_handle.undodb
        try:
            transaction = undodb.get_transaction(
                transaction_id=transaction_id,
                old_data=True,
                new_data=True,
            )
        except AttributeError:
            abort_with_message(404, f"Transaction {transaction_id} not found")

        if not transaction:
            abort_with_message(404, f"Transaction {transaction_id} not found")

        # Check each change in the transaction for conflicts
        conflicts: list[dict] = []
        can_undo_without_force = True

        for change in transaction["changes"]:
            # Skip reference entries as they are handled automatically by the database
            if str(change["obj_class"]) == str(REFERENCE_KEY):
                continue

            class_name = change["obj_class"]
            handle = change["obj_handle"]
            old_data = change.get("old_data")

            if change["trans_type"] == TXNDEL:
                # Check if an object with this handle already exists (would be a conflict)
                handle_func = db_handle.method("has_%s_handle", class_name)
                if handle_func and handle_func(handle):
                    conflicts.append(
                        {
                            "change_index": len(conflicts),
                            "object_class": class_name,
                            "handle": handle,
                            "conflict_type": "object_exists",
                            "description": f"Cannot undo delete: object with handle {handle} already exists",
                        }
                    )
                    can_undo_without_force = False
            else:
                try:
                    if change["trans_type"] == TXNADD:
                        # For add transactions, check if current object differs from what was added (new_data)
                        new_data = change.get("new_data")
                        unchanged = old_unchanged(
                            db_handle, class_name, handle, new_data
                        )
                    else:
                        # For update transactions, check if current object differs from pre-update state (old_data)
                        unchanged = old_unchanged(
                            db_handle, class_name, handle, old_data
                        )

                    if not unchanged:
                        conflicts.append(
                            {
                                "change_index": len(conflicts),
                                "object_class": class_name,
                                "handle": handle,
                                "conflict_type": "object_changed",
                                "description": f"Object {class_name} with handle {handle} has been modified since the original transaction",
                            }
                        )
                        can_undo_without_force = False
                except Exception as e:
                    if "No handle function found" in str(e):
                        # Skip objects we can't check (like references)
                        continue
                    conflicts.append(
                        {
                            "change_index": len(conflicts),
                            "object_class": class_name,
                            "handle": handle,
                            "conflict_type": "check_failed",
                            "description": f"Could not verify object state: {str(e)}",
                        }
                    )
                    can_undo_without_force = False

        result = {
            "transaction_id": transaction_id,
            "can_undo_without_force": can_undo_without_force,
            "total_changes": len(
                [
                    c
                    for c in transaction["changes"]
                    if str(c["obj_class"]) != str(REFERENCE_KEY)
                ]
            ),
            "conflicts_count": len(conflicts),
            "conflicts": conflicts,
        }

        return result, 200

    @use_args(
        {
            "force": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def post(self, args: Dict, transaction_id: int) -> ResponseReturnValue:
        """Undo a transaction using background processing."""
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ, PERM_DEL_OBJ])

        # Get the transaction to undo
        db_handle = get_db_handle()
        undodb = db_handle.undodb
        try:
            transaction = undodb.get_transaction(
                transaction_id=transaction_id,
                old_data=True,
                new_data=True,
            )
        except AttributeError:
            # This happens when get_transaction returns None and we try to call _to_dict()
            abort_with_message(404, f"Transaction {transaction_id} not found")

        if not transaction:
            abort_with_message(404, f"Transaction {transaction_id} not found")

        # Convert transaction to the format expected by reverse_transaction
        # Skip reference entries as they are handled automatically by the database
        payload = []
        for change in transaction["changes"]:
            if str(change["obj_class"]) == str(REFERENCE_KEY):
                continue  # Skip reference entries
            item = {
                "type": {TXNADD: "add", TXNUPD: "update", TXNDEL: "delete"}[
                    change["trans_type"]
                ],
                "_class": change["obj_class"],
                "handle": change["obj_handle"],
                "old": change.get("old_data"),
                "new": change.get("new_data"),
            }
            payload.append(item)

        # Reverse the transaction
        reversed_payload = reverse_transaction(payload)

        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()

        # Always use background processing for undo operations
        task = run_task(
            process_transactions,
            tree=tree,
            user_id=user_id,
            payload=reversed_payload,
            force=args["force"],
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return task, 200


def get_user_dict() -> Dict[str, Dict[str, str]]:
    """Get a dictionary with user IDs to user names."""
    tree = get_tree_from_jwt()
    is_single = current_app.config["TREE"] != TREE_MULTI
    users = get_all_user_details(
        tree=tree, include_treeless=is_single, include_guid=True
    )
    return {
        str(user["user_id"]): {"name": user["name"], "full_name": user["full_name"]}
        for user in users
    }


def fix_transaction_user(transaction, user_dict):
    """Replace the user ID by the user name."""

    return {
        **transaction,
        "connection": {
            **{k: v for k, v in transaction["connection"].items() if k != "user_id"},
            "user": user_dict.get(transaction["connection"]["user_id"]),
        },
    }
