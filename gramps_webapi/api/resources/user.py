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

from flask import abort, current_app
from flask_jwt_extended import get_jwt_identity
from webargs import fields
from webargs.flaskparser import use_args

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
