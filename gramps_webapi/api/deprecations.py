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

"""Detection of deprecated configuration options."""

from __future__ import annotations

import os
from typing import Any, Callable, Mapping

from ..config import DefaultConfig

# default removal target; individual deprecations may be scheduled for a later release
REMOVED_IN = "4.0.0"

# config options that can also be set via an unprefixed environment variable
DEPRECATED_ENV_OPTIONS = [
    "TREE",
    "SECRET_KEY",
    "USER_DB_URI",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "MEDIA_BASE_DIR",
    "SEARCH_INDEX_DIR",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "DEFAULT_FROM_EMAIL",
    "BASE_URL",
    "STATIC_PATH",
]


def _deprecation(
    option: str, replacement: str, message: str, removed_in: str = REMOVED_IN
) -> dict[str, str]:
    """Build a single deprecation entry."""
    return {
        "option": option,
        "replacement": replacement,
        "message": message,
        "removed_in": removed_in,
    }


def check_deprecations(
    config: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
    get_option: Callable[[str], Any] | None = None,
) -> list[dict[str, str]]:
    """Return the deprecated configuration options this deployment relies on.

    `get_option` is used to look up options that can also be stored in the user
    database rather than in the app config; it defaults to the app config.
    """
    if environ is None:
        environ = os.environ
    if get_option is None:
        get_option = config.get
    deprecations = []
    for option in DEPRECATED_ENV_OPTIONS:
        # a prefixed variable takes precedence, so the unprefixed one is unused
        if environ.get(option) and not environ.get(f"GRAMPSWEB_{option}"):
            deprecations.append(
                _deprecation(
                    option,
                    f"GRAMPSWEB_{option}",
                    f"Setting the `{option}` config option via the `{option}`"
                    f" environment variable is deprecated. Please use"
                    f" `GRAMPSWEB_{option}` instead.",
                )
            )
    if (
        not config["SEARCH_INDEX_DB_URI"]
        # the default value is equivalent to the default SEARCH_INDEX_DB_URI
        and config["SEARCH_INDEX_DIR"] != DefaultConfig.SEARCH_INDEX_DIR
    ):
        deprecations.append(
            _deprecation(
                "SEARCH_INDEX_DIR",
                "SEARCH_INDEX_DB_URI",
                "The `SEARCH_INDEX_DIR` config option is deprecated. Please use"
                " `SEARCH_INDEX_DB_URI` instead, e.g. setting it to"
                f" `sqlite:///{config['SEARCH_INDEX_DIR']}/search_index.db`.",
            )
        )
    if (
        config["EMAIL_USE_SSL"] is None
        and config["EMAIL_USE_STARTTLS"] is None
        # only relevant if e-mails are sent at all; may be stored in the database,
        # so this is looked up last to avoid the query where possible
        and get_option("DEFAULT_FROM_EMAIL")
    ):
        deprecations.append(
            _deprecation(
                "EMAIL_USE_TLS",
                "EMAIL_USE_SSL",
                "The `EMAIL_USE_TLS` config option is deprecated. Please use"
                " `EMAIL_USE_SSL` or `EMAIL_USE_STARTTLS` instead.",
            )
        )
    return deprecations
