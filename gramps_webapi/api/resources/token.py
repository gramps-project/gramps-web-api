#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

from typing import Optional, Iterable

from flask import abort, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
)
from webargs import fields, validate

from ...auth.const import CLAIM_LIMITED_SCOPE, SCOPE_CREATE_OWNER
from ..ratelimiter import limiter
from ..util import use_args
from . import RefreshProtectedResource, Resource
from ...dbmanager import WebDbManager


def get_tokens(
    user_id: str,
    permissions: Iterable[str],
    tree_id: Optional[str] = None,
    include_refresh: bool = False,
):
    """Create access token (and refresh token if desired)."""
    claims = {"permissions": list(permissions)}
    if tree_id:
        claims["tree"] = tree_id
    access_token = create_access_token(identity=str(user_id), additional_claims=claims)
    if not include_refresh:
        return {"access_token": access_token}
    refresh_token = create_refresh_token(identity=str(user_id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def get_tree_id(guid: str) -> str:
    """Get the appropriate tree ID for a user."""
    auth_provider = current_app.config.get("AUTH_PROVIDER")
    tree_id = auth_provider.get_tree(guid)
    if not tree_id:
        # needed for backwards compatibility!
        dbmgr = WebDbManager(name=current_app.config["TREE"], create_if_missing=False)
        tree_id = dbmgr.dirname
    return tree_id


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
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if "username" not in args or "password" not in args:
            abort(401)
        if not auth_provider.authorized(args.get("username"), args.get("password")):
            abort(403)
        permissions = auth_provider.get_permissions(args["username"])
        user_id = auth_provider.get_guid(args["username"])
        tree_id = get_tree_id(user_id)
        return get_tokens(
            user_id=user_id,
            permissions=permissions,
            tree_id=tree_id,
            include_refresh=True,
        )


class TokenRefreshResource(RefreshProtectedResource):
    """Resource for refreshing a JWT."""

    @limiter.limit("1/second")
    def post(self):
        """Fetch a fresh token."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        user_id = get_jwt_identity()
        try:
            username = auth_provider.get_name(user_id)
        except ValueError:
            abort(401)
        permissions = auth_provider.get_permissions(username)
        tree_id = get_tree_id(user_id)
        return get_tokens(
            user_id=user_id,
            permissions=permissions,
            tree_id=tree_id,
            include_refresh=False,
        )


class TokenCreateOwnerResource(Resource):
    """Resource for getting a token that allows creating an owner account."""

    @limiter.limit("1/second")
    def get(self):
        """Get a token."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider.get_all_user_details():
            # users already exist!
            abort(405)
        token = create_access_token(
            identity="owner",
            additional_claims={
                CLAIM_LIMITED_SCOPE: SCOPE_CREATE_OWNER,
            },
        )
        return {"access_token": token}
