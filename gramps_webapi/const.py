"""Constants for the web API."""

import gramps.gen.lib as lib
from pkg_resources import resource_filename

# files
TEST_CONFIG = resource_filename("gramps_webapi", "data/test.cfg")
TEST_AUTH_CONFIG = resource_filename("gramps_webapi", "data/test_auth.cfg")

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
