#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2022      David Straub
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
from pathlib import Path
from typing import Dict


class DefaultConfig(object):
    """Default configuration object."""

    PROPAGATE_EXCEPTIONS = True
    SEARCH_INDEX_DIR = "indexdir"  # deprecated!
    SEARCH_INDEX_DB_URI = ""
    EMAIL_HOST = "localhost"
    EMAIL_PORT = "465"
    EMAIL_HOST_USER = ""
    EMAIL_HOST_PASSWORD = ""
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = ""
    BASE_URL = "http://localhost/"
    CORS_EXPOSE_HEADERS = ["X-Total-Count"]
    STATIC_PATH = "static"
    REQUEST_CACHE_CONFIG = {
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": str(Path.cwd() / "request_cache"),
        "CACHE_THRESHOLD": 1000,
        "CACHE_DEFAULT_TIMEOUT": 0,
    }
    THUMBNAIL_CACHE_CONFIG = {
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": str(Path.cwd() / "thumbnail_cache"),
        "CACHE_THRESHOLD": 1000,
        "CACHE_DEFAULT_TIMEOUT": 0,
    }
    PERSISTENT_CACHE_CONFIG = {
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": str(Path.cwd() / "persistent_cache"),
        "CACHE_THRESHOLD": 0,
        "CACHE_DEFAULT_TIMEOUT": 0,
    }
    POSTGRES_USER = None
    POSTGRES_PASSWORD = None
    POSTGRES_HOST = "localhost"
    POSTGRES_PORT = "5432"
    IGNORE_DB_LOCK = False
    CELERY_CONFIG: Dict[str, str] = {}
    MEDIA_BASE_DIR = ""
    MEDIA_PREFIX_TREE = False
    REPORT_DIR = str(Path.cwd() / "report_cache")
    EXPORT_DIR = str(Path.cwd() / "export_cache")
    NEW_DB_BACKEND = "sqlite"
    RATE_LIMIT_MEDIA_ARCHIVE = "1 per day"
    REGISTRATION_DISABLED = False
    LOG_LEVEL = "INFO"
    LLM_BASE_URL = None
    LLM_MODEL = ""
    LLM_MAX_CONTEXT_LENGTH = 50000
    VECTOR_EMBEDDING_MODEL = ""
    DISABLE_TELEMETRY = False


class DefaultConfigJWT(object):
    """Default configuration for JWT auth."""

    JWT_TOKEN_LOCATION = ["headers", "query_string"]
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = False
    JWT_ERROR_MESSAGE_KEY = "message"
