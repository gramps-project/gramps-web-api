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

"""Reusable Web Push delivery helpers."""

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from flask import current_app
from pywebpush import WebPushException, webpush

from .auth import PushSubscription, User, user_db


class WebPushNotConfiguredError(RuntimeError):
    """Raised when Web Push delivery is attempted without VAPID settings."""


@dataclass(frozen=True)
class WebPushDeliveryResult:
    """Aggregate result for one user's subscriptions."""

    sent: int = 0
    failed: int = 0
    removed: int = 0


def _web_push_config():
    public_key = current_app.config.get("WEB_PUSH_VAPID_PUBLIC_KEY", "")
    private_key = current_app.config.get("WEB_PUSH_VAPID_PRIVATE_KEY", "")
    subject = current_app.config.get("WEB_PUSH_VAPID_SUBJECT", "")
    if not public_key or not private_key or not subject:
        raise WebPushNotConfiguredError("Web Push is not configured")
    return private_key, subject


def send_web_push(
    user_id,
    payload: Mapping[str, Any],
    *,
    ttl: int | None = None,
) -> WebPushDeliveryResult:
    """Send a JSON notification to every subscription owned by a user.

    Permanently expired subscriptions and endpoints rejected with HTTP 404 or
    410 are removed. Transient failures are retained for a later retry.
    """
    private_key, subject = _web_push_config()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    max_payload_bytes = int(current_app.config["WEB_PUSH_MAX_PAYLOAD_BYTES"])
    if len(data.encode("utf-8")) > max_payload_bytes:
        raise ValueError("Web Push payload is too large")

    subscriptions = (
        user_db.session.query(PushSubscription)  # pylint: disable=no-member
        .filter_by(user_id=user_id)
        .all()
    )
    now_ms = int(time.time() * 1000)
    sent = 0
    failed = 0
    removed = 0
    for subscription in subscriptions:
        if (
            subscription.expiration_time is not None
            and subscription.expiration_time <= now_ms
        ):
            user_db.session.delete(subscription)  # pylint: disable=no-member
            removed += 1
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=data,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=ttl if ttl is not None else current_app.config["WEB_PUSH_TTL"],
                timeout=current_app.config["WEB_PUSH_TIMEOUT"],
            )
            sent += 1
        except WebPushException as exc:
            if exc.status_code in (404, 410):
                user_db.session.delete(subscription)  # pylint: disable=no-member
                removed += 1
            else:
                failed += 1
                current_app.logger.warning(
                    "Web Push delivery failed with status %s", exc.status_code
                )
        except Exception as exc:  # pragma: no cover - provider/library boundary
            failed += 1
            current_app.logger.warning(
                "Web Push delivery failed: %s", type(exc).__name__
            )
    if removed:
        user_db.session.commit()  # pylint: disable=no-member
    return WebPushDeliveryResult(sent=sent, failed=failed, removed=removed)


def send_web_push_to_user(
    username: str,
    payload: Mapping[str, Any],
    *,
    ttl: int | None = None,
) -> WebPushDeliveryResult:
    """Send a JSON notification to all subscriptions for a username."""
    user = (
        user_db.session.query(User)  # pylint: disable=no-member
        .filter_by(name=username)
        .scalar()
    )
    if user is None:
        raise ValueError("User does not exist")
    return send_web_push(user.id, payload, ttl=ttl)
