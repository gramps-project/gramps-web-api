"""Default configuration settings."""

import datetime


class DefaultConfig(object):
    """Default configuration object."""

    PROPAGATE_EXCEPTIONS = True


class DefaultConfigJWT(object):
    """Default configuration for JWT auth."""

    JWT_TOKEN_LOCATION = ["headers", "query_string"]
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)
