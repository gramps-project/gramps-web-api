#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David Straub
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

"""Background task resources."""

import os
import re
import uuid
from typing import Dict, Optional

from flask import abort, current_app
from gramps.gen.config import config
from webargs import fields
from werkzeug.security import safe_join

from ...auth.const import PERM_ADD_TREE, PERM_EDIT_OTHER_TREE, PERM_EDIT_TREE
from ...dbmanager import WebDbManager
from ..auth import require_permissions
from ..util import get_tree_from_jwt, use_args
from . import ProtectedResource

# legal tree dirnames
TREE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_tree_details(tree_id: str) -> Dict[str, str]:
    """Get details about a tree."""
    try:
        dbmgr = WebDbManager(dirname=tree_id, create_if_missing=False)
    except ValueError:
        abort(404)
    return {"name": dbmgr.name, "id": tree_id}


def get_tree_path(tree_id: str) -> Optional[str]:
    """Get the path to the tree."""
    dbdir = config.get("database.path")
    return safe_join(dbdir, tree_id)


def tree_exists(tree_id: str) -> bool:
    """Check whether a tree exists."""
    tree_path = get_tree_path(tree_id)
    return tree_path and os.path.isdir(tree_path)


def validate_tree_id(tree_id: str) -> None:
    """Raise an error if the tree ID has an illegal format."""
    if not TREE_ID_REGEX.match(tree_id):
        abort(422)


def get_single_tree_id() -> str:
    """Get the tree ID in the case of using app.config['TREE']."""
    dbmgr = WebDbManager(name=current_app.config["TREE"], create_if_missing=False)
    return dbmgr.dirname


class TreesResource(ProtectedResource):
    """Resource for getting info about trees."""

    def get(self):
        """Get info about all trees."""
        user_tree_id = get_tree_from_jwt() or get_single_tree_id()
        # only allowed to see details about our own tree
        tree_ids = [user_tree_id]
        return [get_tree_details(tree_id) for tree_id in tree_ids]

    @use_args(
        {
            "name": fields.Str(required=True),
        },
        location="json",
    )
    def post(self, args):
        """Create a new tree."""
        require_permissions([PERM_ADD_TREE])
        tree_id = str(uuid.uuid4())
        # TODO dbid
        dbmgr = WebDbManager(dirname=tree_id, name=args["name"], create_if_missing=True)
        return {"name": args["name"], "tree_id": dbmgr.dirname}, 201


class TreeResource(ProtectedResource):
    """Resource for a single tree."""

    def get(self, tree_id: str):
        """Get info about a tree."""
        validate_tree_id(tree_id)
        user_tree_id = get_tree_from_jwt() or get_single_tree_id()
        if tree_id != user_tree_id:
            # only allowed to see details about our own tree
            abort(403)
        return get_tree_details(tree_id)

    @use_args(
        {
            "name": fields.Str(required=True),
        },
        location="json",
    )
    def put(self, args, tree_id: str):
        """Modify a tree."""
        user_tree_id = get_tree_from_jwt() or get_single_tree_id()
        if tree_id == user_tree_id:
            require_permissions([PERM_EDIT_TREE])
        else:
            require_permissions([PERM_EDIT_OTHER_TREE])
            validate_tree_id(tree_id)
        try:
            dbmgr = WebDbManager(dirname=tree_id, create_if_missing=False)
        except ValueError:
            abort(404)
        old_name, new_name = dbmgr.rename_database(new_name=args["name"])
        return {"old_name": old_name, "new_name": new_name}
