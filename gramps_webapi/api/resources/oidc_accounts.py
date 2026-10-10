#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Resources for the current user's own OIDC accounts."""

from flask import current_app
from flask_jwt_extended import get_jwt_identity

from ...auth import (
    UNLINK_LAST,
    UNLINK_NOT_FOUND,
    authorized,
    get_name,
    get_user_oidc_accounts,
    unlink_oidc_account,
)
from ...auth.oidc_helpers import is_oidc_enabled
from ..blueprint import api_blueprint
from ..ratelimiter import limiter
from ..util import abort_with_message
from . import FreshProtectedResource, ProtectedResource
from .schemas import UserOIDCAccountSchema, UserOIDCUnlinkSchema


class UserOIDCAccountsResource(ProtectedResource):
    """The current user's OIDC accounts."""

    @api_blueprint.response(200, UserOIDCAccountSchema(many=True))
    def get(self):
        """List the current user's OIDC accounts."""
        return get_user_oidc_accounts(get_jwt_identity())


class UserOIDCAccountResource(FreshProtectedResource):
    """One of the current user's OIDC accounts."""

    @api_blueprint.response(204)
    @api_blueprint.arguments(UserOIDCUnlinkSchema, location="json")
    @limiter.limit("5/minute")
    def delete(self, args, account_id: int):
        """Unlink one of the current user's OIDC accounts.

        Unlinking the last one needs the user's current password, so that they
        can still log in, and is refused if local authentication is disabled.
        """
        user_id = get_jwt_identity()
        local_auth_disabled = is_oidc_enabled() and current_app.config.get(
            "OIDC_DISABLE_LOCAL_AUTH", False
        )
        password = args["password"]
        # users created through OIDC have a random password they don't know
        allow_last = (
            not local_auth_disabled
            and bool(password)
            and authorized(get_name(user_id), password)
        )
        result = unlink_oidc_account(user_id, account_id, allow_last=allow_last)
        if result == UNLINK_NOT_FOUND:
            abort_with_message(404, "OIDC account not found")
        if result == UNLINK_LAST:
            if local_auth_disabled:
                abort_with_message(
                    409,
                    "The last OIDC account can't be unlinked while local"
                    " authentication is disabled",
                )
            abort_with_message(
                403, "The current password is required to unlink the last OIDC account"
            )
        return "", 204
