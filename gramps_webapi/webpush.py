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

import base64
import json
from functools import lru_cache
from typing import Any, Mapping
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from .auth import PushSubscription, user_db

WEB_PUSH_TIMEOUT_SECONDS = 10
WEB_PUSH_TTL_SECONDS = 24 * 60 * 60
VAPID_KEY_CONTEXT = b"gramps-web-api:webpush:vapid:v1"


@lru_cache(maxsize=1)
def _derive_vapid_key(secret_key: bytes) -> tuple[Vapid, str]:
    """Derive a stable, separate signing key; secret rotation requires resubscription."""
    curve = ec.SECP256R1()
    material = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=VAPID_KEY_CONTEXT,
    ).derive(secret_key)
    private_value = int.from_bytes(material, "big") % (curve.group_order - 1) + 1
    private_key = ec.derive_private_key(private_value, curve)
    public_key = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    # The contact URI is validated below. py-vapid's stricter regex rejects
    # otherwise valid HTTPS origins with a port.
    return Vapid(private_key, conf={"no-strict": True}), public_key


def get_web_push_config() -> tuple[Vapid, str, str] | None:
    """Return VAPID credentials from the existing secret and HTTPS base URL."""
    secret_key = current_app.config.get("SECRET_KEY")
    base_url = current_app.config.get("BASE_URL")
    if not secret_key or not isinstance(secret_key, (str, bytes)):
        return None
    if not isinstance(base_url, str):
        return None
    try:
        url = urlsplit(base_url)
    except ValueError:
        return None
    if url.scheme != "https" or not url.hostname:
        return None
    secret = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    vapid, public_key = _derive_vapid_key(secret)
    return vapid, public_key, f"https://{url.netloc}"


def send_web_push(
    user_id,
    payload: Mapping[str, Any],
) -> None:
    """Send a JSON notification to every subscription owned by a user.

    Endpoints rejected with HTTP 401, 403, 404, or 410 are removed. Transient
    failures are retained for a later retry.
    """
    config = get_web_push_config()
    if config is None:
        current_app.logger.warning("Web Push delivery skipped: VAPID is not configured")
        return
    vapid, _, subject = config
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
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                ttl=WEB_PUSH_TTL_SECONDS,
                timeout=WEB_PUSH_TIMEOUT_SECONDS,
            )
        except WebPushException as exc:
            if exc.status_code in (401, 403, 404, 410):
                user_db.session.delete(subscription)  # pylint: disable=no-member
                removed += 1
            else:
                current_app.logger.warning(
                    "Web Push delivery failed with status %s", exc.status_code
                )
        except Exception as exc:
            current_app.logger.warning(
                "Web Push delivery failed: %s", type(exc).__name__
            )
    if removed:
        user_db.session.commit()  # pylint: disable=no-member
