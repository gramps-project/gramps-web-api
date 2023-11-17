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

from ...auth import disable_enable_tree, get_tree_usage, set_tree_quota
from ...auth.const import (
    PERM_ADD_TREE,
    PERM_DISABLE_TREE,
    PERM_EDIT_OTHER_TREE,
    PERM_EDIT_TREE,
    PERM_EDIT_TREE_QUOTA,
)
from ...const import TREE_MULTI
from ...dbmanager import WebDbManager
from ..auth import require_permissions
from ..util import abort_with_message, get_tree_from_jwt, use_args
from . import ProtectedResource

# legal tree dirnames
TREE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_tree_details(tree_id: str) -> Dict[str, str]:
    """Get details about a tree."""
    try:
        dbmgr = WebDbManager(
            dirname=tree_id,
            create_if_missing=False,
            ignore_lock=current_app.config["IGNORE_DB_LOCK"],
        )
    except ValueError:
        abort(404)
    usage = get_tree_usage(tree_id) or {}
    return {"name": dbmgr.name, "id": tree_id, **usage}


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
        abort_with_message(422, "Invalid tree ID")


class TreesResource(ProtectedResource):
    """Resource for getting info about trees."""

    def get(self):
        """Get info about all trees."""
        user_tree_id = get_tree_from_jwt()
        # only allowed to see details about our own tree
        tree_ids = [user_tree_id]
        return [get_tree_details(tree_id) for tree_id in tree_ids]

    @use_args(
        {
            "name": fields.Str(required=True),
            "quota_media": fields.Integer(required=False),
            "quota_people": fields.Integer(required=False),
        },
        location="json",
    )
    def post(self, args):
        """Create a new tree."""
        if current_app.config["TREE"] != TREE_MULTI:
            abort_with_message(405, "Not allowed in single-tree setup")
        require_permissions([PERM_ADD_TREE])
        tree_id = str(uuid.uuid4())
        backend = current_app.config["NEW_DB_BACKEND"]
        WebDbManager(
            dirname=tree_id,
            name=args["name"],
            create_if_missing=True,
            create_backend=backend,
        )
        if args.get("quota_media") or args.get("quota_people"):
            set_tree_quota(
                tree=tree_id,
                quota_media=args.get("quota_media"),
                quota_people=args.get("quota_people"),
            )
        return get_tree_details(tree_id), 201


class TreeResource(ProtectedResource):
    """Resource for a single tree."""

    def get(self, tree_id: str):
        """Get info about a tree."""
        if tree_id == "-":
            # own tree
            tree_id = get_tree_from_jwt()
        else:
            validate_tree_id(tree_id)
            user_tree_id = get_tree_from_jwt()
            if tree_id != user_tree_id:
                # only allowed to see details about our own tree
                abort_with_message(403, "Not authorized to view other trees")
        return get_tree_details(tree_id)

    @use_args(
        {
            "name": fields.Str(required=False, load_default=None),
            "quota_media": fields.Integer(required=False),
            "quota_people": fields.Integer(required=False),
        },
        location="json",
    )
    def put(self, args, tree_id: str):
        """Modify a tree."""
        if tree_id == "-":
            # own tree
            tree_id = get_tree_from_jwt()
            require_permissions([PERM_EDIT_TREE])
        else:
            user_tree_id = get_tree_from_jwt()
            if tree_id == user_tree_id:
                require_permissions([PERM_EDIT_TREE])
            else:
                require_permissions([PERM_EDIT_OTHER_TREE])
                validate_tree_id(tree_id)
        try:
            dbmgr = WebDbManager(
                dirname=tree_id,
                create_if_missing=False,
                ignore_lock=current_app.config["IGNORE_DB_LOCK"],
            )
        except ValueError:
            abort(404)
        rv = {}
        if args["name"]:
            old_name, new_name = dbmgr.rename_database(new_name=args["name"])
            rv.update({"old_name": old_name, "new_name": new_name})
        if args.get("quota_media") is not None or args.get("quota_people") is not None:
            require_permissions([PERM_EDIT_TREE_QUOTA])
            set_tree_quota(
                tree=tree_id,
                quota_media=args.get("quota_media"),
                quota_people=args.get("quota_people"),
            )
            for quota in ["quota_media", "quota_people"]:
                if args.get(quota) is not None:
                    rv.update({quota: args[quota]})
        return rv


class DisableEnableTreeResource(ProtectedResource):
    """Base class for disabling or enabling a tree."""

    def _post_disable_enable_tree(self, tree_id: str, disabled: bool):
        """Disable or enable a tree."""
        if current_app.config["TREE"] != TREE_MULTI:
            abort_with_message(405, "Not allowed in single-tree setup")
        if tree_id == "-":
            # own tree
            tree_id = get_tree_from_jwt()
        if not tree_exists(tree_id):
            abort(404)
        require_permissions([PERM_DISABLE_TREE])
        disable_enable_tree(tree=tree_id, disabled=disabled)
        return "", 201


class DisableTreeResource(DisableEnableTreeResource):
    """Resource for disabling a tree."""

    def post(self, tree_id: str):
        """Disable a tree."""
        return self._post_disable_enable_tree(tree_id=tree_id, disabled=True)


class EnableTreeResource(DisableEnableTreeResource):
    """Resource for enabling a tree."""

    def post(self, tree_id: str):
        """Disable a tree."""
        return self._post_disable_enable_tree(tree_id=tree_id, disabled=False)
