#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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

"""Authentication endpoint blueprint."""

from typing import Any, Iterable

from flask import abort, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
)
from webargs import fields, validate

from ...auth import (
    authorized,
    get_all_user_details,
    get_guid,
    get_name,
    get_permissions,
    is_tree_disabled,
)
from ...auth.const import CLAIM_LIMITED_SCOPE, SCOPE_CREATE_ADMIN, SCOPE_CREATE_OWNER
from ...const import TREE_MULTI
from ..ratelimiter import limiter
from ..util import abort_with_message, get_tree_id, tree_exists, use_args
from . import RefreshProtectedResource, Resource


def get_tokens(
    user_id: str,
    permissions: Iterable[str],
    tree_id: str,
    include_refresh: bool = False,
    fresh: bool = False,
):
    """Create access token (and refresh token if desired)."""
    claims: dict[str, Any] = {"permissions": list(permissions)}
    if tree_id:
        claims["tree"] = tree_id
    access_token = create_access_token(
        identity=str(user_id), additional_claims=claims, fresh=fresh
    )
    if not include_refresh:
        return {"access_token": access_token}
    refresh_token = create_refresh_token(identity=str(user_id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


class TokenResource(Resource):
    """Resource for obtaining a JWT."""

    @limiter.limit("1/second")
    @use_args(
        {
            "username": fields.Str(required=True, validate=validate.Length(min=1)),
            "password": fields.Str(required=True, validate=validate.Length(min=1)),
        },
        location="json",
    )
    def post(self, args):
        """Post username and password to fetch a token."""
        if "username" not in args or "password" not in args:
            abort_with_message(401, "Missing username or password")
        if not authorized(args.get("username"), args.get("password")):
            abort_with_message(403, "Invalid username or password")
        user_id = get_guid(args["username"])
        tree_id = get_tree_id(user_id)
        if is_tree_disabled(tree=tree_id):
            abort_with_message(503, "This tree is temporarily disabled")
        permissions = get_permissions(username=args["username"], tree=tree_id)
        return get_tokens(
            user_id=user_id,
            permissions=permissions,
            tree_id=tree_id,
            include_refresh=True,
            fresh=True,
        )


class TokenRefreshResource(RefreshProtectedResource):
    """Resource for refreshing a JWT."""

    @limiter.limit("1/second")
    def post(self):
        """Fetch a new token."""
        user_id = get_jwt_identity()
        try:
            username = get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
        tree_id = get_tree_id(user_id)
        if is_tree_disabled(tree=tree_id):
            abort_with_message(503, "This tree is temporarily disabled")
        permissions = get_permissions(username=username, tree=tree_id)
        return get_tokens(
            user_id=user_id,
            permissions=permissions,
            tree_id=tree_id,
            include_refresh=False,
            fresh=False,
        )


class TokenCreateOwnerResource(Resource):
    """Resource for getting a token that allows creating a site admin or tree owner account."""

    @limiter.limit("1/second")
    def get(self):
        """Get a token."""
        # This GET method is deprecated and only kept for backward compatibility!
        if get_all_user_details(tree=None):
            # users already exist!
            abort_with_message(405, "Users already exist")
        token = create_access_token(
            identity="admin",
            additional_claims={
                CLAIM_LIMITED_SCOPE: SCOPE_CREATE_ADMIN,
            },
        )
        return {"access_token": token}

    @limiter.limit("1/second")
    @use_args(
        {
            "tree": fields.Str(required=False),
        },
        location="json",
    )
    def post(self, args):
        """Get a token."""
        tree = args.get("tree")
        if (
            tree
            and current_app.config["TREE"] != TREE_MULTI
            and tree != current_app.config["TREE"]
        ):
            abort_with_message(403, "Not allowed in single-tree setup")
        if tree and not tree_exists(tree):
            abort(404)
        if get_all_user_details(
            # only include treeless users in single-tree setup
            tree=tree,
            include_treeless=current_app.config["TREE"] != TREE_MULTI,
        ):
            # users already exist!
            abort_with_message(405, "Users already exist")
        if tree:
            claims = {
                CLAIM_LIMITED_SCOPE: SCOPE_CREATE_OWNER,
                "tree": tree,
            }
        else:
            claims = {CLAIM_LIMITED_SCOPE: SCOPE_CREATE_ADMIN}
        token = create_access_token(identity="owner", additional_claims=claims)
        return {"access_token": token}, 201
