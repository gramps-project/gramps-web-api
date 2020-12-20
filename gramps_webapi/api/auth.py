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
from typing import Iterable

from flask import abort, current_app
from flask_jwt_extended import (
    get_jwt_claims,
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


def has_permissions(scope: Iterable[str]) -> bool:
    """Check a set of permissions and return False if any are missing."""
    if current_app.config.get("DISABLE_AUTH"):
        return True
    claims = get_jwt_claims()
    user_permissions = set(claims.get("permissions", []))
    required_permissions = set(scope)
    missing_permissions = required_permissions - user_permissions
    if missing_permissions:
        return False
    return True


def require_permissions(scope: Iterable[str]) -> None:
    """Require a set of permissions or fail with a 403."""
    if not has_permissions(scope):
        abort(403)
