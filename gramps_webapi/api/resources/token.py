"""Authentication endpoint blueprint."""

from flask import abort, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from webargs import fields
from webargs.flaskparser import use_args

from . import RefreshProtectedResource, Resource

limiter = Limiter(key_func=get_remote_address)


class TokenResource(Resource):
    """Resource for obtaining a JWT."""

    @limiter.limit("1/second")
    @use_args(
        {"username": fields.Str(), "password": fields.Str()}, location="json",
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
