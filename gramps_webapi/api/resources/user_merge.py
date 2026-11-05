#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Resource for merging two users."""

import logging

from flask_jwt_extended import get_jwt_identity

from ...auth import (
    UserMergeError,
    get_guid,
    get_tree,
    get_user_details,
    get_user_oidc_accounts,
    merge_users,
)
from ...auth.const import PERM_DEL_OTHER_TREE_USER, PERM_EDIT_OTHER_TREE_USER
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import (
    abort_with_message,
    close_db,
    get_db_outside_request,
    get_tree_id_or_none,
)
from . import FreshProtectedResource
from .schemas import UserMergeSchema, UserSchema

logger = logging.getLogger(__name__)


def _reassign_history(tree: str, source_id: str, target_id: str) -> None:
    """Attribute the source's edits in the tree's history to the target.

    The undo database is separate from the user database, so this runs after
    the merge is committed. A failure only affects the history's attribution.
    """
    try:
        db_handle = get_db_outside_request(
            tree=tree, view_private=True, readonly=True, user_id=get_jwt_identity()
        )
        try:
            db_handle.undodb.reassign_user(source_id, target_id)
        finally:
            close_db(db_handle)
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "Merged user %s into %s, but could not update the history of tree %s",
            source_id,
            target_id,
            tree,
            exc_info=True,
        )


class UserMergeResource(FreshProtectedResource):
    """Merge a user into another one."""

    @api_blueprint.response(200, UserSchema())
    @api_blueprint.arguments(UserMergeSchema, location="json")
    def post(self, args, user_name: str):
        """Merge another user into this one and delete the other user.

        The OIDC accounts, persistent access tokens, push subscriptions, tasks
        and edit history of the other user move to this one, which keeps its
        own name, password, e-mail address and role. Site admins only.
        """
        require_permissions([PERM_EDIT_OTHER_TREE_USER, PERM_DEL_OTHER_TREE_USER])
        try:
            target_id = str(get_guid(user_name))
            source_id = str(get_guid(args["source"]))
        except ValueError:
            abort_with_message(404, "User with this name does not exist")
        if source_id == target_id:
            abort_with_message(400, "Cannot merge a user into itself")
        if source_id == get_jwt_identity():
            abort_with_message(409, "Cannot merge away the own user")
        # as stored, which can be empty in a single-tree setup
        source_tree, target_tree = get_tree(source_id), get_tree(target_id)
        tree = get_tree_id_or_none(target_id)
        if get_tree_id_or_none(source_id) != tree:
            abort_with_message(409, "The users belong to different trees")
        try:
            merge_users(source_id, target_id, source_tree, target_tree)
        except UserMergeError as exc:
            abort_with_message(409, str(exc))
        except ValueError:
            abort_with_message(404, "User with this name does not exist")
        if tree:
            _reassign_history(tree, source_id, target_id)
        details = get_user_details(user_name, include_guid=True)
        if details is None:
            # renamed or deleted concurrently
            abort_with_message(404, "User with this name does not exist")
        details["oidc_accounts"] = get_user_oidc_accounts(target_id)
        return details
