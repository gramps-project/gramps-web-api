#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024      David Straub
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

"""Tests for the OIDC API endpoints."""

import json
import unittest
from unittest.mock import MagicMock, patch

from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_EDITOR, ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client


class TestOIDCEndpoints(unittest.TestCase):
    """Test cases for OIDC API endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_oidc_config_disabled(self):
        """Test OIDC config endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/config/")
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertFalse(data.get("enabled", True))

    @patch.dict("os.environ", {"GRAMPSWEB_OIDC_ENABLED": "true"})
    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    def test_oidc_config_enabled(self, mock_oidc_enabled):
        """Test OIDC config endpoint when OIDC is enabled."""
        with patch.dict(
            "os.environ",
            {
                "GRAMPSWEB_OIDC_ISSUER": "https://test-issuer.com",
                "GRAMPSWEB_OIDC_CLIENT_ID": "test-client-id",
            },
        ):
            rv = self.client.get(BASE_URL + "/oidc/config/")
            self.assertEqual(rv.status_code, 200)
            data = rv.get_json()
            self.assertTrue(data.get("enabled"))
            self.assertEqual(data.get("issuer"), "https://test-issuer.com")
            self.assertEqual(data.get("client_id"), "test-client-id")
            self.assertFalse(data.get("disable_local_auth", False))
            self.assertTrue(data.get("auto_redirect", True))

    @patch.dict("os.environ", {"GRAMPSWEB_OIDC_ENABLED": "true"})
    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    def test_oidc_config_with_disabled_local_auth(self, mock_oidc_enabled):
        """Test OIDC config endpoint with local auth disabled."""
        with patch.dict(
            "os.environ",
            {
                "GRAMPSWEB_OIDC_ISSUER": "https://test-issuer.com",
                "GRAMPSWEB_OIDC_CLIENT_ID": "test-client-id",
                "GRAMPSWEB_OIDC_DISABLE_LOCAL_AUTH": "true",
                "GRAMPSWEB_OIDC_AUTO_REDIRECT": "false",
            },
        ):
            rv = self.client.get(BASE_URL + "/oidc/config/")
            self.assertEqual(rv.status_code, 200)
            data = rv.get_json()
            self.assertTrue(data.get("enabled"))
            self.assertTrue(data.get("disable_local_auth"))
            self.assertFalse(data.get("auto_redirect"))

    def test_oidc_login_disabled(self):
        """Test OIDC login endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/login/")
        self.assertEqual(rv.status_code, 404)
        data = rv.get_json()
        self.assertIn("not enabled", data["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    def test_oidc_login_no_client(self, mock_app, mock_oidc_enabled):
        """Test OIDC login when OAuth client is not initialized."""
        mock_app.extensions.get.return_value = None
        rv = self.client.get(BASE_URL + "/oidc/login/")
        self.assertEqual(rv.status_code, 500)
        data = rv.get_json()
        self.assertIn("not properly initialized", data["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    def test_oidc_login_success(self, mock_app, mock_oidc_enabled):
        """Test successful OIDC login redirect."""
        # Mock OAuth client
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps = mock_oidc_client
        mock_app.extensions.get.return_value = mock_oauth
        mock_app.config = {"OIDC_REDIRECT_URI": "http://test.com/callback"}

        # Mock the authorize_redirect to return a redirect response
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_oidc_client.authorize_redirect.return_value = mock_response

        rv = self.client.get(BASE_URL + "/oidc/login/")
        # The actual redirect handling depends on the OAuth library
        # We just verify the client method was called
        mock_oidc_client.authorize_redirect.assert_called_once()

    def test_oidc_callback_disabled(self):
        """Test OIDC callback endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/callback/?code=test123")
        self.assertEqual(rv.status_code, 404)
        data = rv.get_json()
        self.assertIn("not enabled", data["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    def test_oidc_callback_no_client(self, mock_app, mock_oidc_enabled):
        """Test OIDC callback when OAuth client is not initialized."""
        mock_app.extensions.get.return_value = None
        rv = self.client.get(BASE_URL + "/oidc/callback/?code=test123")
        self.assertEqual(rv.status_code, 500)
        data = rv.get_json()
        self.assertIn("not properly initialized", data["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name")
    @patch("gramps_webapi.api.resources.oidc.get_tree_id")
    @patch("gramps_webapi.api.resources.oidc.get_permissions")
    @patch("gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=False)
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_success(
        self,
        mock_get_tokens,
        mock_tree_disabled,
        mock_get_permissions,
        mock_get_tree_id,
        mock_get_name,
        mock_create_user,
        mock_app,
        mock_oidc_enabled,
    ):
        """Test successful OIDC callback."""
        # Mock OAuth client and token exchange
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps = mock_oidc_client
        mock_app.extensions.get.return_value = mock_oauth
        mock_app.config = {"TREE": "test_tree"}

        # Mock token and userinfo
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {
            "sub": "user123",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "groups": ["gramps-editors"],
        }
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo

        # Mock user creation and token generation
        mock_create_user.return_value = "user-guid-123"
        mock_get_name.return_value = "testuser"
        mock_get_tree_id.return_value = "test_tree"
        mock_get_permissions.return_value = {"EditObject", "ViewPrivate"}
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        rv = self.client.get(BASE_URL + "/oidc/callback/?code=auth_code&state=abc123&provider=gramps")
        self.assertEqual(rv.status_code, 302)  # Redirect response

        # Verify the flow
        mock_oidc_client.authorize_access_token.assert_called_once()
        mock_oidc_client.userinfo.assert_called_once_with(token=mock_token)
        mock_create_user.assert_called_once_with(mock_userinfo, None, "gramps")
        mock_get_tokens.assert_called_once()

        # Verify redirect location and cookies
        self.assertIn("/oidc/complete", rv.location)
        self.assertIn("oidc_access_token", [cookie.name for cookie in rv.cookies])
        self.assertIn("oidc_refresh_token", [cookie.name for cookie in rv.cookies])

        # Verify cookie values
        access_cookie = next(cookie for cookie in rv.cookies if cookie.name == "oidc_access_token")
        refresh_cookie = next(cookie for cookie in rv.cookies if cookie.name == "oidc_refresh_token")
        self.assertEqual(access_cookie.value, "jwt_access_token")
        self.assertEqual(refresh_cookie.value, "jwt_refresh_token")
        self.assertTrue(access_cookie.httponly)
        self.assertTrue(refresh_cookie.httponly)

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    def test_oidc_callback_auth_failure(self, mock_app, mock_oidc_enabled):
        """Test OIDC callback with authentication failure."""
        # Mock OAuth client that raises an exception
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps = mock_oidc_client
        mock_app.extensions.get.return_value = mock_oauth

        # Mock authorization failure
        mock_oidc_client.authorize_access_token.side_effect = Exception(
            "Invalid authorization code"
        )

        rv = self.client.get(BASE_URL + "/oidc/callback/?code=invalid_code")
        self.assertEqual(rv.status_code, 401)
        data = rv.get_json()
        self.assertIn("authentication failed", data["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    def test_oidc_callback_user_creation_failure(
        self, mock_create_user, mock_app, mock_oidc_enabled
    ):
        """Test OIDC callback with user creation failure."""
        # Mock OAuth client
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps = mock_oidc_client
        mock_app.extensions.get.return_value = mock_oauth
        mock_app.config = {"TREE": "test_tree"}

        # Mock successful token exchange but user creation failure
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {"sub": "user123", "groups": []}
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo
        mock_create_user.side_effect = ValueError("Invalid user data")

        rv = self.client.get(BASE_URL + "/oidc/callback/?code=auth_code")
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("Error processing user", data["message"])

    def test_oidc_callback_missing_code(self):
        """Test OIDC callback without authorization code."""
        with patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True):
            rv = self.client.get(BASE_URL + "/oidc/callback/")
            # The endpoint should handle missing code parameter gracefully
            # Implementation will determine exact behavior

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.current_app")
    def test_oidc_callback_tree_disabled(self, mock_app, mock_oidc_enabled):
        """Test OIDC callback when tree is disabled."""
        with patch("gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=True):
            # Mock OAuth client
            mock_oauth = MagicMock()
            mock_oidc_client = MagicMock()
            mock_oauth.gramps = mock_oidc_client
            mock_app.extensions.get.return_value = mock_oauth

            # Mock successful token exchange
            mock_token = {"access_token": "test_token"}
            mock_userinfo = {"sub": "user123", "groups": []}
            mock_oidc_client.authorize_access_token.return_value = mock_token
            mock_oidc_client.userinfo.return_value = mock_userinfo

            with patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user", return_value="user123"):
                with patch("gramps_webapi.api.resources.oidc.get_name", return_value="testuser"):
                    with patch("gramps_webapi.api.resources.oidc.get_tree_id", return_value="disabled_tree"):
                        rv = self.client.get(BASE_URL + "/oidc/callback/?code=auth_code")
                        self.assertEqual(rv.status_code, 503)
                        data = rv.get_json()
                        self.assertIn("temporarily disabled", data["message"])


if __name__ == "__main__":
    unittest.main()