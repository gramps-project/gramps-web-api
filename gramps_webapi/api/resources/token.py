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

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from flask import abort, current_app, request
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
from ...auth.oidc_helpers import is_oidc_enabled
from ...auth.const import CLAIM_LIMITED_SCOPE, SCOPE_CREATE_ADMIN, SCOPE_CREATE_OWNER
from ...const import TREE_MULTI
from ..ratelimiter import limiter
from ..util import abort_with_message, get_tree_id, tree_exists, use_args
from . import RefreshProtectedResource, Resource

logger = logging.getLogger(__name__)

# In-memory storage for temporary login tokens
# Maps token -> {user_id, tree_id, permissions, expires_at}
_LOGIN_TOKENS: Dict[str, Dict[str, Any]] = {}
_LOGIN_TOKEN_TIMESTAMPS: Dict[str, datetime] = {}

# Temporary token expiration time (5 minutes)
LOGIN_TOKEN_EXPIRY_MINUTES = 5


def get_tokens(
    user_id: str,
    permissions: Iterable[str],
    tree_id: str,
    include_refresh: bool = False,
    fresh: bool = False,
    oidc_provider: Optional[str] = None,
):
    """Create access token (and refresh token if desired)."""
    claims: dict[str, Any] = {"permissions": list(permissions)}
    if tree_id:
        claims["tree"] = tree_id
    if oidc_provider:
        claims["oidc_provider"] = oidc_provider
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
        # Check if local authentication is disabled when OIDC is enabled
        if is_oidc_enabled() and current_app.config.get(
            "OIDC_DISABLE_LOCAL_AUTH", False
        ):
            abort_with_message(
                403, "Local authentication is disabled. Please use OIDC authentication."
            )

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


def _create_login_token(user_id: str, tree_id: str, permissions: Iterable[str]) -> str:
    """Create a temporary login token.

    Args:
        user_id: User GUID
        tree_id: Tree ID
        permissions: User permissions

    Returns:
        Temporary token string
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(minutes=LOGIN_TOKEN_EXPIRY_MINUTES)
    _LOGIN_TOKENS[token] = {
        "user_id": user_id,
        "tree_id": tree_id,
        "permissions": list(permissions),
        "expires_at": expires_at,
    }
    _LOGIN_TOKEN_TIMESTAMPS[token] = datetime.now()
    logger.debug(f"Created temporary login token for user {user_id}")
    return token


def _get_login_token_data(token: str) -> Optional[Dict[str, Any]]:
    """Get data for a temporary login token.

    Args:
        token: Temporary token string

    Returns:
        Token data dict or None if invalid/expired
    """
    if token not in _LOGIN_TOKENS:
        return None
    data = _LOGIN_TOKENS[token]
    if datetime.now() > data["expires_at"]:
        # Token expired, remove it
        _LOGIN_TOKENS.pop(token, None)
        _LOGIN_TOKEN_TIMESTAMPS.pop(token, None)
        return None
    return data


def _consume_login_token(token: str) -> Optional[Dict[str, Any]]:
    """Get and remove a temporary login token (one-time use).

    Args:
        token: Temporary token string

    Returns:
        Token data dict or None if invalid/expired
    """
    data = _get_login_token_data(token)
    if data:
        # Remove token after use (one-time use)
        _LOGIN_TOKENS.pop(token, None)
        _LOGIN_TOKEN_TIMESTAMPS.pop(token, None)
    return data


def _cleanup_expired_login_tokens() -> int:
    """Remove expired login tokens.

    Returns:
        Number of tokens removed
    """
    now = datetime.now()
    to_remove = [
        token for token, data in _LOGIN_TOKENS.items() if now > data["expires_at"]
    ]
    for token in to_remove:
        _LOGIN_TOKENS.pop(token, None)
        _LOGIN_TOKEN_TIMESTAMPS.pop(token, None)
    if to_remove:
        logger.debug(f"Cleaned up {len(to_remove)} expired login tokens")
    return len(to_remove)


class LoginResource(Resource):
    """Resource for programmatic login that returns a redirect URL with token."""

    @limiter.limit("1/second")
    @use_args(
        {
            "username": fields.Str(required=True, validate=validate.Length(min=1)),
            "password": fields.Str(required=True, validate=validate.Length(min=1)),
            "redirect": fields.Str(required=False, validate=validate.Length(min=1)),
        },
        location="json",
    )
    def post(self, args):
        """Post username and password to get a redirect URL with temporary token."""
        # Check if local authentication is disabled when OIDC is enabled
        if is_oidc_enabled() and current_app.config.get(
            "OIDC_DISABLE_LOCAL_AUTH", False
        ):
            abort_with_message(
                403, "Local authentication is disabled. Please use OIDC authentication."
            )

        if "username" not in args or "password" not in args:
            abort_with_message(401, "Missing username or password")
        if not authorized(args.get("username"), args.get("password")):
            abort_with_message(403, "Invalid username or password")

        user_id = get_guid(args["username"])
        tree_id = get_tree_id(user_id)
        if is_tree_disabled(tree=tree_id):
            abort_with_message(503, "This tree is temporarily disabled")
        permissions = get_permissions(username=args["username"], tree=tree_id)

        # Create temporary token
        temp_token = _create_login_token(user_id, tree_id, permissions)

        # Clean up expired tokens periodically
        _cleanup_expired_login_tokens()

        # Build redirect URL
        redirect_path = args.get("redirect", "/")
        # Get the frontend URL from request origin or config
        frontend_url = request.headers.get("Origin") or current_app.config.get(
            "FRONTEND_URL", ""
        )
        if frontend_url:
            # Remove trailing slash if present
            frontend_url = frontend_url.rstrip("/")
        else:
            # Fallback to relative URL
            frontend_url = ""

        redirect_url = (
            f"{frontend_url}/login?token={temp_token}&redirect={redirect_path}"
        )

        # Return redirect URL
        return {"redirect_url": redirect_url}, 200


class LoginTokenResource(Resource):
    """Resource for exchanging temporary login token for access tokens."""

    @limiter.limit("1/second")
    @use_args(
        {
            "token": fields.Str(required=True, validate=validate.Length(min=1)),
        },
        location="query",
    )
    def get(self, args):
        """Exchange temporary token for access and refresh tokens."""
        token = args.get("token")
        if not token:
            abort_with_message(400, "Missing token parameter")

        # Get and consume token (one-time use)
        token_data = _consume_login_token(token)
        if not token_data:
            abort_with_message(401, "Invalid or expired token")

        # Clean up expired tokens periodically
        _cleanup_expired_login_tokens()

        # Generate real tokens
        return get_tokens(
            user_id=token_data["user_id"],
            permissions=token_data["permissions"],
            tree_id=token_data["tree_id"],
            include_refresh=True,
            fresh=True,
        )
