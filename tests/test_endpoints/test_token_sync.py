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

"""Tests for exchanging a persistent sync token for an access token."""

import unittest
from unittest.mock import patch
from uuid import uuid4

from flask_jwt_extended import decode_token

from gramps_webapi.auth import (
    add_user,
    get_permissions,
    get_user_details,
    modify_user,
    rotate_user_access_token,
)
from gramps_webapi.auth.const import (
    ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS,
    ACCESS_TOKEN_SCOPE_PERMISSIONS,
    ACCESS_TOKEN_SCOPE_SYNC,
    PERM_EDIT_OBJ,
    PERM_EDIT_OWN_USER,
    ROLE_DISABLED,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_OWNER,
)

from . import BASE_URL, TEST_USERS, get_test_client
from .util import fetch_header

SYNC_URL = BASE_URL + "/token/sync/"
TOKEN_URL = BASE_URL + "/users/-/access-tokens/sync/"
MEDIA_HANDLE = "b39fe1cfc1305ac4a21"
SYNC_PERMISSIONS = ACCESS_TOKEN_SCOPE_PERMISSIONS[ACCESS_TOKEN_SCOPE_SYNC]


class TestTokenSync(unittest.TestCase):
    """Test cases for POST /token/sync/."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def _create_token(self, role=ROLE_OWNER):
        """Create or rotate a sync token for role and return (header, token)."""
        header = fetch_header(self.client, role=role)
        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        return header, rv.json["token"]

    def _add_user(self, role):
        """Add a user in the owner's tree and return its name."""
        username = f"sync-{uuid4().hex[:8]}"
        with self.client.application.app_context():
            tree = get_user_details("owner")["tree"]
            add_user(name=username, password="secret", role=role, tree=tree)
        return username

    def _claims(self, access_token):
        with self.client.application.app_context():
            return decode_token(access_token)

    def _sync_header(self, role=ROLE_OWNER):
        """Return (access token, header) for a JWT exchanged from a sync token."""
        _, token = self._create_token(role=role)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 200)
        access = rv.json["access_token"]
        return access, {"Authorization": f"Bearer {access}"}

    def test_requires_token(self):
        """A missing, empty or unknown token is rejected."""
        rv = self.client.post(SYNC_URL, json={})
        self.assertEqual(rv.status_code, 422)
        rv = self.client.post(SYNC_URL, json={"token": ""})
        self.assertEqual(rv.status_code, 422)
        rv = self.client.post(SYNC_URL, json={"token": "invalid-token"})
        self.assertEqual(rv.status_code, 401)

    def test_exchange_returns_non_fresh_access_token_only(self):
        """The exchange returns a usable access token and no refresh token."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(set(rv.json), {"access_token"})
        claims = self._claims(rv.json["access_token"])
        self.assertFalse(claims["fresh"])
        self.assertEqual(claims["type"], "access")
        with self.client.application.app_context():
            user = get_user_details("owner", include_guid=True)
            full = get_permissions(username="owner", tree=user["tree"])
        self.assertEqual(claims["sub"], str(user["user_id"]))
        self.assertEqual(claims["tree"], user["tree"])
        # narrowed to the sync allowlist, which an owner has in full
        self.assertEqual(set(claims["permissions"]), full & SYNC_PERMISSIONS)
        self.assertEqual(set(claims["permissions"]), set(SYNC_PERMISSIONS))
        self.assertNotIn(PERM_EDIT_OWN_USER, claims["permissions"])
        rv = self.client.get(
            BASE_URL + "/people/",
            headers={"Authorization": f"Bearer {rv.json['access_token']}"},
        )
        self.assertEqual(rv.status_code, 200)

    def test_revoked_and_rotated_tokens_are_rejected(self):
        """Revoking or rotating the sync token invalidates the old value."""
        header, token_1 = self._create_token(role=ROLE_GUEST)
        rv = self.client.post(TOKEN_URL, headers=header)
        token_2 = rv.json["token"]
        rv = self.client.post(SYNC_URL, json={"token": token_1})
        self.assertEqual(rv.status_code, 401)
        rv = self.client.post(SYNC_URL, json={"token": token_2})
        self.assertEqual(rv.status_code, 200)
        rv = self.client.delete(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        rv = self.client.post(SYNC_URL, json={"token": token_2})
        self.assertEqual(rv.status_code, 401)

    def test_other_scope_cannot_be_exchanged(self):
        """A token of another scope does not work as a sync token."""
        username = self._add_user(ROLE_OWNER)
        with self.client.application.app_context():
            token = rotate_user_access_token(
                username, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
            )
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 401)

    def test_disabled_user(self):
        """Disabled users cannot exchange their sync token."""
        username = self._add_user(ROLE_DISABLED)
        with self.client.application.app_context():
            token = rotate_user_access_token(username, ACCESS_TOKEN_SCOPE_SYNC)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 403)

    def test_disabled_tree(self):
        """If the tree is disabled, the exchange returns 503."""
        _, token = self._create_token(role=ROLE_OWNER)
        with patch(
            "gramps_webapi.api.resources.token.is_tree_disabled",
            return_value=True,
        ):
            rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 503)

    def test_permissions_are_looked_up_on_every_exchange(self):
        """A role change takes effect at the next exchange."""
        username = self._add_user(ROLE_EDITOR)
        with self.client.application.app_context():
            token = rotate_user_access_token(username, ACCESS_TOKEN_SCOPE_SYNC)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 200)
        self.assertIn(
            PERM_EDIT_OBJ, self._claims(rv.json["access_token"])["permissions"]
        )
        with self.client.application.app_context():
            modify_user(name=username, role=ROLE_GUEST)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn(
            PERM_EDIT_OBJ, self._claims(rv.json["access_token"])["permissions"]
        )
        with self.client.application.app_context():
            modify_user(name=username, role=ROLE_DISABLED)
        rv = self.client.post(SYNC_URL, json={"token": token})
        self.assertEqual(rv.status_code, 403)

    def test_works_when_local_auth_is_disabled(self):
        """Password login is refused, but the sync token still works."""
        _, token = self._create_token(role=ROLE_OWNER)
        config = self.client.application.config
        with (
            patch(
                "gramps_webapi.api.resources.token.is_oidc_enabled", return_value=True
            ),
            patch.dict(config, {"OIDC_DISABLE_LOCAL_AUTH": True}),
        ):
            rv = self.client.post(
                BASE_URL + "/token/",
                json={"username": "owner", "password": "123"},
            )
            self.assertEqual(rv.status_code, 403)
            rv = self.client.post(SYNC_URL, json={"token": token})
            self.assertEqual(rv.status_code, 200)

    def test_sync_jwt_cannot_edit_own_user(self):
        """A sync-issued JWT can't change the account, e.g. its e-mail."""
        _, header = self._sync_header(role=ROLE_OWNER)
        rv = self.client.put(
            BASE_URL + "/users/-/",
            json={"email": "attacker@example.com"},
            headers=header,
        )
        self.assertEqual(rv.status_code, 403)
        with self.client.application.app_context():
            self.assertNotEqual(
                get_user_details("owner")["email"], "attacker@example.com"
            )

    def test_sync_jwt_cannot_manage_access_tokens(self):
        """A sync-issued JWT can't read, create or revoke persistent tokens."""
        _, header = self._sync_header(role=ROLE_OWNER)
        for scope in (ACCESS_TOKEN_SCOPE_SYNC, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS):
            url = BASE_URL + f"/users/-/access-tokens/{scope}/"
            self.assertEqual(self.client.get(url, headers=header).status_code, 403)
            self.assertEqual(self.client.post(url, headers=header).status_code, 403)
            self.assertEqual(self.client.delete(url, headers=header).status_code, 403)

    def test_sync_jwt_reads_and_writes_tree_data(self):
        """A sync-issued JWT can read, add, delete, and fetch media via ?jwt=."""
        access, header = self._sync_header(role=ROLE_OWNER)
        rv = self.client.get(BASE_URL + "/people/?pagesize=1", headers=header)
        self.assertEqual(rv.status_code, 200)
        rv = self.client.post(
            BASE_URL + "/notes/",
            json={"_class": "Note", "text": {"_class": "StyledText", "string": "x"}},
            headers=header,
        )
        self.assertEqual(rv.status_code, 201)
        handle = rv.json[0]["handle"]
        rv = self.client.delete(BASE_URL + f"/notes/{handle}", headers=header)
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get(BASE_URL + f"/media/{MEDIA_HANDLE}/file?jwt={access}")
        self.assertEqual(rv.status_code, 200)

    def test_refresh_keeps_full_permissions(self):
        """Only sync-issued JWTs are narrowed, not refreshed ones."""
        user = TEST_USERS[ROLE_OWNER]
        rv = self.client.post(
            BASE_URL + "/token/",
            json={"username": user["name"], "password": user["password"]},
        )
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {rv.json['refresh_token']}"},
        )
        self.assertEqual(rv.status_code, 200)
        claims = self._claims(rv.json["access_token"])
        self.assertIn(PERM_EDIT_OWN_USER, claims["permissions"])
