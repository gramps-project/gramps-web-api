#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Test utility functions."""

import time
from weakref import WeakKeyDictionary

from gramps_webapi.auth.const import ROLE_OWNER

from . import TEST_USERS

# Logging in hashes the password, which is slow by design, so access tokens
# are cached per app and user, and renewed well before they expire.
_TOKEN_CACHE: WeakKeyDictionary = WeakKeyDictionary()
_TOKEN_MAX_AGE = 600


def clear_token_cache():
    """Clear cached access tokens, e.g. after changing a user's role."""
    _TOKEN_CACHE.clear()


def fetch_header(test, role=ROLE_OWNER, empty_db: bool = False):
    """Return authorization header with valid token."""
    username = TEST_USERS[role]["name"]
    if empty_db:
        username += "_empty"
    tokens = _TOKEN_CACHE.setdefault(test.application, {})
    token, created = tokens.get(username, (None, 0.0))
    if token is None or time.monotonic() - created > _TOKEN_MAX_AGE:
        rv = test.post(
            "/api/token/",
            json={
                "username": username,
                "password": TEST_USERS[role]["password"],
            },
        )
        token = rv.json["access_token"]
        tokens[username] = (token, time.monotonic())
    return {"Authorization": "Bearer {}".format(token)}


def check_keys_stripped(test, object1, object2):
    """Check keys for empty values in first object no longer exist in second."""
    for key in object1:
        if object1[key] in [[], {}, None]:
            test.assertNotIn(key, object2)
        else:
            if isinstance(object1[key], type({})):
                check_keys_stripped(test, object1[key], object2[key])
            if isinstance(object1[key], type([])):
                for item in object1:
                    if isinstance(item, (type([]), type({}))):
                        check_keys_stripped(test, item, object2[object1.index(item)])
