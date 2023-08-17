#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021-2023      David Straub
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
from typing import Dict

from flask import Response, request
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from gramps.gen.errors import HandleError
from gramps.gen.lib.serialize import from_json, to_json
from gramps.gen.merge.diff import diff_items
from webargs import fields

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from ..search import SearchIndexer
from ..util import (
    abort_with_message,
    check_quota_people,
    get_db_handle,
    get_search_indexer,
    get_tree_from_jwt,
    update_usage_people,
    use_args,
)
from . import ProtectedResource
from .util import reverse_transaction, transaction_to_json

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsResource(ProtectedResource):
    """Resource for raw database transactions."""

    @use_args(
        {
            "undo": fields.Boolean(load_default=False),
            "force": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def post(self, args) -> Response:
        """Post the transaction."""
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ, PERM_DEL_OBJ])
        payload = request.json
        if not payload:
            abort_with_message(400, "Empty payload")
        is_undo = args["undo"]
        if is_undo:
            payload = reverse_transaction(payload)
        db_handle = get_db_handle(readonly=False)
        num_people_deleted = sum(
            item["type"] == "delete" and item["_class"] == "Person" for item in payload
        )
        num_people_added = sum(
            item["type"] == "add" and item["_class"] == "Person" for item in payload
        )
        num_people_new = num_people_added - num_people_deleted
        check_quota_people(to_add=num_people_new)
        with DbTxn("Raw transaction", db_handle) as trans:
            for item in payload:
                try:
                    class_name = item["_class"]
                    trans_type = item["type"]
                    handle = item["handle"]
                    old_data = item["old"]
                    if not args["force"] and not self.old_unchanged(
                        db_handle, class_name, handle, old_data
                    ):
                        if num_people_added or num_people_deleted:
                            update_usage_people()
                        abort_with_message(409, "Object has changed")
                    new_data = item["new"]
                    if new_data:
                        new_obj = from_json(json.dumps(new_data))
                    if trans_type == "delete":
                        self.handle_delete(trans, class_name, handle)
                        if (
                            class_name == "Person"
                            and handle == db_handle.get_default_handle()
                        ):
                            db_handle.set_default_person_handle(None)
                    elif trans_type == "add":
                        self.handle_add(trans, class_name, new_obj)
                    elif trans_type == "update":
                        self.handle_commit(trans, class_name, new_obj)
                    else:
                        if num_people_added or num_people_deleted:
                            update_usage_people()
                        abort_with_message(400, "Unexpected transaction type")
                except (KeyError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    if num_people_added or num_people_deleted:
                        update_usage_people()
                    abort_with_message(400, "Error while processing transaction")
            trans_dict = transaction_to_json(trans)
        if num_people_new:
            update_usage_people()
        # update search index
        tree = get_tree_from_jwt()
        indexer: SearchIndexer = get_search_indexer(tree)
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                if _trans_dict["type"] == "delete":
                    indexer.delete_object(writer, handle)
                else:
                    indexer.add_or_update_object(writer, handle, db_handle, class_name)
        res = Response(
            response=json.dumps(trans_dict),
            status=200,
            mimetype="application/json",
        )
        res.headers.add("X-Total-Count", len(trans_dict))
        return res

    def handle_delete(self, trans: DbTxn, class_name: str, handle: str) -> None:
        """Handle a delete action."""
        del_func = trans.db.method("remove_%s", class_name)
        del_func(handle, trans)

    def handle_commit(self, trans: DbTxn, class_name: str, obj) -> None:
        """Handle an update action."""
        com_func = trans.db.method("commit_%s", class_name)
        com_func(obj, trans)

    def handle_add(self, trans: DbTxn, class_name: str, obj) -> None:
        """Handle an add action."""
        if class_name != "Tag" and not obj.gramps_id:
            abort_with_message(400, "Gramps ID missing")
        self.handle_commit(trans, class_name, obj)

    def old_unchanged(
        self, db: DbReadBase, class_name: str, handle: str, old_data: Dict
    ) -> bool:
        """Check if the "old" object is still unchanged."""
        handle_func = db.method("get_%s_from_handle", class_name)
        try:
            obj = handle_func(handle)
        except HandleError:
            if old_data is None:
                return True
            return False
        obj_dict = json.loads(to_json(obj))
        if diff_items(class_name, old_data, obj_dict):
            return False
        return True
