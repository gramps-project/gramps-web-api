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

"""Cookie utilities for secure authentication."""

import logging
from urllib.parse import urlparse
from flask import current_app

from ..api.util import get_config

logger = logging.getLogger(__name__)


def get_cookie_domain():
    """
    Determine the appropriate cookie domain for cross-origin cookie sharing.

    Returns the shared parent domain if backend and frontend can share cookies,
    None otherwise (fallback to URL fragment method required).

    Examples:
        BASE_URL=https://api.example.com, FRONTEND_URL=https://app.example.com -> .example.com
        BASE_URL=https://example.com/api, FRONTEND_URL=https://example.com -> .example.com
        BASE_URL=https://backend.com, FRONTEND_URL=https://frontend.com -> None
    """
    base_url = get_config("BASE_URL")
    frontend_url = get_config("FRONTEND_URL") or base_url

    logger.debug(f"Cookie domain calculation: BASE_URL={base_url}, FRONTEND_URL={frontend_url}")

    if not base_url or not frontend_url:
        logger.warning("BASE_URL or FRONTEND_URL not configured, cannot determine cookie domain")
        return None

    try:
        base_domain = urlparse(base_url).netloc
        frontend_domain = urlparse(frontend_url).netloc

        # Remove port numbers if present
        base_host = base_domain.split(':')[0]
        frontend_host = frontend_domain.split(':')[0]

        logger.debug(f"Parsed hosts: base_host={base_host}, frontend_host={frontend_host}")

        # Handle localhost/IP addresses - special handling for development
        if (base_host in ['localhost', '127.0.0.1'] or
            frontend_host in ['localhost', '127.0.0.1'] or
            base_host.replace('.', '').isdigit() or
            frontend_host.replace('.', '').isdigit()):

            # For localhost development, we can share cookies if both use same host
            if base_host == frontend_host:
                logger.debug(f"Localhost development: using domain {base_host}")
                return base_host  # Don't use dot prefix for localhost
            else:
                logger.debug("Different localhost/IP addresses, cannot share cookies")
                return None

        # Same domain - can share cookies
        if base_host == frontend_host:
            return f".{base_host}"

        # Different subdomains - check for shared parent domain
        base_parts = base_host.split('.')
        frontend_parts = frontend_host.split('.')

        # Need at least 2 parts for a valid domain (e.g., example.com)
        if len(base_parts) >= 2 and len(frontend_parts) >= 2:
            # Get the last 2 parts (root domain)
            base_root = '.'.join(base_parts[-2:])
            frontend_root = '.'.join(frontend_parts[-2:])

            if base_root == frontend_root:
                logger.debug(f"Shared parent domain found: .{base_root}")
                return f".{base_root}"

        logger.debug("No shared domain found between %s and %s", base_host, frontend_host)
        return None

    except Exception as e:
        logger.exception("Error determining cookie domain: %s", e)
        return None


def get_cookie_config():
    """
    Get secure cookie configuration based on environment.

    Returns dict with cookie settings for secure token storage.
    """
    config = {
        'httponly': True,
        'samesite': 'Lax',  # Default to Lax for better compatibility
        'secure': current_app.config.get('PREFER_HTTPS', False),
        'max_age': 60 * 15,  # 15 minutes for access token
        'path': '/',
    }

    # Determine if we need cross-origin cookies
    cookie_domain = get_cookie_domain()
    base_url = get_config("BASE_URL")
    frontend_url = get_config("FRONTEND_URL") or base_url

    if cookie_domain:
        config['domain'] = cookie_domain

        # Check if we need SameSite=None for cross-origin
        if base_url and frontend_url:
            base_domain = urlparse(base_url).netloc.split(':')[0]
            frontend_domain = urlparse(frontend_url).netloc.split(':')[0]

            if base_domain != frontend_domain:
                config['samesite'] = 'None'
                config['secure'] = True  # Required for SameSite=None
                logger.debug("Cross-origin setup detected, using SameSite=None")

    return config


def can_use_cookies():
    """
    Check if cookies can be used for the current frontend/backend configuration.

    Returns True if cookies can be shared, False if URL fragment fallback needed.
    """
    return get_cookie_domain() is not None