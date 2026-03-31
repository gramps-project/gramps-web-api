#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#

"""Tests for persistent access token endpoints."""

import unittest

from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

SCOPE = "anniversaries_ics"
TOKEN_URL = BASE_URL + f"/users/-/access-tokens/{SCOPE}/"


class TestAccessTokens(unittest.TestCase):
    """Test cases for persistent access token lifecycle endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_access_token_endpoint_requires_jwt(self):
        """Access token endpoint requires authentication."""
        rv = self.client.get(TOKEN_URL)
        self.assertEqual(rv.status_code, 401)

    def test_access_token_rejects_invalid_scope(self):
        """Access token endpoint rejects unsupported scopes."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(
            BASE_URL + "/users/-/access-tokens/unsupported-scope/",
            headers=header,
        )
        self.assertEqual(rv.status_code, 422)

    def test_access_token_lifecycle_owner(self):
        """Token lifecycle create/get/rotate/revoke works for owner."""
        header = fetch_header(self.client, role=ROLE_OWNER)

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": False, "token": None})

        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        token_1 = rv.json["token"]
        self.assertTrue(rv.json["active"])
        self.assertIsInstance(token_1, str)
        self.assertNotEqual(token_1, "")

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": True, "token": token_1})

        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        token_2 = rv.json["token"]
        self.assertNotEqual(token_1, token_2)

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": True, "token": token_2})

        rv = self.client.delete(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": False, "token": None})

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": False, "token": None})

    def test_guest_can_manage_own_access_token(self):
        """Guests can manage own token because they can edit own user settings."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["active"], True)
        self.assertIsNotNone(rv.json["token"])
