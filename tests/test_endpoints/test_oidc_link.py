#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025           Gramps Web API Contributors
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

"""Tests for OIDC account linking functionality."""

import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import (
    User,
    add_user,
    create_oidc_account,
    delete_oidc_account,
    delete_user,
    get_guid,
    get_oidc_account,
    get_pwhash,
    get_user_oidc_accounts,
    link_oidc_account,
    user_db,
)
from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_MEMBER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

from . import BASE_URL
from .util import fetch_header


class TestOIDCAccountLinking(unittest.TestCase):
    """Test cases for OIDC account linking."""

    def setUp(self):
        self.name = "Test OIDC Link"
        self.dbman = CLIDbManager(DbState())
        dbpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)

        # Create app with OIDC enabled
        with patch.dict(
            "os.environ",
            {
                ENV_CONFIG_FILE: TEST_AUTH_CONFIG,
                "OIDC_ENABLED": "true",
                "OIDC_GOOGLE_CLIENT_ID": "test-client-id",
                "OIDC_GOOGLE_CLIENT_SECRET": "test-client-secret",
            },
        ):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()

        with self.app.app_context():
            user_db.create_all()
            # Create a password-based user
            add_user(
                name="passworduser",
                password="testpassword",
                email="password@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
            # Create another password user
            add_user(
                name="user2",
                password="testpassword",
                email="user2@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_link_oidc_account_function(self):
        """Test the link_oidc_account function directly."""
        with self.app.app_context():
            user_id = get_guid("passworduser")

            # Link an OIDC account
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-123",
                email="user@example.com",
            )

            # Verify the link was created
            linked_user = get_oidc_account("google", "google-subject-123")
            assert linked_user == user_id

            # Verify the user has the linked account
            accounts = get_user_oidc_accounts(user_id)
            assert len(accounts) == 1
            assert accounts[0]["provider_id"] == "google"
            assert accounts[0]["subject_id"] == "google-subject-123"

    def test_link_oidc_account_duplicate(self):
        """Test that linking a duplicate OIDC account raises an error."""
        with self.app.app_context():
            user_id = get_guid("passworduser")
            user2_id = get_guid("user2")

            # Link an OIDC account to first user
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-duplicate",
                email="user@example.com",
            )

            # Try to link the same OIDC account to second user - should fail
            with self.assertRaises(ValueError) as context:
                link_oidc_account(
                    user_id=user2_id,
                    provider_id="google",
                    subject_id="google-subject-duplicate",
                    email="user2@example.com",
                )
            assert "already linked to another user" in str(context.exception)

    def test_delete_oidc_account_function(self):
        """Test the delete_oidc_account function directly."""
        with self.app.app_context():
            user_id = get_guid("passworduser")

            # Link an OIDC account
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-delete",
                email="user@example.com",
            )

            # Verify it exists
            accounts = get_user_oidc_accounts(user_id)
            assert len(accounts) == 1

            # Delete the account
            result = delete_oidc_account(user_id, "google")
            assert result is True

            # Verify it's gone
            accounts = get_user_oidc_accounts(user_id)
            assert len(accounts) == 0

            # Trying to delete again should return False
            result = delete_oidc_account(user_id, "google")
            assert result is False

    def test_delete_oidc_account_wrong_user(self):
        """Test that deleting an OIDC account from wrong user returns False."""
        with self.app.app_context():
            user_id = get_guid("passworduser")
            user2_id = get_guid("user2")

            # Link an OIDC account to first user
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-wronguser",
                email="user@example.com",
            )

            # Try to delete from second user - should return False
            result = delete_oidc_account(user2_id, "google")
            assert result is False

            # Original account should still exist
            accounts = get_user_oidc_accounts(user_id)
            assert len(accounts) == 1

    def test_list_oidc_accounts_endpoint(self):
        """Test the GET /api/oidc/accounts/ endpoint."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "passworduser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        with self.app.app_context():
            user_id = get_guid("passworduser")

            # Initially no OIDC accounts
            rv = self.client.get(
                BASE_URL + "/oidc/accounts/",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert rv.status_code == 200
            assert rv.json["oidc_accounts"] == []
            assert rv.json["account_source"] == "Local"

            # Link an OIDC account
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-list",
                email="user@example.com",
            )

        # Now should have one account
        rv = self.client.get(
            BASE_URL + "/oidc/accounts/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 200
        assert len(rv.json["oidc_accounts"]) == 1
        assert rv.json["oidc_accounts"][0]["provider_id"] == "google"

    def test_list_oidc_accounts_unauthenticated(self):
        """Test that unauthenticated requests are rejected."""
        rv = self.client.get(BASE_URL + "/oidc/accounts/")
        assert rv.status_code == 401

    def test_unlink_oidc_account_endpoint(self):
        """Test the DELETE /api/oidc/accounts/<provider_id>/ endpoint."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "passworduser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        with self.app.app_context():
            user_id = get_guid("passworduser")
            # Link an OIDC account
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-unlink",
                email="user@example.com",
            )

        # Unlink the account
        rv = self.client.delete(
            BASE_URL + "/oidc/accounts/google/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 204

        # Verify it's gone
        with self.app.app_context():
            accounts = get_user_oidc_accounts(user_id)
            assert len(accounts) == 0

    def test_unlink_oidc_account_not_linked(self):
        """Test unlinking a provider that isn't linked."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "passworduser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Try to unlink a provider that's not linked
        rv = self.client.delete(
            BASE_URL + "/oidc/accounts/google/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 404

    def test_unlink_oidc_account_unauthenticated(self):
        """Test that unauthenticated unlink requests are rejected."""
        rv = self.client.delete(BASE_URL + "/oidc/accounts/google/")
        assert rv.status_code == 401

    def test_unlink_only_auth_method_prevented(self):
        """Test that unlinking the only auth method is prevented."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "passworduser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        with self.app.app_context():
            user_id = get_guid("passworduser")

            # This user has a password account, so they should be able to unlink
            # (they still have password auth as fallback)
            link_oidc_account(
                user_id=user_id,
                provider_id="google",
                subject_id="google-subject-only",
                email="user@example.com",
            )

            # Verify user has password
            user_obj = user_db.session.get(User, user_id)
            assert user_obj.pwhash != ""

        # Should succeed because user still has password auth
        rv = self.client.delete(
            BASE_URL + "/oidc/accounts/google/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 204


class TestOIDCLinkEndpoint(unittest.TestCase):
    """Test cases for the OIDC link initiation endpoint."""

    def setUp(self):
        self.name = "Test OIDC Link Init"
        self.dbman = CLIDbManager(DbState())
        dbpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)

        with patch.dict(
            "os.environ",
            {
                ENV_CONFIG_FILE: TEST_AUTH_CONFIG,
                "OIDC_ENABLED": "true",
                "OIDC_GOOGLE_CLIENT_ID": "test-client-id",
                "OIDC_GOOGLE_CLIENT_SECRET": "test-client-secret",
            },
        ):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()

        with self.app.app_context():
            user_db.create_all()
            add_user(
                name="testuser",
                password="testpassword",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def test_link_endpoint_requires_auth(self):
        """Test that the link endpoint requires authentication."""
        rv = self.client.post(
            BASE_URL + "/oidc/link/",
            query_string={"provider": "google", "password": "testpassword"},
        )
        assert rv.status_code == 401

    def test_link_endpoint_requires_valid_password(self):
        """Test that the link endpoint requires correct password."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Try with wrong password
        rv = self.client.post(
            BASE_URL + "/oidc/link/",
            query_string={"provider": "google", "password": "wrongpassword"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 401

    def test_link_endpoint_requires_provider(self):
        """Test that the link endpoint requires provider parameter."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Try without provider
        rv = self.client.post(
            BASE_URL + "/oidc/link/",
            query_string={"password": "testpassword"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400

    def test_link_endpoint_requires_password(self):
        """Test that the link endpoint requires password parameter."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Try without password
        rv = self.client.post(
            BASE_URL + "/oidc/link/",
            query_string={"provider": "google"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400

    @patch("gramps_webapi.api.resources.oidc.OAuth")
    def test_link_endpoint_redirects_to_provider(self, mock_oauth_class):
        """Test that link endpoint redirects to OIDC provider."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Mock the OAuth client
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_oidc_client.authorize_redirect.return_value = mock_redirect
        mock_oauth.gramps_google = mock_oidc_client
        mock_oauth_class.return_value = mock_oauth

        rv = self.client.post(
            BASE_URL + "/oidc/link/",
            query_string={"provider": "google", "password": "testpassword"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should redirect
        assert rv.status_code == 302


class TestOIDCLinkCallbackEndpoint(unittest.TestCase):
    """Test cases for the OIDC link callback endpoint."""

    def setUp(self):
        self.name = "Test OIDC Link Callback"
        self.dbman = CLIDbManager(DbState())
        dbpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.tree = os.path.basename(dbpath)

        with patch.dict(
            "os.environ",
            {
                ENV_CONFIG_FILE: TEST_AUTH_CONFIG,
                "OIDC_ENABLED": "true",
                "OIDC_GOOGLE_CLIENT_ID": "test-client-id",
                "OIDC_GOOGLE_CLIENT_SECRET": "test-client-secret",
            },
        ):
            self.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        self.client = self.app.test_client()

        with self.app.app_context():
            user_db.create_all()
            add_user(
                name="testuser",
                password="testpassword",
                email="test@example.com",
                role=ROLE_MEMBER,
                tree=self.tree,
            )
        self.ctx = self.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.dbman.remove_database(self.name)

    def _create_link_state(self, user_id: str, password_hash: str) -> str:
        """Create a properly encoded state parameter for linking."""
        state_data = {
            "action": "link",
            "user_id": user_id,
            "password_hash": password_hash,
        }
        state_json = json.dumps(state_data)
        state_encoded = base64.urlsafe_b64encode(state_json.encode()).decode()
        return state_encoded

    def test_link_callback_requires_auth(self):
        """Test that the link callback requires authentication."""
        state = self._create_link_state("test-id", "test-hash")
        rv = self.client.get(
            BASE_URL + "/oidc/link-callback/google/",
            query_string={"state": state, "code": "test-code"},
        )
        assert rv.status_code == 401

    def test_link_callback_requires_state(self):
        """Test that the link callback requires state parameter."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        rv = self.client.get(
            BASE_URL + "/oidc/link-callback/google/",
            query_string={"code": "test-code"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400

    def test_link_callback_validates_user_match(self):
        """Test that the link callback validates user in state matches current user."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Create state with wrong user ID
        with self.app.app_context():
            user_id = get_guid("testuser")
            wrong_id = "00000000-0000-0000-0000-000000000000"
            pwhash = get_pwhash("testuser")

        state = self._create_link_state(wrong_id, pwhash)

        rv = self.client.get(
            BASE_URL + "/oidc/link-callback/google/",
            query_string={"state": state, "code": "test-code"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 403

    def test_link_callback_validates_password(self):
        """Test that the link callback validates password hash."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Create state with wrong password hash
        with self.app.app_context():
            user_id = get_guid("testuser")

        state = self._create_link_state(user_id, "wrong-hash")

        rv = self.client.get(
            BASE_URL + "/oidc/link-callback/google/",
            query_string={"state": state, "code": "test-code"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 403

    def test_link_callback_rejects_non_link_action(self):
        """Test that the link callback rejects state with non-link action."""
        # Login first
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "testuser", "password": "testpassword"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]

        # Create state with wrong action
        with self.app.app_context():
            user_id = get_guid("testuser")
            pwhash = get_pwhash("testuser")

        state_data = {
            "action": "login",  # Wrong action
            "user_id": user_id,
            "password_hash": pwhash,
        }
        state_json = json.dumps(state_data)
        state = base64.urlsafe_b64encode(state_json.encode()).decode()

        rv = self.client.get(
            BASE_URL + "/oidc/link-callback/google/",
            query_string={"state": state, "code": "test-code"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rv.status_code == 400


if __name__ == "__main__":
    unittest.main()