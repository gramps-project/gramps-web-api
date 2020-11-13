#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Constants for the web API."""

import gramps.gen.lib as lib
from gramps.gen.plug import (
    CATEGORY_BOOK,
    CATEGORY_CODE,
    CATEGORY_DRAW,
    CATEGORY_GRAPHVIZ,
    CATEGORY_TEXT,
    CATEGORY_TREE,
    CATEGORY_WEB,
)
from pkg_resources import resource_filename

from ._version import __version__ as VERSION

# files
TEST_CONFIG = resource_filename("gramps_webapi", "data/test.cfg")
TEST_AUTH_CONFIG = resource_filename("gramps_webapi", "data/test_auth.cfg")
TEST_EXAMPLE_GRAMPS_CONFIG = resource_filename(
    "gramps_webapi", "data/example_gramps.cfg"
)
TEST_EXAMPLE_GRAMPS_AUTH_CONFIG = resource_filename(
    "gramps_webapi", "data/example_gramps_auth.cfg"
)

# environment variables
ENV_CONFIG_FILE = "GRAMPS_API_CONFIG"

# API endpoints
API_PREFIX = "/api"

# Sex identifiers
SEX_MALE = "M"
SEX_FEMALE = "F"
SEX_UNKNOWN = "U"

# Primary Gramps objects
# This is used to identify the only ones that the keys and skipkeys
# filters should operate on
PRIMARY_GRAMPS_OBJECTS = {
    "Person": lib.Person,
    "Family": lib.Family,
    "Event": lib.Event,
    "Place": lib.Place,
    "Citation": lib.Citation,
    "Source": lib.Source,
    "Repository": lib.Repository,
    "Media": lib.Media,
    "Note": lib.Note,
    "Tag": lib.Tag,
}

# To map endpoints to Gramps objects
GRAMPS_NAMESPACES = {
    "people": "Person",
    "families": "Family",
    "events": "Event",
    "places": "Place",
    "citations": "Citation",
    "sources": "Source",
    "repositories": "Repository",
    "media": "Media",
    "notes": "Note",
}

# MIME types
MIME_PDF = "application/pdf"
MIME_JPEG = "image/jpeg"
MIME_GIF = "image/gif"
MIME_PNG = "image/png"
MIME_TEXT = "text/plain"
MIME_HTML = "text/html"
MIME_TEX = "application/x-tex"
MIME_ODT = "application/vnd.oasis.opendocument.text"
MIME_PS = "application/postscript"
MIME_RTF = "application/rtf"
MIME_DOT = "application/octet-stream"
MIME_SVG = "image/svg+xml"
MIME_SVGZ = "image/svg+xml"
MIME_GSPDF = "application/pdf"
MIME_GVPDF = "application/pdf"

# Mapping of report output file formats to MIME types
REPORT_MIMETYPES = {
    "txt": MIME_TEXT,
    "html": MIME_HTML,
    "tex": MIME_TEX,
    "odt": MIME_ODT,
    "pdf": MIME_PDF,
    "ps": MIME_PS,
    "rtf": MIME_RTF,
    "dot": MIME_DOT,
    "gspdf": MIME_GSPDF,
    "gvpdf": MIME_GVPDF,
    "svg": MIME_SVG,
    "svgz": MIME_SVGZ,
    "jpg": MIME_JPEG,
    "gif": MIME_GIF,
    "png": MIME_PNG,
}

# Mapping of defaults based on report category
REPORT_DEFAULTS = {
    CATEGORY_TEXT: "pdf",
    CATEGORY_DRAW: "pdf",
    CATEGORY_GRAPHVIZ: "gvpdf",
    CATEGORY_BOOK: "pdf",
    CATEGORY_TREE: "pdf",
    CATEGORY_CODE: "pdf",
    CATEGORY_WEB: "html",
}
