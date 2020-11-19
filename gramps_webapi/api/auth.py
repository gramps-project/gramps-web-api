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

"""API resource endpoints."""

from functools import wraps

from flask import current_app
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
