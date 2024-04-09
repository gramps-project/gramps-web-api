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
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from webargs import fields, validate

from ...auth import get_all_user_details
from ...auth.const import PERM_VIEW_PRIVATE
from ...const import TREE_MULTI
from ..auth import require_permissions
from ..util import get_db_handle, get_tree_from_jwt, use_args
from . import ProtectedResource

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
    """Resource for database transaction history."""

    @use_args(
        {
            "old": fields.Boolean(load_default=False),
            "new": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict, transaction_id: int) -> Response:
        """Return a list of transactions."""
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
