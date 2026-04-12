"""Optional telemetry for Gramps Web API."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid

import requests
from flask import current_app

from gramps_webapi.api.cache import persistent_cache
from gramps_webapi.const import (
    TELEMETRY_ENDPOINT,
    TELEMETRY_SERVER_ID_KEY,
    TELEMETRY_TIMESTAMP_KEY,
)

_LOG = logging.getLogger(__name__)

_last_sent: float = 0.0


def send_telemetry(data: dict[str, str | int | float]) -> None:
    """Send telemetry, logging any network or HTTP errors."""
    try:
        response = requests.post(TELEMETRY_ENDPOINT, json=data, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _LOG.warning("Failed to send telemetry: %s", exc)


def telemetry_sent_last_24h() -> bool:
    """Check if telemetry has been sent in the last 24 hours."""
    global _last_sent
    now = time.time()
    if now - _last_sent < 24 * 60 * 60:
        return True
    # Fall back to persistent cache (handles worker restarts and fresh deploys).
    _last_sent = telemetry_last_sent()
    return now - _last_sent < 24 * 60 * 60


def should_send_telemetry() -> bool:
    """Whether telemetry should be sent."""
    if current_app.config.get("DISABLE_TELEMETRY"):
        return False
    if os.getenv("FLASK_RUN_FROM_CLI"):
        # Flask development server, not a production environment (hopefully!)
        return False
    if (os.environ.get("PYTEST_CURRENT_TEST") or current_app.testing) and not os.getenv(
        "MOCK_TELEMETRY"
    ):
        # do not send telemetry during tests unless MOCK_TELEMETRY is set
        return False
    # only send telemetry if it has not been sent in the last 24 hours
    if telemetry_sent_last_24h():
        return False
    return True


def telemetry_last_sent() -> float:
    """Timestamp when telemetry was last sent successfully."""
    return persistent_cache.get(TELEMETRY_TIMESTAMP_KEY) or 0.0


def update_telemetry_timestamp() -> None:
    """Update the telemetry timestamp."""
    global _last_sent
    _last_sent = time.time()
    persistent_cache.set(TELEMETRY_TIMESTAMP_KEY, _last_sent)


def generate_server_uuid() -> str:
    """Generate a random, unique server UUID."""
    return uuid.uuid4().hex


def get_server_uuid() -> str:
    """Return the persistent server UUID, creating and storing it if absent.

    Performs a re-read after write so that concurrent workers that race on
    first startup all converge to the same stored value rather than each
    using a locally-generated UUID that differs from what ended up in cache.
    """
    server_uuid = persistent_cache.get(TELEMETRY_SERVER_ID_KEY)
    if not server_uuid:
        persistent_cache.set(TELEMETRY_SERVER_ID_KEY, generate_server_uuid())
        # Re-read: if two workers raced, both will now see the winner's value.
        server_uuid = persistent_cache.get(TELEMETRY_SERVER_ID_KEY)
        if not server_uuid:
            # Cache is unavailable (e.g. NullCache); generate an ephemeral UUID.
            server_uuid = generate_server_uuid()
    return server_uuid


def generate_tree_uuid(tree_id: str, server_uuid: str) -> str:
    """Generate a pseudonymous tree UUID.

    The UUID is deterministic for a given (tree_id, server_uuid) pair but
    does not allow reconstructing the tree_id.
    """
    return hmac.new(
        server_uuid.encode(), tree_id.encode(), hashlib.sha256
    ).hexdigest()


def get_telemetry_payload(tree_id: str) -> dict[str, str | int | float]:
    """Get the telemetry payload for the given tree ID."""
    if not tree_id:
        raise ValueError("Tree ID must not be empty")
    server_uuid = get_server_uuid()
    tree_uuid = generate_tree_uuid(tree_id=tree_id, server_uuid=server_uuid)
    return {
        "server_uuid": server_uuid,
        "tree_uuid": tree_uuid,
        "timestamp": time.time(),
    }
