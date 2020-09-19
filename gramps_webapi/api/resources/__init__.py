"""API resource endpoints."""

from functools import wraps

from flask import current_app
from flask_restful import Resource
from flask_jwt_extended import (
    verify_jwt_in_request,
    verify_jwt_refresh_token_in_request,
)


def jwt_required_ifauth(func):
    """Check JWT unless authentication is disabled."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("DISABLE_AUTH"):
            verify_jwt_in_request()
        return func(*args, **kwargs)

    return wrapper


def jwt_refresh_token_required_ifauth(func):
    """Check JWT unless authentication is disabled."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("DISABLE_AUTH"):
            verify_jwt_refresh_token_in_request()
        return func(*args, **kwargs)

    return wrapper


class ProtectedResource(Resource):
    """Resource requiring JWT authentication."""

    method_decorators = [jwt_required_ifauth]


class RefreshProtectedResource(Resource):
    """Resource requiring a JWT refresh token."""

    method_decorators = [jwt_refresh_token_required_ifauth]
