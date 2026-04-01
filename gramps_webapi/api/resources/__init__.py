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

"""API resource endpoints."""

import typing as t

from flask import abort, current_app, request
from flask.views import MethodView

from ..auth import (
    fresh_jwt_required,
    jwt_limited_scope_required,
    jwt_refresh_token_required,
    jwt_required,
)
from gramps_webapi.types import ResponseReturnValue


class Resource(MethodView):
    """Base class for API resources."""

    def dispatch_request(self, /, *args: t.Any, **kwargs: t.Any) -> ResponseReturnValue:
        """Dispatch to the appropriate method handler, returning 405 for undefined methods.

        Flask 3.x MethodView raises AssertionError for undefined methods; we
        override to return a proper 405 response so that routes registered with
        all HTTP methods (needed for correct 405 vs 404 routing) behave correctly.
        """
        meth = getattr(self, request.method.lower(), None)
        if meth is None and request.method == "HEAD":
            meth = getattr(self, "get", None)
        if meth is None:
            abort(405)
        return current_app.ensure_sync(meth)(*args, **kwargs)


class ProtectedResource(Resource):
    """Resource requiring JWT authentication."""

    decorators = [jwt_required]


class FreshProtectedResource(Resource):
    """Resource requiring a fresh JWT token."""

    decorators = [fresh_jwt_required]


class RefreshProtectedResource(Resource):
    """Resource requiring a JWT refresh token."""

    decorators = [jwt_refresh_token_required]


class LimitedScopeProtectedResource(Resource):
    """Resource requiring JWT authentication with limited scope."""

    decorators = [jwt_limited_scope_required]
