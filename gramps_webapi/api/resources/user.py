"""User administration resources."""

from flask import abort, current_app
from webargs import fields
from webargs.flaskparser import use_args
from flask_jwt_extended import get_jwt_identity

from . import ProtectedResource


class UserChangePasswordResource(ProtectedResource):
    """Resource for changing a user password."""

    @use_args(
        {
            "old_password": fields.Str(required=True),
            "new_password": fields.Str(required=True),
        },
        location="json",
    )
    def post(self, args):
        """Post new password."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        if len(args["new_password"]) == "":
            abort(400)
        username = get_jwt_identity()
        if not auth_provider.authorized(username, args["old_password"]):
            abort(403)
        auth_provider.modify_user(name=username, password=args["new_password"])
        return "", 201
