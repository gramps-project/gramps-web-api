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
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for listing and unlinking the current user's OIDC accounts."""

import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from gramps_webapi.api.resources.token import issue_access_token
from gramps_webapi.app import create_app
from gramps_webapi.auth import (
    UNLINK_LAST,
    UNLINKED,
    add_user,
    create_oidc_account,
    delete_user,
    get_guid,
    get_user_details,
    get_user_oidc_accounts,
    unlink_oidc_account,
    user_db,
)
from gramps_webapi.auth.const import ACCESS_TOKEN_SCOPE_SYNC, ROLE_EDITOR
from gramps_webapi.const import ENV_CONFIG_FILE, TREE_MULTI

from . import BASE_URL, get_test_client

LIST_URL = BASE_URL + "/users/-/oidc-accounts/"
OIDC = "gramps_webapi.api.resources.oidc_accounts"


class TestOIDCAccounts(unittest.TestCase):
    """Test cases for /users/-/oidc-accounts/."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.app = cls.client.application

    def setUp(self):
        """Add a user with a password, the way a local account has one."""
        self.user = self._add_user()

    def _add_user(self):
        name = f"unlink-{uuid4().hex[:8]}"
        with self.app.app_context():
            tree = get_user_details("owner")["tree"]
            add_user(name=name, password="secret", role=ROLE_EDITOR, tree=tree)
        return name

    def _link(self, name, provider="custom"):
        """Link a new identity to name and return its ID."""
        with self.app.app_context():
            guid = get_guid(name)
            create_oidc_account(guid, provider, f"sub-{uuid4().hex}")
            return get_user_oidc_accounts(guid)[-1]["id"]

    def _accounts(self, name):
        with self.app.app_context():
            return [a["id"] for a in get_user_oidc_accounts(get_guid(name))]

    def _header(self, name, fresh=True):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": name, "password": "secret"}
        )
        self.assertEqual(rv.status_code, 200)
        if fresh:
            return {"Authorization": f"Bearer {rv.json['access_token']}"}
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {rv.json['refresh_token']}"},
        )
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def _unlink(self, account_id, name=None, **body):
        return self.client.delete(
            f"{LIST_URL}{account_id}/",
            headers=self._header(name or self.user),
            json=body,
        )

    def test_list_own_accounts(self):
        first = self._link(self.user)
        second = self._link(self.user, provider="google")
        self._link(self._add_user())
        rv = self.client.get(LIST_URL, headers=self._header(self.user))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual([a["id"] for a in rv.json], [first, second])
        self.assertEqual(rv.json[1]["provider_id"], "google")

    def test_list_without_accounts(self):
        rv = self.client.get(LIST_URL, headers=self._header(self.user))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, [])

    def test_unlink_needs_a_token(self):
        account = self._link(self.user)
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        self.assertEqual(self.client.delete(f"{LIST_URL}{account}/").status_code, 401)

    def test_unlink_needs_a_fresh_login(self):
        account = self._link(self.user)
        self._link(self.user)
        rv = self.client.delete(
            f"{LIST_URL}{account}/", headers=self._header(self.user, fresh=False)
        )
        self.assertEqual(rv.status_code, 401)
        self.assertIn(account, self._accounts(self.user))

    def test_unlink_one_of_several_without_password(self):
        account = self._link(self.user)
        other = self._link(self.user)
        rv = self.client.delete(
            f"{LIST_URL}{account}/", headers=self._header(self.user)
        )
        self.assertEqual(rv.status_code, 204)
        self.assertEqual(self._accounts(self.user), [other])

    def test_another_users_account_is_not_found(self):
        self._link(self.user)
        theirs = self._link(self._add_user())
        self._link(self.user)
        rv = self._unlink(theirs)
        self.assertEqual(rv.status_code, 404)

    def test_unknown_account_is_not_found(self):
        self.assertEqual(self._unlink(999999).status_code, 404)

    def test_last_account_needs_the_password(self):
        account = self._link(self.user)
        rv = self.client.delete(
            f"{LIST_URL}{account}/", headers=self._header(self.user)
        )
        self.assertEqual(rv.status_code, 403)
        self.assertEqual(self._accounts(self.user), [account])

    def test_last_account_wrong_password(self):
        """E.g. a user created through OIDC, with a random password."""
        account = self._link(self.user)
        self.assertEqual(self._unlink(account, password="wrong").status_code, 403)
        self.assertEqual(self._accounts(self.user), [account])

    def test_last_account_with_password(self):
        account = self._link(self.user)
        self.assertEqual(self._unlink(account, password="secret").status_code, 204)
        self.assertEqual(self._accounts(self.user), [])
        # the user can still log in
        self._header(self.user)

    def test_last_account_never_with_local_auth_disabled(self):
        account = self._link(self.user)
        header = self._header(self.user)
        with (
            patch("gramps_webapi.auth.oidc_helpers.is_oidc_enabled", return_value=True),
            patch.dict(self.app.config, {"OIDC_DISABLE_LOCAL_AUTH": True}),
        ):
            rv = self.client.delete(
                f"{LIST_URL}{account}/", headers=header, json={"password": "secret"}
            )
        self.assertEqual(rv.status_code, 409)
        self.assertEqual(self._accounts(self.user), [account])

    def test_not_last_with_local_auth_disabled(self):
        account = self._link(self.user)
        self._link(self.user)
        header = self._header(self.user)
        with (
            patch("gramps_webapi.auth.oidc_helpers.is_oidc_enabled", return_value=True),
            patch.dict(self.app.config, {"OIDC_DISABLE_LOCAL_AUTH": True}),
        ):
            rv = self.client.delete(f"{LIST_URL}{account}/", headers=header)
        self.assertEqual(rv.status_code, 204)

    def test_sync_token_cannot_list_accounts(self):
        """Tokens exchanged from a sync token may only sync."""
        self._link(self.user)
        with self.app.test_request_context():
            token = issue_access_token(
                self._guid(self.user), scope=ACCESS_TOKEN_SCOPE_SYNC
            )["access_token"]
        rv = self.client.get(LIST_URL, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(rv.status_code, 403)

    def test_deleted_user_gets_401(self):
        account = self._link(self.user)
        header = self._header(self.user)
        with self.app.app_context():
            delete_user(self.user)
        rv = self.client.delete(
            f"{LIST_URL}{account}/", headers=header, json={"password": "secret"}
        )
        self.assertEqual(rv.status_code, 401)

    def _guid(self, name):
        with self.app.app_context():
            return str(get_guid(name))


class TestConcurrentUnlink(unittest.TestCase):
    """Two unlinks at once against a SQLite file, as in a default deployment."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        # a config file left in the environment by another test would be loaded
        with patch.dict(os.environ):
            os.environ.pop(ENV_CONFIG_FILE, None)
            self.app = create_app(
                config={
                    "TREE": TREE_MULTI,
                    "SECRET_KEY": "secret",
                    "USER_DB_URI": "sqlite:///" + os.path.join(self.tmpdir, "u.sqlite"),
                },
                config_from_env=False,
            )
        with self.app.app_context():
            user_db.create_all()
            add_user(name="user", password="secret", role=ROLE_EDITOR)
            self.user_id = str(get_guid("user"))
            for provider in ("one", "two"):
                create_oidc_account(self.user_id, provider, "sub")
            self.accounts = [a["id"] for a in get_user_oidc_accounts(self.user_id)]

    def test_the_last_account_survives_two_unlinks_at_once(self):
        barrier = threading.Barrier(2)
        results = []
        delete = user_db.session.delete

        def slow_delete(obj):
            # widen the window between the check and the delete
            threading.Event().wait(0.2)
            delete(obj)

        def unlink(account_id):
            with self.app.app_context():
                barrier.wait()
                try:
                    results.append(
                        unlink_oidc_account(self.user_id, account_id, allow_last=False)
                    )
                except Exception as exc:  # noqa: BLE001
                    results.append(exc)

        with patch.object(user_db.session, "delete", side_effect=slow_delete):
            threads = [
                threading.Thread(target=unlink, args=(account_id,))
                for account_id in self.accounts
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(sorted(map(str, results)), sorted([UNLINKED, UNLINK_LAST]))
        with self.app.app_context():
            self.assertEqual(len(get_user_oidc_accounts(self.user_id)), 1)
