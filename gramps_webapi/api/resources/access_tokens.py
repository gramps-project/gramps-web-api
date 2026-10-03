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
from webargs import fields, validate

from ...auth import (
    AccessTokenConflictError,
    User,
    create_user_access_token,
    delete_user_access_token,
    get_name,
    get_user_from_access_token,
    has_user_access_token,
    list_user_access_tokens,
    normalize_access_token_scope,
    revoke_user_access_token,
    rotate_user_access_token,
)
from ...auth.const import (
    ACCESS_TOKEN_LABEL_MAX_LENGTH,
    ACCESS_TOKEN_SCOPES_MULTIPLE,
    PERM_EDIT_OWN_USER,
)
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import abort_with_message, get_tree_from_jwt_or_fail
from . import ProtectedResource


def get_active_user_from_access_token(token: str, scope: str) -> User:
    """Return the user owning a persistent access token, or abort.

    Aborts with 401 if the token is unknown or revoked, and with 403 if the
    account is disabled or unconfirmed. Checking the tree is left to the
    caller, since what a missing or disabled tree means depends on the scope.
    """
    user = get_user_from_access_token(token, scope)
    if user is None:
        abort_with_message(401, "Invalid access token")
    if user.role is None or user.role < 0:
        abort_with_message(403, "User account is disabled")
    return user


class AccessTokenStatusSchema(Schema):
    """Response schema for persistent access token status."""

    active = fields.Boolean(
        required=True,
        metadata={"description": "Whether a token is currently active."},
    )


class AccessTokenCreateSchema(Schema):
    """Response schema for newly created or rotated persistent token."""

    active = fields.Boolean(
        required=True,
        metadata={"description": "Whether a token is currently active."},
    )
    token = fields.Str(
        required=True,
        metadata={"description": "Newly created persistent token value."},
    )


class AccessTokenLabelSchema(Schema):
    """Request body for creating a labelled persistent token."""

    label = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=ACCESS_TOKEN_LABEL_MAX_LENGTH),
        metadata={
            "description": "Name of the device or client using the token, "
            "unique among the user's tokens of this scope."
        },
    )


class AccessTokenInfoSchema(Schema):
    """Response schema for one labelled persistent token, without its value."""

    id = fields.Int(
        required=True,
        metadata={"description": "ID of the token, used to revoke it."},
    )
    label = fields.Str(
        required=True,
        metadata={"description": "Name of the device or client using the token."},
    )
    created_at = fields.DateTime(
        required=True,
        metadata={"description": "When the token was created (UTC)."},
    )
    last_used_at = fields.DateTime(
        allow_none=True,
        metadata={"description": "When the token was last used (UTC), if ever."},
    )


class AccessTokenInfoCreateSchema(AccessTokenInfoSchema):
    """Response schema for a newly created labelled persistent token."""

    token = fields.Str(
        required=True,
        metadata={
            "description": "The token value. It is only returned once and "
            "can't be retrieved later."
        },
    )


def _access_token_info(access_token) -> dict:
    """Return the public details of a labelled persistent token."""
    return {
        "id": access_token.id,
        "label": access_token.label,
        "created_at": access_token.created_at,
        "last_used_at": access_token.last_used_at,
    }


class AccessTokenResourceBase(ProtectedResource):
    """Base for resources managing the current user's persistent tokens."""

    # whether the resource handles scopes with several tokens per user
    multiple: bool = False

    def _get_user_name(self) -> str:
        user_id = get_jwt_identity()
        try:
            return get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
            raise  # unreachable

    def _validate_scope(self, scope: str) -> str:
        try:
            scope = normalize_access_token_scope(scope)
        except ValueError as exc:
            abort_with_message(422, str(exc))
            raise  # unreachable
        if self.multiple and scope not in ACCESS_TOKEN_SCOPES_MULTIPLE:
            abort_with_message(
                422,
                "This scope allows a single token per user, "
                f"use /users/-/access-tokens/{scope}/",
            )
        if not self.multiple and scope in ACCESS_TOKEN_SCOPES_MULTIPLE:
            abort_with_message(
                422,
                "This scope allows several tokens per user, "
                f"use /users/-/access-tokens/{scope}/tokens/",
            )
        return scope

    def _prepare(self, scope: str) -> tuple[str, str]:
        """Check permissions and return the validated scope and user name."""
        require_permissions([PERM_EDIT_OWN_USER])
        # persistent tokens grant access to tree-scoped data, so they are
        # meaningless without a tree
        get_tree_from_jwt_or_fail()
        return self._validate_scope(scope), self._get_user_name()


class UserAccessTokenResource(AccessTokenResourceBase):
    """Resource for managing current user's persistent tokens by scope.

    Only for scopes with a single token per user.
    """

    @api_blueprint.response(200, AccessTokenStatusSchema())
    def get(self, scope: str):
        """Get persistent token status for current user and scope."""
        scope, user_name = self._prepare(scope)
        active = has_user_access_token(user_name, scope)
        return {"active": active}, 200

    @api_blueprint.response(200, AccessTokenCreateSchema())
    def post(self, scope: str):
        """Create or rotate persistent token for current user and scope."""
        scope, user_name = self._prepare(scope)
        token = rotate_user_access_token(user_name, scope)
        return {"active": True, "token": token}, 200

    @api_blueprint.response(200, AccessTokenStatusSchema())
    def delete(self, scope: str):
        """Revoke persistent token for current user and scope."""
        scope, user_name = self._prepare(scope)
        revoke_user_access_token(user_name, scope)
        return {"active": False}, 200


class UserAccessTokenListResource(AccessTokenResourceBase):
    """Resource for the current user's labelled tokens of a scope.

    Only for scopes with several tokens per user, e.g. one per sync device.
    """

    multiple = True

    @api_blueprint.response(200, AccessTokenInfoSchema(many=True))
    def get(self, scope: str):
        """List the current user's tokens for the scope, oldest first."""
        scope, user_name = self._prepare(scope)
        access_tokens = list_user_access_tokens(user_name, scope)
        return [_access_token_info(access_token) for access_token in access_tokens]

    @api_blueprint.response(201, AccessTokenInfoCreateSchema())
    @api_blueprint.arguments(AccessTokenLabelSchema, location="json")
    def post(self, args, scope: str):
        """Create a new labelled token for the current user and scope."""
        scope, user_name = self._prepare(scope)
        label = args["label"].strip()
        if not label:
            abort_with_message(422, "Label must not be empty")
        try:
            access_token, token = create_user_access_token(user_name, scope, label)
        except AccessTokenConflictError as exc:
            abort_with_message(409, str(exc))
            raise  # unreachable
        return {**_access_token_info(access_token), "token": token}, 201


class UserAccessTokenItemResource(AccessTokenResourceBase):
    """Resource for one of the current user's labelled tokens of a scope."""

    multiple = True

    @api_blueprint.response(204)
    def delete(self, scope: str, token_id: int):
        """Revoke one of the current user's tokens for the scope."""
        scope, user_name = self._prepare(scope)
        if not delete_user_access_token(user_name, scope, token_id):
            abort_with_message(404, "Access token not found")
