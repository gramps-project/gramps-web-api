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

"""Utility functions."""

import mimetypes
from typing import Optional

from ..const import MIME_TYPES


def get_extension(mime: str) -> Optional[str]:
    """Get extension from MIME type."""
    # try hard-coded types first
    for ext, ext_mime in MIME_TYPES.items():
        if mime == ext_mime:
            return ext
    # last resort
    return mimetypes.guess_extension(mime, strict=False)


def get_type(ext: str) -> Optional[str]:
    """Get file extension from MIME type."""
    # try hard-coded types first
    if ext in MIME_TYPES:
        return MIME_TYPES[ext]
    # last resort
    typ, enc = mimetypes.guess_type(ext, strict=False)
    return typ


def pin_postgres_driver(url: str) -> str:
    """Use psycopg2 for a PostgreSQL URL that names no driver.

    SQLAlchemy 2.1 made psycopg (3) the default PostgreSQL driver, but Gramps
    Web uses psycopg2 everywhere else (sifts, the PostgreSQL addons). A URL
    with an explicit driver, e.g. ``postgresql+psycopg://``, is left alone.
    """
    prefix = "postgresql://"
    if url.startswith(prefix):
        return "postgresql+psycopg2://" + url[len(prefix) :]
    return url
