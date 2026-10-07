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

from flask import Response
from flask_jwt_extended import get_jwt_identity

from ...auth import (
    delete_user_push_subscription,
    upsert_user_push_subscription,
)
from ...auth.const import PERM_EDIT_OWN_USER
from ...webpush import get_web_push_config
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

    @api_blueprint.response(200, PushSubscriptionConfigSchema())
    def get(self):
        """Get the VAPID public key without exposing subscription endpoints."""
        require_permissions([PERM_EDIT_OWN_USER])
        config = get_web_push_config()
        return {"public_key": config[1] if config is not None else None}, 200

    @api_blueprint.response(201)
    @api_blueprint.arguments(PushSubscriptionBodySchema, location="json")
    def post(self, args):
        """Create or update the current browser's Web Push subscription."""
        require_permissions([PERM_EDIT_OWN_USER])
        if get_web_push_config() is None:
            abort_with_message(503, "Web Push is not configured")
        try:
            upsert_user_push_subscription(
                user_id=get_jwt_identity(),
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
        delete_user_push_subscription(get_jwt_identity(), args["endpoint"])
        return "", 204
