"""Constants for the web API."""

from pkg_resources import resource_filename

# files
TEST_CONFIG = resource_filename("gramps_webapi", "data/test.cfg")

# environment variables
ENV_CONFIG_FILE = "GRAMPS_API_CONFIG"

# API endpoints
API_PREFIX = "/api"
