#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Test utility functions."""

from gramps_webapi.auth.const import ROLE_OWNER

from . import TEST_USERS


def fetch_header(test, role=ROLE_OWNER):
    """Return authorization header with valid token."""
    rv = test.post(
        "/api/token/",
        json={
            "username": TEST_USERS[role]["name"],
            "password": TEST_USERS[role]["password"],
        },
    )
    return {"Authorization": "Bearer {}".format(rv.json["access_token"])}


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
