#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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

"""Constants for the web API."""

import shutil

import gramps.gen.lib as lib
from gramps.gen.plug import CATEGORY_DRAW, CATEGORY_GRAPHVIZ, CATEGORY_TEXT
from pkg_resources import resource_filename  # type: ignore[import-untyped]

from ._version import __version__ as VERSION

# the value of the TREE config option that enables multi-tree support
TREE_MULTI = "*"

# files
TEST_CONFIG = resource_filename("gramps_webapi", "data/test.cfg")
TEST_AUTH_CONFIG = resource_filename("gramps_webapi", "data/test_auth.cfg")
TEST_EXAMPLE_GRAMPS_CONFIG = resource_filename(
    "gramps_webapi", "data/example_gramps.cfg"
)
TEST_EXAMPLE_GRAMPS_AUTH_CONFIG = resource_filename(
    "gramps_webapi", "data/example_gramps_auth.cfg"
)
TEST_EMPTY_GRAMPS_AUTH_CONFIG = resource_filename(
    "gramps_webapi", "data/empty_gramps_auth.cfg"
)

# allowed db config keys
DB_CONFIG_ALLOWED_KEYS = [
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "DEFAULT_FROM_EMAIL",
    "BASE_URL",
]


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

# needed for iter_%s methods
GRAMPS_OBJECT_PLURAL = {
    "Person": "people",
    "Family": "families",
    "Event": "events",
    "Place": "places",
    "Citation": "citations",
    "Source": "sources",
    "Repository": "repositories",
    "Media": "media",
    "Note": "notes",
    "Tag": "tags",
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

# Some platforms may not find all of these
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".gvpdf": "application/pdf",
    ".gspdf": "application/pdf",
    ".gv": "text/vnd.graphviz",
    ".dot": "text/vnd.graphviz",
    ".rtf": "application/rtf",
    ".ps": "application/postscript",
    ".svg": "image/svg+xml",
    ".svgz": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".png": "image/png",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".tex": "application/x-tex",
    ".txt": "text/plain",
    ".html": "text/html",
}

# These determine the supported report categories and default formats
# depending on whether needed dependencies are available.
try:
    import gi

    gi.require_version("Gtk", "3.0")

    REPORT_FILTERS = ["gv", "dot", "gvpdf"]
    REPORT_DEFAULTS = {
        CATEGORY_TEXT: "pdf",
        CATEGORY_DRAW: "pdf",
    }
    if shutil.which("dot") is not None:
        REPORT_FILTERS = []
        REPORT_DEFAULTS[CATEGORY_GRAPHVIZ] = "dot"
except ImportError:
    REPORT_FILTERS = ["pdf", "ps", "gspdf", "gvpdf"]
    REPORT_DEFAULTS = {
        CATEGORY_TEXT: "rtf",
    }


# mapping Gramps language codes to locales that exist on a typical Unix system.
LOCALE_MAP = {
    "ar": "ar_EG",
    "bg": "bg_BG",
    "ca": "ca_ES",
    "cs": "cs_CZ",
    "da": "da_DK",
    "de": "de_DE",
    "el": "el_GR",
    "en": "en_US",
    "es": "es_ES",
    "fi": "fi_FI",
    "fr": "fr_FR",
    "he": "he_IL",
    "hr": "hr_HR",
    "hu": "hu_HU",
    "is": "is_IS",
    "it": "it_IT",
    "ja": "ja_JP",
    "lt": "lt_LT",
    "nb": "nb_NO",
    "nl": "nl_NL",
    "nn": "nn_NO",
    "pl": "pl_PL",
    "ru": "ru_RU",
    "sk": "sk_SK",
    "sl": "sl_SI",
    "sq": "sq_AL",
    "sr": "sr_RS",
    "sv": "sv_SE",
    "ta": "ta_IN",
    "tr": "tr_TR",
    "uk": "uk_UA",
    "vi": "vi_VN",
}

# list of importers (by file extension) that are not allowed
DISABLED_IMPORTERS = ["gpkg"]

# list of exporters (by file extension) that are not allowed
DISABLED_EXPORTERS = ["gpkg"]

# Settings for the opt-out telemetry
TELEMETRY_ENDPOINT = "https://telemetry-cloud-run-442080026669.europe-west1.run.app"
TELEMETRY_TIMESTAMP_KEY = "telemetry_last_sent"
TELEMETRY_SERVER_ID_KEY = "telemetry_server_uuid"

# Regular expression for allowed values of the `name_format` query parameter.
NAME_FORMAT_REGEXP = r"^(%[%tTfFlLcCxXiImMyYoOrRpPqQsSnNgG]|%[0-2][mMyY]|[ \u0022\u0027,.:;\]\[\(\)\{\}\&\@])*$"
