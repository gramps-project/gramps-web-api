#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Default configuration settings."""

import datetime
import os


class DefaultConfig(object):
    """Default configuration object."""

    PROPAGATE_EXCEPTIONS = True
    SEARCH_INDEX_DIR = os.getenv("SEARCH_INDEX_DIR", "indexdir")
    EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "")
    BASE_URL = os.getenv("BASE_URL", "http://localhost/")
    CORS_EXPOSE_HEADERS = ["X-Total-Count"]
    STATIC_PATH = os.getenv("STATIC_PATH", "static")
    THUMBNAIL_CACHE_CONFIG = {
        "CACHE_TYPE": "filesystem",
        "CACHE_DIR": "thumbnail_cache",
        "CACHE_THRESHOLD": 1000,
    }
    POSTGRES_USER = None
    POSTGRES_PASSWORD = None


class DefaultConfigJWT(object):
    """Default configuration for JWT auth."""

    JWT_TOKEN_LOCATION = ["headers", "query_string"]
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)
