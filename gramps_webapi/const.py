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
from gramps.gen.plug import CATEGORY_DRAW, CATEGORY_GRAPHVIZ, CATEGORY_TEXT
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

# These determine the supported report categories and default formats
# depending on whether needed dependencies are available.
try:
    import gi

    REPORT_DEFAULTS = {
        CATEGORY_TEXT: "pdf",
        CATEGORY_DRAW: "pdf",
        CATEGORY_GRAPHVIZ: "gspdf",
    }
    REPORT_FILTERS = []
except ImportError:
    REPORT_DEFAULTS = {
        CATEGORY_TEXT: "rtf",
    }
    REPORT_FILTERS = ["pdf", "ps", "gspdf", "gvpdf"]
