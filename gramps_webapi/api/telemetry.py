"""Optional telemetry for Gramps Web API."""

from __future__ import annotations

import os
import time
import uuid

import requests
from flask import current_app

from gramps_webapi.api.cache import persistent_cache
from gramps_webapi.auth.passwords import hash_password_salt
from gramps_webapi.const import (
    TELEMETRY_ENDPOINT,
    TELEMETRY_SERVER_ID_KEY,
    TELEMETRY_TIMESTAMP_KEY,
)


def send_telemetry(data: dict[str, str | int | float]) -> None:
    """Send telemetry"""
    response = requests.post(TELEMETRY_ENDPOINT, json=data, timeout=30)
    response.raise_for_status()  # Raise exception for HTTP errors


def telemetry_sent_last_24h() -> bool:
    """Check if telemetry has been sent in the last 24 hours."""
    return time.time() - telemetry_last_sent() < 24 * 60 * 60


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
    persistent_cache.set(TELEMETRY_TIMESTAMP_KEY, time.time())


def generate_server_uuid() -> str:
    """Generate a random, unique server UUID."""
    return uuid.uuid4().hex


def generate_tree_uuid(tree_id: str, server_uuid: str) -> str:
    """Generate a unique tree UUID for the given tree ID and server UUID.

    The tree UUID is uniquely determined for a given tree ID and server
    UUID but does not allow reconstructing the tree ID.
    """
    return hash_password_salt(password=tree_id, salt=server_uuid.encode()).hex()


def get_telemetry_payload(tree_id: str) -> dict[str, str | int | float]:
    """Get the telemetry payload for the given tree ID."""
    if not tree_id:
        raise ValueError("Tree ID must not be empty")
    server_uuid = persistent_cache.get(TELEMETRY_SERVER_ID_KEY)
    if not server_uuid:
        server_uuid = generate_server_uuid()
        persistent_cache.set(TELEMETRY_SERVER_ID_KEY, server_uuid)
    tree_uuid = generate_tree_uuid(tree_id=tree_id, server_uuid=server_uuid)
    return {
        "server_uuid": server_uuid,
        "tree_uuid": tree_uuid,
        "timestamp": time.time(),
    }
