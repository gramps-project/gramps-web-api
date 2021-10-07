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

"""User administration resources."""

import datetime
from gettext import gettext as _

from flask import abort, current_app, jsonify, render_template
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from webargs import fields

from ...auth.const import (
    CLAIM_LIMITED_SCOPE,
    PERM_ADD_USER,
    PERM_DEL_USER,
    PERM_EDIT_OTHER_USER,
    PERM_EDIT_OWN_USER,
    PERM_EDIT_USER_ROLE,
    PERM_VIEW_OTHER_USER,
    ROLE_DISABLED,
    ROLE_UNCONFIRMED,
    SCOPE_CONF_EMAIL,
    SCOPE_RESET_PW,
)
from ..auth import require_permissions
from ..tasks import (
    send_email_confirm_email,
    send_email_new_user,
    send_email_reset_password,
)
from ..util import use_args
from . import LimitedScopeProtectedResource, ProtectedResource, Resource

limiter = Limiter(key_func=get_remote_address)


class UserChangeBase(ProtectedResource):
    """Base class for user change endpoints."""

    def prepare_edit(self, user_name: str):
        """Cheks to do before processing the request."""
        if user_name == "-":
            require_permissions([PERM_EDIT_OWN_USER])
            user_name = get_jwt_identity()
        else:
            require_permissions([PERM_EDIT_OTHER_USER])
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        return auth_provider, user_name


class UsersResource(ProtectedResource):
    """Resource for all users."""

    def get(self):
        """Get users' details."""
        require_permissions([PERM_VIEW_OTHER_USER])
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        return jsonify(auth_provider.get_all_user_details()), 200


class UserResource(UserChangeBase):
    """Resource for a single user."""

    def get(self, user_name: str):
        """Get a user's details."""
        if user_name == "-":
            user_name = get_jwt_identity()
        else:
            require_permissions([PERM_VIEW_OTHER_USER])
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        details = auth_provider.get_user_details(user_name)
        if details is None:
            # user does not exist
            abort(404)
        return jsonify(details), 200

    @use_args(
        {
            "email": fields.Str(required=False),
            "full_name": fields.Str(required=False),
            "role": fields.Int(required=False),
        },
        location="json",
    )
    def put(self, args, user_name: str):
        """Update a user's details."""
        auth_provider, user_name = self.prepare_edit(user_name)
        if "role" in args:
            require_permissions([PERM_EDIT_USER_ROLE])
        auth_provider.modify_user(
            name=user_name,
            email=args.get("email"),
            fullname=args.get("full_name"),
            role=args.get("role"),
        )
        return "", 200

    @use_args(
        {
            "email": fields.Str(required=True),
            "full_name": fields.Str(required=True),
            "password": fields.Str(required=True),
            "role": fields.Int(required=True),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Add a new user."""
        if user_name == "-":
            # Adding a new user does not make sense for "own" user
            abort(404)
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        require_permissions([PERM_ADD_USER])
        try:
            auth_provider.add_user(
                name=user_name,
                password=args["password"],
                email=args["email"],
                fullname=args["full_name"],
                role=args["role"],
            )
        except ValueError:
            abort(409)
        return "", 201

    def delete(self, user_name: str):
        """Delete a user."""
        if user_name == "-":
            # Deleting the own user is currently not allowed
            abort(404)
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        require_permissions([PERM_DEL_USER])
        try:
            auth_provider.delete_user(name=user_name)
        except ValueError:
            abort(404)  # user not found
        return "", 200


class UserRegisterResource(Resource):
    """Resource for registering a new user."""

    @limiter.limit("1/second")
    @use_args(
        {
            "email": fields.Str(required=True),
            "full_name": fields.Str(required=True),
            "password": fields.Str(required=True),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Register a new user."""
        if user_name == "-":
            # Registering a new user does not make sense for "own" user
            abort(404)
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        try:
            auth_provider.add_user(
                name=user_name,
                password=args["password"],
                email=args["email"],
                fullname=args["full_name"],
                role=ROLE_UNCONFIRMED,
            )
        except ValueError:
            abort(409)
        token = create_access_token(
            identity=user_name,
            additional_claims={
                "email": args["email"],
                CLAIM_LIMITED_SCOPE: SCOPE_CONF_EMAIL,
            },
            # email has to be confirmed within 1h
            expires_delta=datetime.timedelta(hours=1),
        )
        send_email_confirm_email(email=args["email"], token=token)
        return "", 201


class UserChangePasswordResource(UserChangeBase):
    """Resource for changing a user password."""

    @use_args(
        {
            "old_password": fields.Str(required=True),
            "new_password": fields.Str(required=True),
        },
        location="json",
    )
    def post(self, args, user_name: str):
        """Post new password."""
        auth_provider, user_name = self.prepare_edit(user_name)
        if len(args["new_password"]) == "":
            abort(400)
        if not auth_provider.authorized(user_name, args["old_password"]):
            abort(403)
        auth_provider.modify_user(name=user_name, password=args["new_password"])
        return "", 201


class UserTriggerResetPasswordResource(Resource):
    """Resource for obtaining a one-time JWT for password reset."""

    @limiter.limit("1/second")
    def post(self, user_name):
        """Post username to initiate the password reset."""
        if user_name == "-":
            # password reset trigger not make sense for "own" user since not logged in
            abort(404)
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        details = auth_provider.get_user_details(user_name)
        if details is None:
            # user does not exist!
            abort(404)
        email = details["email"]
        if email is None:
            abort(404)
        token = create_access_token(
            identity=user_name,
            # the hash of the existing password is stored in the token in order
            # to make sure the rest token can only be used once
            additional_claims={
                "old_hash": auth_provider.get_pwhash(user_name),
                CLAIM_LIMITED_SCOPE: SCOPE_RESET_PW,
            },
            # password reset has to be triggered within 1h
            expires_delta=datetime.timedelta(hours=1),
        )
        try:
            send_email_reset_password(email=email, token=token)
        except ValueError:
            abort(500)
        return "", 201


class UserResetPasswordResource(LimitedScopeProtectedResource):
    """Resource for resetting a user password."""

    @use_args(
        {"new_password": fields.Str(required=True)}, location="json",
    )
    def post(self, args):
        """Post new password."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        if args["new_password"] == "":
            abort(400)
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_RESET_PW:
            # This is a wrong token!
            abort(403)
        username = get_jwt_identity()
        # the old PW hash is stored in the reset JWT to check if the token has
        # been used already
        if claims["old_hash"] != auth_provider.get_pwhash(username):
            # the one-time token has been used before!
            abort(409)
        auth_provider.modify_user(name=username, password=args["new_password"])
        return "", 201

    def get(self):
        """Reset password form."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        username = get_jwt_identity()
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_RESET_PW:
            # This is a wrong token!
            abort(403)
        # the old PW hash is stored in the reset JWT to check if the token has
        # been used already
        if claims["old_hash"] != auth_provider.get_pwhash(username):
            # the one-time token has been used before!
            return render_template("reset_password_error.html", username=username)
        return render_template("reset_password.html", username=username)


class UserConfirmEmailResource(LimitedScopeProtectedResource):
    """Resource for confirming an email address."""

    def get(self):
        """Show email confirmation dialog."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        username = get_jwt_identity()
        claims = get_jwt()
        if claims[CLAIM_LIMITED_SCOPE] != SCOPE_CONF_EMAIL:
            # This is a wrong token!
            abort(403)
        current_details = auth_provider.get_user_details(username)
        # the email is stored in the JWT
        if claims["email"] != current_details.get("email"):
            # This is a wrong token!
            abort(403)
        if current_details["role"] == ROLE_UNCONFIRMED:
            # otherwise it has been confirmed already
            auth_provider.modify_user(name=username, role=ROLE_DISABLED)
            send_email_new_user(
                username=username,
                fullname=current_details.get("full_name", ""),
                email=claims["email"],
            )
        title = _("E-mail address confirmation")
        message = _("Thank you for confirming your e-mail address.")
        return render_template("confirmation.html", title=title, message=message)
