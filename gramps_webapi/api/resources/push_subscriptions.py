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

import base64
import binascii
import ipaddress
import time
from urllib.parse import urlsplit

from flask import current_app
from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema, ValidationError, validate
from webargs import fields

from ...auth import (
    delete_user_push_subscription,
    get_name,
    get_user_push_subscription_count,
    upsert_user_push_subscription,
)
from ...auth.const import PERM_EDIT_OWN_USER
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import abort_with_message
from . import ProtectedResource


def _validate_push_endpoint(value: str) -> str:
    """Validate a browser-provided push endpoint without contacting it."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValidationError("Invalid Web Push endpoint")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValidationError("Invalid Web Push endpoint")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValidationError("Invalid Web Push endpoint")
    return value


def _push_key_validator(expected_bytes: int, prefix: bytes | None = None):
    """Return a validator for a URL-safe base64 Web Push key."""

    def validate_key(value: str) -> str:
        try:
            padding = "=" * (-len(value) % 4)
            decoded = base64.b64decode(
                value + padding,
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, ValueError) as exc:
            raise ValidationError("Invalid Web Push key") from exc
        if len(decoded) != expected_bytes or (
            prefix is not None and not decoded.startswith(prefix)
        ):
            raise ValidationError("Invalid Web Push key")
        return value

    return validate_key


class PushSubscriptionKeysSchema(Schema):
    """Encryption keys from ``PushSubscription.toJSON()``."""

    p256dh = fields.Str(required=True, validate=_push_key_validator(65, b"\x04"))
    auth = fields.Str(required=True, validate=_push_key_validator(16))


class PushSubscriptionBodySchema(Schema):
    """Browser Web Push subscription payload."""

    endpoint = fields.Str(
        required=True,
        validate=[validate.Length(min=1, max=4096), _validate_push_endpoint],
    )
    expiration_time = fields.Int(
        required=False,
        allow_none=True,
        load_default=None,
        data_key="expirationTime",
        validate=validate.Range(min=0),
    )
    keys = fields.Nested(PushSubscriptionKeysSchema, required=True)


class PushSubscriptionDeleteSchema(Schema):
    """Payload identifying the current browser subscription to delete."""

    endpoint = fields.Str(
        required=True,
        validate=[validate.Length(min=1, max=4096), _validate_push_endpoint],
    )


class PushSubscriptionStatusSchema(Schema):
    """Web Push availability and current-user subscription count."""

    available = fields.Boolean(required=True)
    public_key = fields.Str(required=False, allow_none=True)
    subscriptions = fields.Int(required=True)


class UserPushSubscriptionsResource(ProtectedResource):
    """Manage browser subscriptions owned by the current user."""

    def _get_user_name(self) -> str:
        user_id = get_jwt_identity()
        try:
            return get_name(user_id)
        except ValueError:
            abort_with_message(401, "User not found for token ID")
            raise  # unreachable

    def _config(self):
        public_key = current_app.config.get("WEB_PUSH_VAPID_PUBLIC_KEY", "")
        private_key = current_app.config.get("WEB_PUSH_VAPID_PRIVATE_KEY", "")
        subject = current_app.config.get("WEB_PUSH_VAPID_SUBJECT", "")
        available = bool(public_key and private_key and subject)
        if available:
            try:
                _push_key_validator(65, b"\x04")(public_key)
            except ValidationError:
                available = False
        return available, public_key if available else None

    def _status(self, user_name: str):
        available, public_key = self._config()
        return {
            "available": available,
            "public_key": public_key,
            "subscriptions": get_user_push_subscription_count(user_name),
        }

    @api_blueprint.response(200, PushSubscriptionStatusSchema())
    def get(self):
        """Get Web Push availability without exposing subscription endpoints."""
        require_permissions([PERM_EDIT_OWN_USER])
        return self._status(self._get_user_name()), 200

    @api_blueprint.response(200, PushSubscriptionStatusSchema())
    @api_blueprint.arguments(PushSubscriptionBodySchema, location="json")
    def post(self, args):
        """Create or update the current browser's Web Push subscription."""
        require_permissions([PERM_EDIT_OWN_USER])
        available, _ = self._config()
        if not available:
            abort_with_message(503, "Web Push is not configured")
        expiration_time = args["expiration_time"]
        if expiration_time is not None and expiration_time <= int(time.time() * 1000):
            abort_with_message(422, "Web Push subscription has expired")
        user_name = self._get_user_name()
        try:
            upsert_user_push_subscription(
                username=user_name,
                endpoint=args["endpoint"],
                p256dh=args["keys"]["p256dh"],
                auth=args["keys"]["auth"],
                expiration_time=expiration_time,
                max_subscriptions=int(
                    current_app.config["WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER"]
                ),
            )
        except ValueError as exc:
            abort_with_message(409, str(exc))
        return self._status(user_name), 200

    @api_blueprint.response(200, PushSubscriptionStatusSchema())
    @api_blueprint.arguments(PushSubscriptionDeleteSchema, location="json")
    def delete(self, args):
        """Delete the current browser's Web Push subscription."""
        require_permissions([PERM_EDIT_OWN_USER])
        user_name = self._get_user_name()
        delete_user_push_subscription(user_name, args["endpoint"])
        return self._status(user_name), 200
