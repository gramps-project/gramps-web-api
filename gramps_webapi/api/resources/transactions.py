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

"""Raw database transaction API resource."""

import json
from typing import Dict

from flask import Response, abort, current_app, request
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, TXNADD, TXNDEL, TXNUPD
from gramps.gen.errors import HandleError
from gramps.gen.lib.serialize import from_json, to_json
from gramps.gen.merge.diff import diff_items

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from ..search import SearchIndexer
from ..util import get_db_handle
from . import ProtectedResource
from .util import transaction_to_json

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsResource(ProtectedResource):
    """Resource for raw database transactions."""

    def post(self) -> Response:
        """Post the transaction."""
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ, PERM_DEL_OBJ])
        payload = request.json
        if not payload:
            abort(400)  # disallow empty payload
        db_handle = get_db_handle(readonly=False)
        with DbTxn("Raw transaction", db_handle) as trans:
            for item in payload:
                try:
                    class_name = item["_class"]
                    trans_type = item["type"]
                    handle = item["handle"]
                    old_data = item["old"]
                    if not self.old_unchanged(db_handle, class_name, handle, old_data):
                        abort(409)  # object has changed!
                    new_data = item["new"]
                    if new_data:
                        new_obj = from_json(json.dumps(new_data))
                    if trans_type == "delete":
                        self.handle_delete(trans, class_name, handle)
                    elif trans_type == "add":
                        self.handle_add(trans, class_name, new_obj)
                    elif trans_type == "update":
                        self.handle_commit(trans, class_name, new_obj)
                    else:
                        abort(400)  # unexpected type
                except (KeyError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    abort(400)
            trans_dict = transaction_to_json(trans)
        # update search index
        indexer: SearchIndexer = current_app.config["SEARCH_INDEXER"]
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                if _trans_dict["type"] == "delete":
                    indexer.delete_object(writer, handle)
                else:
                    indexer.add_or_update_object(writer, handle, db_handle, class_name)
        res = Response(
            response=json.dumps(trans_dict), status=200, mimetype="application/json",
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
            abort(400)  # gramps ID missing!
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
