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

"""Resources for managing the current user's Web Push subscriptions."""

from flask import Response, current_app
from flask_jwt_extended import get_jwt_identity

from ...auth import (
    delete_user_push_subscription,
    get_name,
    upsert_user_push_subscription,
)
from ...auth.const import PERM_EDIT_OWN_USER
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import abort_with_message
from . import ProtectedResource
from .schemas import (
    PushSubscriptionBodySchema,
    PushSubscriptionConfigSchema,
    PushSubscriptionDeleteSchema,
)


class UserPushSubscriptionsResource(ProtectedResource):
    """Manage browser subscriptions owned by the current user."""

    def _get_user_name(self) -> str:
        user_id = get_jwt_identity()
        try:
            return get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
            raise  # unreachable

    def _public_key(self):
        public_key = current_app.config.get("WEB_PUSH_VAPID_PUBLIC_KEY", "")
        private_key = current_app.config.get("WEB_PUSH_VAPID_PRIVATE_KEY", "")
        subject = current_app.config.get("WEB_PUSH_VAPID_SUBJECT", "")
        if not public_key or not private_key or not subject:
            return None
        return public_key

    @api_blueprint.response(200, PushSubscriptionConfigSchema())
    def get(self):
        """Get the VAPID public key without exposing subscription endpoints."""
        require_permissions([PERM_EDIT_OWN_USER])
        return {"public_key": self._public_key()}, 200

    @api_blueprint.response(201)
    @api_blueprint.arguments(PushSubscriptionBodySchema, location="json")
    def post(self, args):
        """Create or update the current browser's Web Push subscription."""
        require_permissions([PERM_EDIT_OWN_USER])
        if self._public_key() is None:
            abort_with_message(503, "Web Push is not configured")
        user_name = self._get_user_name()
        try:
            upsert_user_push_subscription(
                username=user_name,
                endpoint=args["endpoint"],
                p256dh=args["keys"]["p256dh"],
                auth=args["keys"]["auth"],
            )
        except ValueError as exc:
            abort_with_message(409, str(exc))
        return Response(status=201)

    @api_blueprint.response(204)
    @api_blueprint.arguments(PushSubscriptionDeleteSchema, location="json")
    def delete(self, args):
        """Delete the current browser's Web Push subscription."""
        require_permissions([PERM_EDIT_OWN_USER])
        delete_user_push_subscription(self._get_user_name(), args["endpoint"])
        return "", 204
