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

import hashlib
import json
from typing import Dict

from flask import Response
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db import REFERENCE_KEY
from gramps.gen.db.dbconst import KEY_TO_CLASS_MAP, TXNADD, TXNDEL, TXNUPD
from marshmallow import Schema
from webargs import fields, validate

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ, PERM_VIEW_PRIVATE
from ...types import ResponseReturnValue
from ..auth import require_permissions
from ..cache import get_user_dict
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
    get_tree_from_jwt_or_fail,
)
from ..blueprint import api_blueprint
from . import ProtectedResource
from .schemas import ObjectChangeSchema, UndoTransactionSchema
from .util import etag_unchanged, reverse_transaction

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}
OBJECT_CLASSES = sorted(set(KEY_TO_CLASS_MAP.values()))


class TransactionsHistoryQueryArgs(Schema):
    """Query arguments for GET /transactions/history/."""

    old = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data before the change."
        },
    )
    new = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data after the change."
        },
    )
    page = fields.Integer(
        load_default=0,
        validate=validate.Range(min=1),
        metadata={
            "description": "Page number of the result subset to return. If omitted, all results are returned."
        },
    )
    pagesize = fields.Integer(
        load_default=20,
        validate=validate.Range(min=1),
        metadata={"description": "Number of items per page when pagination is active."},
    )
    sort = fields.Str(
        validate=validate.Length(min=1),
        metadata={
            "description": "Sort order for transactions. Use 'id' for ascending or '-id' for descending."
        },
    )
    before = fields.Float(
        load_default=None,
        metadata={
            "description": "Unix timestamp; if provided, return only transactions committed before this time."
        },
    )
    after = fields.Float(
        load_default=None,
        metadata={
            "description": "Unix timestamp; if provided, return only transactions committed after this time."
        },
    )
    before_id = fields.Integer(
        load_default=None,
        validate=validate.Range(min=0),
        metadata={
            "description": "Transaction ID; if provided, return only transactions with an id strictly less than this value. Unlike the timestamp-based `before`/`after` cursor, this is exact and has no floating-point precision loss."
        },
    )
    after_id = fields.Integer(
        load_default=None,
        validate=validate.Range(min=0),
        metadata={
            "description": "Transaction ID; if provided, return only transactions with an id strictly greater than this value. Unlike the timestamp-based `before`/`after` cursor, this is exact and has no floating-point precision loss. 0 means 'from the beginning'."
        },
    )


class TransactionsHistoryResource(ProtectedResource):
    """Resource for database transaction history."""

    @api_blueprint.response(200, UndoTransactionSchema(many=True))
    @api_blueprint.arguments(TransactionsHistoryQueryArgs, location="query")
    def get(self, args: Dict) -> Response:
        """Return a list of transactions."""
        require_permissions([PERM_VIEW_PRIVATE])
        db_handle = get_db_handle()
        undodb = db_handle.undodb

        max_id, count = undodb.get_transactions_state(
            before=args["before"],
            after=args["after"],
            before_id=args["before_id"],
            after_id=args["after_id"],
        )
        etag = transactions_etag(args, max_id, count)
        if etag_unchanged(etag):
            return transactions_response(None, count=count, etag=etag)

        ascending = args.get("sort") != "-id"
        transactions, count = undodb.get_transactions(
            page=args["page"],
            pagesize=args["pagesize"],
            old_data=args["old"],
            new_data=args["new"],
            ascending=ascending,
            before=args["before"],
            after=args["after"],
            before_id=args["before_id"],
            after_id=args["after_id"],
            known_count=count,
        )

        # replace user IDs by user name
        user_dict = get_user_dict(transaction_user_ids(transactions))
        transactions = [
            fix_transaction_user(transaction, user_dict) for transaction in transactions
        ]
        return transactions_response(json.dumps(transactions), count=count, etag=etag)


class ObjectHistoryQueryArgs(Schema):
    """Query arguments for GET /transactions/history/objects/<obj_class>/<obj_handle>/."""

    old = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data before the change."
        },
    )
    new = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data after the change."
        },
    )
    page = fields.Integer(
        load_default=0,
        validate=validate.Range(min=1),
        metadata={
            "description": "Page number of the result subset to return. If omitted, all results are returned."
        },
    )
    pagesize = fields.Integer(
        load_default=20,
        validate=validate.Range(min=1),
        metadata={"description": "Number of items per page when pagination is active."},
    )
    sort = fields.Str(
        validate=validate.Length(min=1),
        metadata={
            "description": "Sort order for changes. Use 'id' for ascending or '-id' for descending (by timestamp)."
        },
    )
    before = fields.Float(
        load_default=None,
        metadata={
            "description": "Unix timestamp; if provided, return only changes committed before this time."
        },
    )
    after = fields.Float(
        load_default=None,
        metadata={
            "description": "Unix timestamp; if provided, return only changes committed after this time."
        },
    )


class ObjectHistoryResource(ProtectedResource):
    """Resource for the change history of a single object."""

    @api_blueprint.response(200, ObjectChangeSchema(many=True))
    @api_blueprint.arguments(ObjectHistoryQueryArgs, location="query")
    def get(self, args: Dict, obj_class: str, obj_handle: str) -> Response:
        """Return the change history of a single object as a flat list of changes."""
        require_permissions([PERM_VIEW_PRIVATE])
        if obj_class not in OBJECT_CLASSES:
            abort_with_message(422, f"Unknown object class: {obj_class}")
        db_handle = get_db_handle()
        undodb = db_handle.undodb

        max_ts, count = undodb.get_object_changes_state(
            obj_class=obj_class,
            obj_handle=obj_handle,
            before=args["before"],
            after=args["after"],
        )
        etag = transactions_etag(args, max_ts, count, obj_key=(obj_class, obj_handle))
        if etag_unchanged(etag):
            return transactions_response(None, count=count, etag=etag)

        ascending = args.get("sort") != "-id"
        changes, count = undodb.get_object_changes(
            obj_class=obj_class,
            obj_handle=obj_handle,
            page=args["page"],
            pagesize=args["pagesize"],
            old_data=args["old"],
            new_data=args["new"],
            ascending=ascending,
            before=args["before"],
            after=args["after"],
            known_count=count,
        )

        # replace user IDs by user name
        user_dict = get_user_dict(transaction_user_ids(changes))
        changes = [fix_transaction_user(change, user_dict) for change in changes]
        return transactions_response(json.dumps(changes), count=count, etag=etag)


class TransactionHistoryQueryArgs(Schema):
    """Query arguments for GET /transactions/history/<id>/."""

    old = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data before the change."
        },
    )
    new = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include the raw object data after the change."
        },
    )


class TransactionHistoryResource(ProtectedResource):
    """Resource for viewing individual transaction history."""

    @api_blueprint.response(200, UndoTransactionSchema())
    @api_blueprint.arguments(TransactionHistoryQueryArgs, location="query")
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
        if not transaction:
            abort_with_message(404, f"Transaction {transaction_id} not found")

        # replace user IDs by user name
        user_dict = get_user_dict(transaction_user_ids([transaction]))
        transaction = fix_transaction_user(transaction, user_dict)

        return transaction


class UndoQueryArgs(Schema):
    """Query arguments for POST /history/transactions/<id>/undo/."""

    force = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, force the undo even if there are conflicts."
        },
    )
    message = fields.String(
        load_default=None,
        metadata={
            "description": "Message to use for the transaction in the undo log. Defaults to 'Undo'."
        },
    )


class TransactionUndoResource(ProtectedResource):
    """Resource for undoing transactions."""

    def get(self, transaction_id: int) -> ResponseReturnValue:
        """Check if a transaction can be undone without conflicts."""
        require_permissions([PERM_VIEW_PRIVATE])

        # Get the transaction to check
        db_handle = get_db_handle()
        undodb = db_handle.undodb
        transaction = undodb.get_transaction(
            transaction_id=transaction_id,
            old_data=True,
            new_data=True,
        )
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
                        # For update transactions, check if current object still matches the
                        # post-update state (new_data). If so, nothing has changed since this
                        # transaction and it's safe to undo.
                        new_data = change.get("new_data")
                        unchanged = old_unchanged(
                            db_handle, class_name, handle, new_data
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

    @api_blueprint.arguments(UndoQueryArgs, location="query")
    def post(self, args: Dict, transaction_id: int) -> ResponseReturnValue:
        """Undo a transaction using background processing."""
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ, PERM_DEL_OBJ])

        # Get the transaction to undo
        db_handle = get_db_handle()
        undodb = db_handle.undodb
        transaction = undodb.get_transaction(
            transaction_id=transaction_id,
            old_data=True,
            new_data=True,
        )
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
        message = args["message"] or "Undo"
        task = run_task(
            process_transactions,
            tree=tree,
            user_id=user_id,
            payload=reversed_payload,
            force=args["force"],
            message=message,
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return task, 200


def transaction_user_ids(transactions: list[Dict]) -> set[str]:
    """Get the IDs of the users that committed the given transactions."""
    return {transaction["connection"]["user_id"] for transaction in transactions}


def transactions_etag(
    args: Dict, max_id: int | None, count: int, obj_key: tuple | None = None
) -> str:
    """Build a cache validator for a page of the transaction history.

    `obj_key` (obj_class, obj_handle) scopes the ETag to a single object's
    history so it cannot collide with the ETag of another object's history.

    The user names resolved into the response are not covered: a rename becomes
    visible only once the next transaction is written.
    """
    tree_id = get_tree_from_jwt_or_fail()
    state = json.dumps(
        [tree_id, obj_key, max_id, count, args], sort_keys=True, default=str
    )
    return hashlib.sha256(state.encode()).hexdigest()


def transactions_response(payload: str | None, count: int, etag: str) -> Response:
    """Build the transaction history response, or a 304 if payload is None."""
    res = Response(
        response=payload,
        status=200 if payload is not None else 304,
        mimetype="application/json",
    )
    res.headers.add("X-Total-Count", str(count))
    res.headers.add("ETag", f'"{etag}"')
    # let the client cache the response, but always revalidate it
    res.headers.add("Cache-Control", "no-cache")
    return res


def fix_transaction_user(transaction, user_dict):
    """Replace the user ID by the user name."""

    return {
        **transaction,
        "connection": {
            **{k: v for k, v in transaction["connection"].items() if k != "user_id"},
            "user": user_dict.get(transaction["connection"]["user_id"]),
        },
    }
