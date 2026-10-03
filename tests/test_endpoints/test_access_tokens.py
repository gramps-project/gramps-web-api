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
from uuid import uuid4

from gramps_webapi.auth import (
    AccessToken,
    add_user,
    get_guid,
    get_user_details,
    user_db,
)
from gramps_webapi.auth.const import (
    ACCESS_TOKEN_LABEL_MAX_LENGTH,
    ACCESS_TOKEN_MAX_PER_SCOPE,
    ACCESS_TOKEN_SCOPE_SYNC,
    ROLE_GUEST,
    ROLE_OWNER,
)

from . import BASE_URL, get_test_client
from .util import fetch_header

SCOPE = "anniversaries_ics"
TOKEN_URL = BASE_URL + f"/users/-/access-tokens/{SCOPE}/"
MULTIPLE_SCOPE = ACCESS_TOKEN_SCOPE_SYNC
TOKENS_URL = BASE_URL + f"/users/-/access-tokens/{MULTIPLE_SCOPE}/tokens/"


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
        self.assertEqual(rv.json, {"active": False})
        self.assertNotIn("token", rv.json)

        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        token_1 = rv.json["token"]
        self.assertTrue(rv.json["active"])
        self.assertIsInstance(token_1, str)
        self.assertNotEqual(token_1, "")

        with self.client.application.app_context():
            user_id = get_guid("owner")
            row = (
                user_db.session.query(AccessToken)  # pylint: disable=no-member
                .filter_by(user_id=user_id, scope=SCOPE)
                .one()
            )
            self.assertIsNotNone(row.token_hash)
            self.assertNotEqual(row.token_hash, token_1)
            self.assertEqual(len(row.token_hash), 64)

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": True})
        self.assertNotIn("token", rv.json)

        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        token_2 = rv.json["token"]
        self.assertNotEqual(token_1, token_2)

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": True})
        self.assertNotIn("token", rv.json)

        rv = self.client.delete(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": False})
        self.assertNotIn("token", rv.json)

        rv = self.client.get(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, {"active": False})
        self.assertNotIn("token", rv.json)

    def test_guest_can_manage_own_access_token(self):
        """Guests can manage own token because they can edit own user settings."""
        header = fetch_header(self.client, role=ROLE_GUEST)
        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["active"], True)
        self.assertIsNotNone(rv.json["token"])

    def test_single_token_endpoint_rejects_multiple_token_scope(self):
        """A scope with several tokens per user is managed via /tokens/."""
        header = fetch_header(self.client, role=ROLE_OWNER)
        url = BASE_URL + f"/users/-/access-tokens/{MULTIPLE_SCOPE}/"
        self.assertEqual(self.client.get(url, headers=header).status_code, 422)
        self.assertEqual(self.client.post(url, headers=header).status_code, 422)
        self.assertEqual(self.client.delete(url, headers=header).status_code, 422)


class TestMultipleAccessTokens(unittest.TestCase):
    """Test cases for scopes with several labelled tokens per user."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def _new_user_header(self, role=ROLE_GUEST):
        """Add a user to the owner's tree, log in, and return the header."""
        username = f"tokens-{uuid4().hex[:8]}"
        with self.client.application.app_context():
            tree = get_user_details("owner")["tree"]
            add_user(name=username, password="secret", role=role, tree=tree)
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": username, "password": "secret"}
        )
        self.assertEqual(rv.status_code, 200)
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def _create(self, header, label):
        return self.client.post(TOKENS_URL, headers=header, json={"label": label})

    def test_requires_jwt(self):
        """The endpoints require authentication."""
        self.assertEqual(self.client.get(TOKENS_URL).status_code, 401)
        rv = self.client.post(TOKENS_URL, json={"label": "Laptop"})
        self.assertEqual(rv.status_code, 401)
        self.assertEqual(self.client.delete(f"{TOKENS_URL}1/").status_code, 401)

    def test_lifecycle(self):
        """Tokens can be created, listed and revoked one by one."""
        header = self._new_user_header()
        rv = self.client.get(TOKENS_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, [])

        rv = self._create(header, "Laptop")
        self.assertEqual(rv.status_code, 201)
        laptop = rv.json
        self.assertEqual(
            set(laptop), {"id", "label", "created_at", "last_used_at", "token"}
        )
        self.assertEqual(laptop["label"], "Laptop")
        self.assertIsNone(laptop["last_used_at"])
        rv = self._create(header, "  Desktop ")
        self.assertEqual(rv.status_code, 201)
        desktop = rv.json
        self.assertEqual(desktop["label"], "Desktop")
        self.assertNotEqual(laptop["token"], desktop["token"])

        with self.client.application.app_context():
            row = (
                user_db.session.query(AccessToken)  # pylint: disable=no-member
                .filter_by(id=laptop["id"])
                .one()
            )
            self.assertEqual(len(row.token_hash), 64)
            self.assertNotEqual(row.token_hash, laptop["token"])

        rv = self.client.get(TOKENS_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(
            [item["id"] for item in rv.json], [laptop["id"], desktop["id"]]
        )
        self.assertEqual([item["label"] for item in rv.json], ["Laptop", "Desktop"])
        for item in rv.json:
            self.assertNotIn("token", item)

        rv = self.client.delete(f"{TOKENS_URL}{laptop['id']}/", headers=header)
        self.assertEqual(rv.status_code, 204)
        self.assertEqual(rv.data, b"")
        rv = self.client.delete(f"{TOKENS_URL}{laptop['id']}/", headers=header)
        self.assertEqual(rv.status_code, 404)
        rv = self.client.get(TOKENS_URL, headers=header)
        self.assertEqual([item["id"] for item in rv.json], [desktop["id"]])
        # the label is free again
        self.assertEqual(self._create(header, "Laptop").status_code, 201)

    def test_label_validation(self):
        """The label is required, non-blank, bounded, and unique per user."""
        header = self._new_user_header()
        rv = self.client.post(TOKENS_URL, headers=header, json={})
        self.assertEqual(rv.status_code, 422)
        self.assertEqual(self._create(header, "").status_code, 422)
        self.assertEqual(self._create(header, "   ").status_code, 422)
        too_long = "x" * (ACCESS_TOKEN_LABEL_MAX_LENGTH + 1)
        self.assertEqual(self._create(header, too_long).status_code, 422)
        self.assertEqual(self._create(header, "Laptop").status_code, 201)
        self.assertEqual(self._create(header, "Laptop").status_code, 409)
        self.assertEqual(self._create(header, " Laptop ").status_code, 409)
        # another user may use the same label
        other = self._new_user_header()
        self.assertEqual(self._create(other, "Laptop").status_code, 201)

    def test_maximum_number_of_tokens(self):
        """A user can't have more than the maximum number of tokens."""
        header = self._new_user_header()
        for i in range(ACCESS_TOKEN_MAX_PER_SCOPE):
            self.assertEqual(self._create(header, f"device {i}").status_code, 201)
        rv = self._create(header, "one too many")
        self.assertEqual(rv.status_code, 409)
        token_id = self.client.get(TOKENS_URL, headers=header).json[0]["id"]
        rv = self.client.delete(f"{TOKENS_URL}{token_id}/", headers=header)
        self.assertEqual(rv.status_code, 204)
        self.assertEqual(self._create(header, "one too many").status_code, 201)

    def test_cannot_see_or_revoke_other_users_tokens(self):
        """Tokens are only visible to and revocable by their owner."""
        header = self._new_user_header()
        other = self._new_user_header()
        token_id = self._create(header, "Laptop").json["id"]
        self.assertEqual(self.client.get(TOKENS_URL, headers=other).json, [])
        rv = self.client.delete(f"{TOKENS_URL}{token_id}/", headers=other)
        self.assertEqual(rv.status_code, 404)
        rv = self.client.get(TOKENS_URL, headers=header)
        self.assertEqual([item["id"] for item in rv.json], [token_id])

    def test_rejects_single_token_scope(self):
        """A scope with a single token per user has no /tokens/ endpoints."""
        header = self._new_user_header()
        url = BASE_URL + f"/users/-/access-tokens/{SCOPE}/tokens/"
        self.assertEqual(self.client.get(url, headers=header).status_code, 422)
        rv = self.client.post(url, headers=header, json={"label": "Laptop"})
        self.assertEqual(rv.status_code, 422)
        self.assertEqual(
            self.client.delete(f"{url}1/", headers=header).status_code, 422
        )
        url = BASE_URL + "/users/-/access-tokens/unsupported-scope/tokens/"
        self.assertEqual(self.client.get(url, headers=header).status_code, 422)
