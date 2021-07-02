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

from typing import Iterable

from flask import abort, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from webargs import fields, validate

from ..util import use_args
from . import RefreshProtectedResource, Resource

limiter = Limiter(key_func=get_remote_address)


def get_tokens(
    username: str, permissions: Iterable[str], include_refresh: bool = False
):
    """Create access token (and refresh token if desired)."""
    access_token = create_access_token(
        identity=username, additional_claims={"permissions": list(permissions)}
    )
    if not include_refresh:
        return {"access_token": access_token}
    refresh_token = create_refresh_token(identity=username)
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
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            return self.get_dummy_tokens()
        if "username" not in args or "password" not in args:
            abort(401)
        if not auth_provider.authorized(args.get("username"), args.get("password")):
            abort(403)
        permissions = auth_provider.get_permissions(args["username"])
        return get_tokens(
            username=args["username"], permissions=permissions, include_refresh=True
        )

    @staticmethod
    def get_dummy_tokens():
        """Return dummy access and refresh token."""
        return {"access_token": 1, "refresh_token": 1}


class TokenRefreshResource(RefreshProtectedResource):
    """Resource for refreshing a JWT."""

    @limiter.limit("1/second")
    def post(self):
        """Fetch a fresh token."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            return self.get_dummy_token()
        username = get_jwt_identity()
        permissions = auth_provider.get_permissions(username)
        return get_tokens(
            username=username, permissions=permissions, include_refresh=False
        )

    @staticmethod
    def get_dummy_token():
        """Return dummy access token."""
        return {"access_token": 1}
