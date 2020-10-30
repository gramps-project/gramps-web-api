"""API resource endpoints."""

from flask.views import MethodView

from ..auth import jwt_refresh_token_required_ifauth, jwt_required_ifauth


class Resource(MethodView):
    """Base class for API resources."""


class ProtectedResource(Resource):
    """Resource requiring JWT authentication."""

    decorators = [jwt_required_ifauth]


class RefreshProtectedResource(Resource):
    """Resource requiring a JWT refresh token."""

    decorators = [jwt_refresh_token_required_ifauth]
