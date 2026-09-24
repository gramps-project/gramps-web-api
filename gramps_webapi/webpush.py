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
from typing import Any, Mapping

from flask import current_app
from pywebpush import WebPushException, webpush

from .auth import PushSubscription, user_db


def _web_push_config():
    public_key = current_app.config.get("WEB_PUSH_VAPID_PUBLIC_KEY", "")
    private_key = current_app.config.get("WEB_PUSH_VAPID_PRIVATE_KEY", "")
    subject = current_app.config.get("WEB_PUSH_VAPID_SUBJECT", "")
    if not public_key or not private_key or not subject:
        return None
    return private_key, subject


def send_web_push(
    user_id,
    payload: Mapping[str, Any],
) -> None:
    """Send a JSON notification to every subscription owned by a user.

    Endpoints rejected with HTTP 404 or 410 are removed. Transient failures
    are retained for a later retry.
    """
    config = _web_push_config()
    if config is None:
        current_app.logger.warning("Web Push delivery skipped: VAPID is not configured")
        return
    private_key, subject = config
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    subscriptions = (
        user_db.session.query(PushSubscription)  # pylint: disable=no-member
        .filter_by(user_id=user_id)
        .all()
    )
    removed = 0
    for subscription in subscriptions:
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
            )
        except WebPushException as exc:
            if exc.status_code in (404, 410):
                user_db.session.delete(subscription)  # pylint: disable=no-member
                removed += 1
            else:
                current_app.logger.warning(
                    "Web Push delivery failed with status %s", exc.status_code
                )
        except Exception as exc:  # pragma: no cover - provider/library boundary
            current_app.logger.warning(
                "Web Push delivery failed: %s", type(exc).__name__
            )
    if removed:
        user_db.session.commit()  # pylint: disable=no-member
