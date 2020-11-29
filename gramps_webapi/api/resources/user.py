#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""User administration resources."""

import datetime

from flask import abort, current_app
from flask_jwt_extended import create_access_token, get_jwt_claims, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from webargs import fields
from webargs.flaskparser import use_args

from . import ProtectedResource, Resource
from ..util import send_email


limiter = Limiter(key_func=get_remote_address)


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


def handle_reset_token(username: str, email: str, token: str):
    """Handle the password reset token."""
    send_email(
        subject="Password reset",
        body="{}, your token: {}".format(username, token),
        sender="from@example.com",
        recipients=[email],
    )


class UserTriggerResetPasswordResource(Resource):
    """Resource for obtaining a one-time JWT for password reset."""

    @limiter.limit("1/second")
    @use_args(
        {"username": fields.Str(required=True)}, location="json",
    )
    def post(self, args):
        """Post username to initiate the password reset."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        details = auth_provider.get_user_details(args["username"])
        if details is None:
            # user does not exist!
            abort(404)
        email = details["email"]
        if email is None:
            abort(404)
        token = create_access_token(
            identity=args["username"],
            # the hash of the existing password is stored in the token in order
            # to make sure the rest token can only be used once
            user_claims={"old_hash": auth_provider.get_pwhash(args["username"])},
            # password reset has to be triggered within 24h
            expires_delta=datetime.timedelta(days=1),
        )
        handle_reset_token(username=args["username"], email=email, token=token)
        return "", 201


class UserResetPasswordResource(ProtectedResource):
    """Resource for resetting a user password."""

    @use_args(
        {"new_password": fields.Str(required=True)}, location="json",
    )
    def post(self, args):
        """Post new password."""
        auth_provider = current_app.config.get("AUTH_PROVIDER")
        if auth_provider is None:
            abort(405)
        if len(args["new_password"]) == "":
            abort(400)
        claims = get_jwt_claims()
        username = get_jwt_identity()
        # the old PW hash is stored in the reset JWT to check if the token has
        # been used already
        if claims["old_hash"] != auth_provider.get_pwhash(username):
            # the one-time token has been used before!
            abort(409)
        auth_provider.modify_user(name=username, password=args["new_password"])
        return "", 201
