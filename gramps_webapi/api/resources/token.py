"""Authentication endpoint blueprint."""

from flask import current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_restful import Resource, abort, reqparse

from . import RefreshProtectedResource

limiter = Limiter(key_func=get_remote_address)


class TokenResource(Resource):
    """Resource for obtaining a JWT."""

    @limiter.limit("1/second")
    def post(self):
        """Post username and password to fetch a token."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            return self.get_dummy_tokens()
        args = self.parser.parse_args()
        if not auth_provider.authorized(args["username"], args["password"]):
            abort(403)
        return self.get_tokens(args["username"])

    @staticmethod
    def get_dummy_tokens():
        """Return dummy access and refresh token."""
        return {"access_token": 1, "refresh_token": 1}

    @staticmethod
    def get_tokens(username: str):
        """Create an access and refresh token."""
        return {
            "access_token": create_access_token(identity=username),
            "refresh_token": create_refresh_token(identity=username),
        }

    @property
    def parser(self):
        """Request argument parser."""
        parser = reqparse.RequestParser()
        parser.add_argument("username", type=str, help="Username", required=True)
        parser.add_argument("password", type=str, help="Password", required=True)
        return parser


class TokenRefreshResource(RefreshProtectedResource):
    """Resource for refreshing a JWT."""

    @limiter.limit("1/second")
    def post(self):
        """Fetch a fresh token."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            return self.get_dummy_token()
        username = get_jwt_identity()
        return self.get_token(username)

    @staticmethod
    def get_dummy_token():
        """Return dummy access token."""
        return {"access_token": 1}

    @staticmethod
    def get_token(username: str):
        """Create an access token."""
        return {"access_token": create_access_token(identity=username)}
