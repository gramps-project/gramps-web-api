#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025           Alexander Bocken
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

"""Token blocklist for handling OIDC backchannel logout."""

import logging
from datetime import datetime, timedelta
from typing import Set

logger = logging.getLogger(__name__)

# In-memory blocklist for revoked JTIs (JWT IDs)
# In production, this should use Redis or a database for persistence across instances
_BLOCKLIST: Set[str] = set()

# Track when JTIs were added for cleanup
_BLOCKLIST_TIMESTAMPS: dict[str, datetime] = {}


def add_jti_to_blocklist(jti: str) -> None:
    """Add a JTI (JWT ID) to the blocklist.

    Args:
        jti: The JWT ID to blocklist
    """
    _BLOCKLIST.add(jti)
    _BLOCKLIST_TIMESTAMPS[jti] = datetime.now()
    logger.info(f"Added JTI to blocklist: {jti}")


def is_jti_blocklisted(jti: str) -> bool:
    """Check if a JTI is in the blocklist.

    Args:
        jti: The JWT ID to check

    Returns:
        True if the JTI is blocklisted, False otherwise
    """
    return jti in _BLOCKLIST


def cleanup_expired_jtis(max_age_hours: int = 24) -> int:
    """Remove JTIs older than max_age_hours from the blocklist.

    This prevents the blocklist from growing indefinitely.
    JTIs can be safely removed after the token expiration time has passed.

    Args:
        max_age_hours: Maximum age in hours before a JTI is removed from blocklist

    Returns:
        Number of JTIs removed
    """
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    to_remove = [
        jti
        for jti, timestamp in _BLOCKLIST_TIMESTAMPS.items()
        if timestamp < cutoff
    ]

    for jti in to_remove:
        _BLOCKLIST.discard(jti)
        _BLOCKLIST_TIMESTAMPS.pop(jti, None)

    if to_remove:
        logger.info(f"Cleaned up {len(to_remove)} expired JTIs from blocklist")

    return len(to_remove)


def get_blocklist_size() -> int:
    """Get the current size of the blocklist.

    Returns:
        Number of JTIs in the blocklist
    """
    return len(_BLOCKLIST)
