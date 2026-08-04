#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Optional Sentry error reporting."""

import logging

_LOG = logging.getLogger(__name__)


def init_sentry(app) -> bool:
    """Initialize Sentry if a DSN is configured. Returns True if enabled."""
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        _LOG.warning(
            "SENTRY_DSN is set but the sentry-sdk package is not installed. "
            "Install gramps-webapi[sentry] to enable error reporting."
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=app.config.get("API_VERSION"),
        environment=app.config.get("SENTRY_ENVIRONMENT") or None,
        traces_sample_rate=float(app.config.get("SENTRY_TRACES_SAMPLE_RATE", 0.0)),
        # off by default: family tree data is sensitive
        send_default_pii=bool(app.config.get("SENTRY_SEND_DEFAULT_PII", False)),
    )
    return True
