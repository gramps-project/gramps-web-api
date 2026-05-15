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

"""Persistent access token resources."""

from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema
from webargs import fields

from ...auth import (
    get_name,
    get_user_access_token,
    normalize_access_token_scope,
    revoke_user_access_token,
    rotate_user_access_token,
)
from ...auth.const import PERM_EDIT_OWN_USER
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import abort_with_message
from . import ProtectedResource


class AccessTokenStateSchema(Schema):
    """Response schema for persistent access token state."""

    active = fields.Boolean(
        required=True,
        metadata={"description": "Whether a token is currently active."},
    )
    token = fields.Str(
        allow_none=True,
        metadata={"description": "Persistent token value when active, else null."},
    )


class UserAccessTokenResource(ProtectedResource):
    """Resource for managing current user's persistent tokens by scope."""

    def _get_user_name(self) -> str:
        user_id = get_jwt_identity()
        try:
            return get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
            raise  # unreachable

    def _validate_scope(self, scope: str) -> str:
        try:
            return normalize_access_token_scope(scope)
        except ValueError as exc:
            abort_with_message(422, str(exc))
            raise  # unreachable

    @api_blueprint.response(200, AccessTokenStateSchema())
    @require_permissions([PERM_EDIT_OWN_USER])
    def get(self, scope: str):
        """Get persistent token status for current user and scope."""
        scope = self._validate_scope(scope)
        user_name = self._get_user_name()
        token = get_user_access_token(user_name, scope)
        return {"active": token is not None, "token": token}, 200

    @api_blueprint.response(200, AccessTokenStateSchema())
    @require_permissions([PERM_EDIT_OWN_USER])
    def post(self, scope: str):
        """Create or rotate persistent token for current user and scope."""
        scope = self._validate_scope(scope)
        user_name = self._get_user_name()
        token = rotate_user_access_token(user_name, scope)
        return {"active": True, "token": token}, 200

    @api_blueprint.response(200, AccessTokenStateSchema())
    @require_permissions([PERM_EDIT_OWN_USER])
    def delete(self, scope: str):
        """Revoke persistent token for current user and scope."""
        scope = self._validate_scope(scope)
        user_name = self._get_user_name()
        revoke_user_access_token(user_name, scope)
        return {"active": False, "token": None}, 200
