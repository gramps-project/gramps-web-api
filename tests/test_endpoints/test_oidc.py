#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025           Alexander Bocken
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

import unittest
from unittest.mock import MagicMock, patch

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
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.get_provider_config")
    def test_oidc_config_enabled(
        self, mock_get_provider_config, mock_get_providers, mock_oidc_enabled
    ):
        """Test OIDC config endpoint when OIDC is enabled."""
        mock_get_provider_config.return_value = {"name": "Custom Provider"}
        rv = self.client.get(BASE_URL + "/oidc/config/")
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertTrue(data.get("enabled"))
        self.assertIn("providers", data)
        self.assertEqual(len(data["providers"]), 1)
        self.assertEqual(data["providers"][0]["id"], "custom")
        self.assertEqual(data["providers"][0]["name"], "Custom Provider")
        self.assertFalse(data.get("disable_local_auth", False))
        # auto_redirect defaults to True in the endpoint, but depends on app config
        self.assertIn("auto_redirect", data)

    @patch.dict("os.environ", {"GRAMPSWEB_OIDC_ENABLED": "true"})
    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.get_provider_config")
    def test_oidc_config_with_disabled_local_auth(
        self, mock_get_provider_config, mock_get_providers, mock_oidc_enabled
    ):
        """Test OIDC config endpoint with local auth disabled."""
        mock_get_provider_config.return_value = {"name": "Custom Provider"}

        self.client.application.config["BASE_URL"] = "http://localhost:5000"
        self.client.application.config["OIDC_DISABLE_LOCAL_AUTH"] = True
        self.client.application.config["OIDC_AUTO_REDIRECT"] = False

        rv = self.client.get(BASE_URL + "/oidc/config/")
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertTrue(data.get("enabled"))
        self.assertTrue(data.get("disable_local_auth"))
        self.assertFalse(data.get("auto_redirect"))

    def test_oidc_login_disabled(self):
        """Test OIDC login endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/login/?provider=custom")
        self.assertEqual(rv.status_code, 405)
        data = rv.get_json()
        self.assertIn("not enabled", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_oidc_login_no_client(self, mock_providers, mock_oidc_enabled):
        """Test OIDC login when OAuth client is not initialized."""
        # Patch the extensions dict on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": None},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/login/?provider=custom")
            self.assertEqual(rv.status_code, 500)
            data = rv.get_json()
            self.assertIn("not properly initialized", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_oidc_login_success(self, mock_providers, mock_oidc_enabled):
        """Test successful OIDC login redirect."""
        # Mock OAuth client
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client

        # Mock the authorize_redirect to return a redirect response
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_oidc_client.authorize_redirect.return_value = mock_response

        # Patch the extensions dict on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/login/?provider=custom")
            # The actual redirect handling depends on the OAuth library
            # We just verify the client method was called
            mock_oidc_client.authorize_redirect.assert_called_once()

    def test_oidc_callback_disabled(self):
        """Test OIDC callback endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/callback/?code=test123&provider=custom")
        self.assertEqual(rv.status_code, 405)
        data = rv.get_json()
        self.assertIn("not enabled", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_oidc_callback_no_client(self, mock_providers, mock_oidc_enabled):
        """Test OIDC callback when OAuth client is not initialized."""
        # Patch the extensions dict on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": None},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + "/oidc/callback/?code=test123&provider=custom"
            )
            self.assertEqual(rv.status_code, 500)
            data = rv.get_json()
            self.assertIn("not properly initialized", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
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
        mock_providers,
        mock_oidc_enabled,
    ):
        """Test successful OIDC callback."""
        # Mock OAuth client and token exchange
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client

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

        # Patch the extensions dict and config on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL
                    + "/oidc/callback/?code=auth_code&state=abc123&provider=custom"
                )
                self.assertEqual(rv.status_code, 302)  # Redirect response

                # Verify the flow
                mock_oidc_client.authorize_access_token.assert_called_once()
                mock_oidc_client.userinfo.assert_called_once_with(token=mock_token)
                mock_create_user.assert_called_once_with(mock_userinfo, None, "custom")
                mock_get_tokens.assert_called_once()

                # Verify redirect location
                self.assertIn("/oidc/complete", rv.location)

                # Verify cookies are set
                set_cookie_headers = rv.headers.getlist("Set-Cookie")
                self.assertTrue(
                    any("oidc_access_token" in cookie for cookie in set_cookie_headers)
                )
                self.assertTrue(
                    any("oidc_refresh_token" in cookie for cookie in set_cookie_headers)
                )

                # Verify HttpOnly flag is set
                access_token_cookie = next(
                    cookie
                    for cookie in set_cookie_headers
                    if "oidc_access_token" in cookie
                )
                refresh_token_cookie = next(
                    cookie
                    for cookie in set_cookie_headers
                    if "oidc_refresh_token" in cookie
                )
                self.assertIn("HttpOnly", access_token_cookie)
                self.assertIn("HttpOnly", refresh_token_cookie)

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_oidc_callback_auth_failure(self, mock_providers, mock_oidc_enabled):
        """Test OIDC callback with authentication failure."""
        # Mock OAuth client that raises an exception
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client

        # Mock authorization failure
        mock_oidc_client.authorize_access_token.side_effect = Exception(
            "Invalid authorization code"
        )

        # Patch the extensions dict on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + "/oidc/callback/?code=invalid_code&provider=custom"
            )
            self.assertEqual(rv.status_code, 401)
            data = rv.get_json()
            self.assertIn("authentication failed", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    def test_oidc_callback_user_creation_failure(
        self, mock_create_user, mock_providers, mock_oidc_enabled
    ):
        """Test OIDC callback with user creation failure."""
        # Mock OAuth client
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client

        # Mock successful token exchange but user creation failure
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {"sub": "user123", "groups": []}
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo
        mock_create_user.side_effect = ValueError("Invalid user data")

        # Patch the extensions dict and config on the test client's app
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL + "/oidc/callback/?code=auth_code&provider=custom"
                )
                self.assertEqual(rv.status_code, 400)
                data = rv.get_json()
                self.assertIn("Error processing user", data["error"]["message"])

    def test_oidc_callback_missing_code(self):
        """Test OIDC callback without authorization code."""
        with patch(
            "gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True
        ):
            rv = self.client.get(BASE_URL + "/oidc/callback/?provider=custom")
            # The endpoint should handle missing code parameter gracefully
            # Implementation will determine exact behavior

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["microsoft"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name")
    @patch("gramps_webapi.api.resources.oidc.get_tree_id")
    @patch("gramps_webapi.api.resources.oidc.get_permissions")
    @patch("gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=False)
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_path_param_microsoft(
        self,
        mock_get_tokens,
        mock_tree_disabled,
        mock_get_permissions,
        mock_get_tree_id,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """Test OIDC callback with path parameter (Microsoft-compatible URL)."""
        # Mock OAuth client and token exchange
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_microsoft = mock_oidc_client

        # Mock token and userinfo
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {
            "sub": "user123",
            "preferred_username": "testuser",
            "email": "test@example.com",
        }
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo

        # Mock user creation and token generation
        mock_create_user.return_value = "user-guid-123"
        mock_get_name.return_value = "testuser"
        mock_get_tree_id.return_value = "test_tree"
        mock_get_permissions.return_value = {"EditObject"}
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        # Test path-based URL (no query param for provider)
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL + "/oidc/callback/microsoft?code=auth_code&state=abc123"
                )
                self.assertEqual(rv.status_code, 302)  # Redirect response

                # Verify the flow worked with provider from path
                mock_create_user.assert_called_once_with(
                    mock_userinfo, None, "microsoft"
                )

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["microsoft"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name")
    @patch("gramps_webapi.api.resources.oidc.get_tree_id")
    @patch("gramps_webapi.api.resources.oidc.get_permissions")
    @patch("gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=False)
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_microsoft_claims_options(
        self,
        mock_get_tokens,
        mock_tree_disabled,
        mock_get_permissions,
        mock_get_tree_id,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """Test OIDC callback for Microsoft uses claims_options to skip issuer validation."""
        # Mock OAuth client and token exchange
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_microsoft = mock_oidc_client

        # Mock token and userinfo
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {
            "sub": "user123",
            "preferred_username": "testuser",
            "email": "test@example.com",
        }
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo

        # Mock user creation and token generation
        mock_create_user.return_value = "user-guid-123"
        mock_get_name.return_value = "testuser"
        mock_get_tree_id.return_value = "test_tree"
        mock_get_permissions.return_value = {"EditObject"}
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        # Test that Microsoft provider passes claims_options to skip issuer validation
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL + "/oidc/callback/microsoft?code=auth_code&state=abc123"
                )
                self.assertEqual(rv.status_code, 302)  # Redirect response

                # Verify authorize_access_token was called with claims_options
                # to skip issuer validation (needed for Microsoft OIDC)
                mock_oidc_client.authorize_access_token.assert_called_once_with(
                    claims_options={"iss": {"essential": False}}
                )

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["google"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name")
    @patch("gramps_webapi.api.resources.oidc.get_tree_id")
    @patch("gramps_webapi.api.resources.oidc.get_permissions")
    @patch("gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=False)
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_backwards_compatible_query_param(
        self,
        mock_get_tokens,
        mock_tree_disabled,
        mock_get_permissions,
        mock_get_tree_id,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """Test OIDC callback still works with legacy query parameter."""
        # Mock OAuth client and token exchange
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_google = mock_oidc_client

        # Mock token and userinfo
        mock_token = {"access_token": "test_token"}
        mock_userinfo = {
            "sub": "user123",
            "email": "test@gmail.com",
        }
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo

        # Mock user creation and token generation
        mock_create_user.return_value = "user-guid-456"
        mock_get_name.return_value = "testuser"
        mock_get_tree_id.return_value = "test_tree"
        mock_get_permissions.return_value = {"ViewPrivate"}
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        # Test legacy query-param based URL (backwards compatibility)
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL
                    + "/oidc/callback/?provider=google&code=auth_code&state=abc123"
                )
                self.assertEqual(rv.status_code, 302)  # Redirect response

                # Verify the flow worked with provider from query param
                mock_create_user.assert_called_once_with(mock_userinfo, None, "google")

                # Verify authorize_access_token was called without claims_options
                # (standard OIDC flow for non-Microsoft providers)
                mock_oidc_client.authorize_access_token.assert_called_once_with()

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_oidc_callback_tree_disabled(self, mock_providers, mock_oidc_enabled):
        """Test OIDC callback when tree is disabled."""
        with patch(
            "gramps_webapi.api.resources.oidc.is_tree_disabled", return_value=True
        ):
            # Mock OAuth client
            mock_oauth = MagicMock()
            mock_oidc_client = MagicMock()
            mock_oauth.gramps_custom = mock_oidc_client

            # Mock successful token exchange
            mock_token = {"access_token": "test_token"}
            mock_userinfo = {"sub": "user123", "groups": []}
            mock_oidc_client.authorize_access_token.return_value = mock_token
            mock_oidc_client.userinfo.return_value = mock_userinfo

            with patch(
                "gramps_webapi.api.resources.oidc.create_or_update_oidc_user",
                return_value="user123",
            ):
                with patch(
                    "gramps_webapi.api.resources.oidc.get_name", return_value="testuser"
                ):
                    with patch(
                        "gramps_webapi.api.resources.oidc.get_tree_id",
                        return_value="disabled_tree",
                    ):
                        # Patch the extensions dict on the test client's app
                        with patch.dict(
                            self.client.application.extensions,
                            {"authlib.integrations.flask_client": mock_oauth},
                            clear=False,
                        ):
                            # Need to provide tree parameter since TREE_MULTI is enabled in test config
                            rv = self.client.get(
                                BASE_URL
                                + "/oidc/callback/?code=auth_code&provider=custom&tree=disabled_tree"
                            )
                            self.assertEqual(rv.status_code, 503)
                            data = rv.get_json()
                            self.assertIn(
                                "temporarily disabled", data["error"]["message"]
                            )


class TestOIDCLogoutEndpoint(unittest.TestCase):
    """Test cases for OIDC logout endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_oidc_logout_disabled(self):
        """Test OIDC logout endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/logout/?provider=google")
        self.assertEqual(rv.status_code, 405)
        data = rv.get_json()
        self.assertIn("not enabled", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.get_available_oidc_providers")
    def test_oidc_logout_invalid_provider(self, mock_providers, mock_oidc_enabled):
        """Test OIDC logout with invalid provider."""
        mock_providers.return_value = ["google", "microsoft"]

        rv = self.client.get(BASE_URL + "/oidc/logout/?provider=invalid")
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("not available", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.get_available_oidc_providers")
    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled")
    def test_oidc_logout_no_client(self, mock_oidc_enabled, mock_providers):
        """Test OIDC logout when OAuth client is not initialized."""
        mock_oidc_enabled.return_value = True
        mock_providers.return_value = ["google"]

        rv = self.client.get(BASE_URL + "/oidc/logout/?provider=google")
        # Should return 500 when client not found
        self.assertEqual(rv.status_code, 500)


class TestOIDCBackchannelLogout(unittest.TestCase):
    """Test cases for OIDC backchannel logout endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def tearDown(self):
        """Clear blocklist after each test."""
        from gramps_webapi.auth.token_blocklist import _BLOCKLIST, _BLOCKLIST_TIMESTAMPS

        _BLOCKLIST.clear()
        _BLOCKLIST_TIMESTAMPS.clear()

    def test_backchannel_logout_disabled(self):
        """Test backchannel logout when OIDC is disabled."""
        rv = self.client.post(BASE_URL + "/oidc/backchannel-logout/")
        self.assertEqual(rv.status_code, 405)
        data = rv.get_json()
        self.assertIn("not enabled", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    def test_backchannel_logout_missing_token(self, mock_oidc_enabled):
        """Test backchannel logout with missing logout_token."""
        rv = self.client.post(BASE_URL + "/oidc/backchannel-logout/")
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("logout_token is required", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    def test_backchannel_logout_invalid_token(self, mock_oidc_enabled):
        """Test backchannel logout with invalid JWT."""
        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "invalid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("Invalid logout_token", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    def test_backchannel_logout_missing_sub_and_sid(
        self, mock_jwt_decode, mock_oidc_enabled
    ):
        """Test backchannel logout token without sub or sid claim."""
        mock_jwt_decode.return_value = {
            "iss": "https://issuer.com",
            "aud": "client-id",
            "jti": "logout-jti-123",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("must contain either sub or sid", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    def test_backchannel_logout_with_nonce(self, mock_jwt_decode, mock_oidc_enabled):
        """Test backchannel logout token with nonce (invalid per spec)."""
        mock_jwt_decode.return_value = {
            "sub": "user123",
            "nonce": "some-nonce",
            "jti": "logout-jti-123",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("must not contain nonce", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    def test_backchannel_logout_missing_event_type(
        self, mock_jwt_decode, mock_oidc_enabled
    ):
        """Test backchannel logout token without required event type."""
        mock_jwt_decode.return_value = {
            "sub": "user123",
            "events": {},
            "jti": "logout-jti-123",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 400)
        data = rv.get_json()
        self.assertIn("missing required event type", data["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    @patch("gramps_webapi.api.resources.oidc.add_jti_to_blocklist")
    def test_backchannel_logout_valid_token(
        self, mock_add_to_blocklist, mock_jwt_decode, mock_oidc_enabled
    ):
        """Test backchannel logout with valid logout_token."""
        mock_jwt_decode.return_value = {
            "sub": "user123",
            "sid": "session-456",
            "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            "jti": "logout-jti-123",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 200)

        # Verify JTI was added to blocklist
        mock_add_to_blocklist.assert_called_once_with("logout-jti-123")

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    @patch("gramps_webapi.api.resources.oidc.add_jti_to_blocklist")
    def test_backchannel_logout_with_sub_only(
        self, mock_add_to_blocklist, mock_jwt_decode, mock_oidc_enabled
    ):
        """Test backchannel logout with only sub claim (no sid)."""
        mock_jwt_decode.return_value = {
            "sub": "user123",
            "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            "jti": "logout-jti-456",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 200)
        mock_add_to_blocklist.assert_called_once_with("logout-jti-456")

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch("gramps_webapi.api.resources.oidc.jwt.decode")
    @patch("gramps_webapi.api.resources.oidc.add_jti_to_blocklist")
    def test_backchannel_logout_with_sid_only(
        self, mock_add_to_blocklist, mock_jwt_decode, mock_oidc_enabled
    ):
        """Test backchannel logout with only sid claim (no sub)."""
        mock_jwt_decode.return_value = {
            "sid": "session-789",
            "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
            "jti": "logout-jti-789",
        }

        rv = self.client.post(
            BASE_URL + "/oidc/backchannel-logout/",
            data={"logout_token": "valid.jwt.token"},
        )
        self.assertEqual(rv.status_code, 200)
        mock_add_to_blocklist.assert_called_once_with("logout-jti-789")


class TestTokenBlocklist(unittest.TestCase):
    """Test cases for token blocklist functionality."""

    def setUp(self):
        """Clear blocklist before each test."""
        from gramps_webapi.auth.token_blocklist import _BLOCKLIST, _BLOCKLIST_TIMESTAMPS

        _BLOCKLIST.clear()
        _BLOCKLIST_TIMESTAMPS.clear()

    def test_add_jti_to_blocklist(self):
        """Test adding a JTI to the blocklist."""
        from gramps_webapi.auth.token_blocklist import (
            add_jti_to_blocklist,
            is_jti_blocklisted,
            get_blocklist_size,
        )

        jti = "test-jti-123"
        add_jti_to_blocklist(jti)

        self.assertTrue(is_jti_blocklisted(jti))
        self.assertEqual(get_blocklist_size(), 1)

    def test_is_jti_not_blocklisted(self):
        """Test checking a JTI that is not blocklisted."""
        from gramps_webapi.auth.token_blocklist import is_jti_blocklisted

        self.assertFalse(is_jti_blocklisted("non-existent-jti"))

    def test_cleanup_expired_jtis_no_expiration(self):
        """Test cleanup when no JTIs have expired."""
        from gramps_webapi.auth.token_blocklist import (
            add_jti_to_blocklist,
            cleanup_expired_jtis,
            get_blocklist_size,
        )

        add_jti_to_blocklist("recent-jti")
        removed = cleanup_expired_jtis(max_age_hours=24)

        self.assertEqual(removed, 0)
        self.assertEqual(get_blocklist_size(), 1)

    def test_cleanup_expired_jtis_with_expiration(self):
        """Test cleanup removes old JTIs."""
        from datetime import datetime, timedelta
        from gramps_webapi.auth.token_blocklist import (
            add_jti_to_blocklist,
            cleanup_expired_jtis,
            is_jti_blocklisted,
            get_blocklist_size,
            _BLOCKLIST_TIMESTAMPS,
        )

        jti = "old-jti"
        add_jti_to_blocklist(jti)

        # Manually backdate timestamp to 25 hours ago
        _BLOCKLIST_TIMESTAMPS[jti] = datetime.now() - timedelta(hours=25)

        removed = cleanup_expired_jtis(max_age_hours=24)

        self.assertEqual(removed, 1)
        self.assertFalse(is_jti_blocklisted(jti))
        self.assertEqual(get_blocklist_size(), 0)

    def test_oidc_provider_in_token_claims(self):
        """Test that OIDC provider is included in token claims."""
        from gramps_webapi.api.resources.token import get_tokens

        with patch(
            "gramps_webapi.api.resources.token.create_access_token"
        ) as mock_access:
            with patch(
                "gramps_webapi.api.resources.token.create_refresh_token"
            ) as mock_refresh:
                get_tokens(
                    user_id="test-user",
                    permissions=["ViewPrivate"],
                    tree_id="test-tree",
                    include_refresh=True,
                    fresh=True,
                    oidc_provider="google",
                )

                # Check that create_access_token was called with oidc_provider in claims
                call_args = mock_access.call_args
                additional_claims = call_args.kwargs.get("additional_claims", {})

                self.assertIn("oidc_provider", additional_claims)
                self.assertEqual(additional_claims["oidc_provider"], "google")
