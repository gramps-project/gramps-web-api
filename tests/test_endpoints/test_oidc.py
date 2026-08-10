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

from flask import redirect

from gramps_webapi.api.cache import persistent_cache

from . import BASE_URL, get_single_tree_test_client, get_test_client


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
        # auto_redirect follows the OIDC_AUTO_REDIRECT config option
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
        self.assertEqual(rv.status_code, 404)
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
            with patch(
                "gramps_webapi.api.resources.oidc.tree_exists", return_value=True
            ):
                rv = self.client.get(
                    BASE_URL + "/oidc/login/?provider=custom&tree=some_tree"
                )
            # The actual redirect handling depends on the OAuth library
            # We just verify the client method was called
            mock_oidc_client.authorize_redirect.assert_called_once()

    def test_oidc_callback_disabled(self):
        """Test OIDC callback endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/callback/?code=test123&provider=custom")
        self.assertEqual(rv.status_code, 404)
        data = rv.get_json()
        self.assertIn("not enabled", data["error"]["message"])

    def test_oidc_callback_iss_param_not_rejected(self):
        """Test that the iss parameter (sent by Keycloak per RFC 9207) is not rejected.

        Regression test: the flask-smorest migration dropped unknown=EXCLUDE from the
        callback endpoint, causing providers that include iss in the redirect URL to
        receive a 422 instead of being processed normally.
        """
        rv = self.client.get(
            BASE_URL
            + "/oidc/callback/?code=test123&provider=custom&iss=https%3A%2F%2Fkeycloak.example.com%2Frealms%2Fmyrealm"
        )
        # OIDC is disabled in the test environment, so we expect 404.
        # Before the fix, the unknown `iss` query param was rejected first, giving 422.
        self.assertNotEqual(rv.status_code, 422)
        self.assertEqual(rv.status_code, 404)

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
    @patch("gramps_webapi.api.resources.oidc.get_tree_id_and_permissions")
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_merges_id_token_claims(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """ID-token claims (e.g. roles) missing from userinfo are merged in.

        Providers such as Microsoft Entra return app roles / group memberships
        only in the ID token, not from the userinfo endpoint. They must still
        reach role mapping.
        """
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client

        # userinfo endpoint response lacks the roles claim...
        mock_userinfo = {
            "sub": "user123",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
        }
        # ...but the ID token (parsed by Authlib into token["userinfo"]) has it.
        # It also carries a conflicting email to prove the userinfo endpoint
        # value takes precedence over the ID-token claim.
        mock_token = {
            "access_token": "test_token",
            "userinfo": {
                "sub": "user123",
                "roles": ["admin"],
                "email": "idtoken@example.com",
            },
        }
        mock_oidc_client.authorize_access_token.return_value = mock_token
        mock_oidc_client.userinfo.return_value = mock_userinfo

        mock_create_user.return_value = "user-guid-123"
        mock_get_name.return_value = "testuser"
        mock_tree_and_perms.return_value = ("test_tree", {"ViewPrivate"})
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

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
                self.assertEqual(rv.status_code, 302)

                # The merged userinfo passed to user creation must include the
                # roles claim that only existed in the ID token.
                passed_userinfo = mock_create_user.call_args.args[0]
                self.assertEqual(passed_userinfo.get("roles"), ["admin"])
                # userinfo endpoint values take precedence over a conflicting
                # ID-token claim (endpoint email wins, not idtoken@example.com).
                self.assertEqual(passed_userinfo.get("email"), "test@example.com")

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name")
    @patch("gramps_webapi.api.resources.oidc.get_tree_id_and_permissions")
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_success(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
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
        mock_tree_and_perms.return_value = ("test_tree", {"EditObject", "ViewPrivate"})
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

                # Verify redirect location carries an exchange code
                self.assertIn("/oidc/complete", rv.location)
                self.assertIn("#code=", rv.location)

                # The tokens themselves must not travel back to the browser
                self.assertNotIn("Set-Cookie", rv.headers)
                self.assertNotIn(mock_get_tokens.return_value["refresh_token"], rv.location)

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
    @patch("gramps_webapi.api.resources.oidc.get_tree_id_and_permissions")
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_path_param_microsoft(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
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
        mock_tree_and_perms.return_value = ("test_tree", {"EditObject"})
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
    @patch("gramps_webapi.api.resources.oidc.get_tree_id_and_permissions")
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_microsoft_claims_options(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """A provider marked relax_issuer must skip ID token issuer validation."""
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
        mock_tree_and_perms.return_value = ("test_tree", {"EditObject"})
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        # relax_issuer comes from the provider metadata, not from a hardcoded
        # provider ID check in the request handler
        with (
            patch.dict(
                self.client.application.extensions,
                {"authlib.integrations.flask_client": mock_oauth},
                clear=False,
            ),
            patch(
                "gramps_webapi.api.resources.oidc.get_provider_config",
                return_value={"name": "Microsoft", "relax_issuer": True},
            ),
        ):
            with patch.dict(self.client.application.config, {"TREE": "test_tree"}):
                rv = self.client.get(
                    BASE_URL + "/oidc/callback/microsoft?code=auth_code&state=abc123"
                )
                self.assertEqual(rv.status_code, 302)  # Redirect response

                # Verify authorize_access_token was called with claims_options
                # to skip issuer validation
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
    @patch("gramps_webapi.api.resources.oidc.get_tree_id_and_permissions")
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_oidc_callback_backwards_compatible_query_param(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
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
        mock_tree_and_perms.return_value = ("test_tree", {"ViewPrivate"})
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
        """A disabled tree gives 503, via the same helper the token endpoint uses.

        The patches deliberately target token.py rather than the OIDC module, so
        that the real get_tree_id_and_permissions() runs and the two login paths
        are proven to share one implementation.
        """
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        mock_oidc_client.authorize_access_token.return_value = {
            "access_token": "test_token"
        }
        mock_oidc_client.userinfo.return_value = {"sub": "user123", "groups": []}

        T = "gramps_webapi.api.resources.token."
        with (
            patch(
                "gramps_webapi.api.resources.oidc.create_or_update_oidc_user",
                return_value="user123",
            ),
            patch("gramps_webapi.api.resources.oidc.get_name", return_value="testuser"),
            patch("gramps_webapi.api.resources.oidc.tree_exists", return_value=True),
            patch(T + "get_tree_id_or_none", return_value="disabled_tree"),
            patch(T + "get_permissions", return_value=set()),
            patch(T + "is_tree_disabled", return_value=True),
            patch.dict(
                self.client.application.extensions,
                {"authlib.integrations.flask_client": mock_oauth},
                clear=False,
            ),
        ):
            # Need to provide tree parameter since TREE_MULTI is enabled in test config
            rv = self.client.get(
                BASE_URL
                + "/oidc/callback/?code=auth_code&provider=custom&tree=disabled_tree"
            )

        self.assertEqual(rv.status_code, 503)
        self.assertIn("temporarily disabled", rv.get_json()["error"]["message"])


class TestOIDCMultiTree(unittest.TestCase):
    """Test cases for OIDC in a multi-tree installation.

    The tree cannot ride along on the redirect URI, because providers require
    the redirect URI to match the registered one exactly. It is carried in the
    session from /oidc/login/ to the callback instead.
    """

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_login_requires_tree(self, mock_providers, mock_oidc_enabled):
        """Multi-tree login without a tree fails at /oidc/login/, not later."""
        mock_oauth = MagicMock()
        mock_oauth.gramps_custom = MagicMock()
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/login/?provider=custom")
        self.assertEqual(rv.status_code, 422)
        self.assertIn("tree is required", rv.get_json()["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_login_rejects_unknown_tree(self, mock_providers, mock_oidc_enabled):
        """A login must not be able to create an account in a tree that does not exist."""
        mock_oauth = MagicMock()
        mock_oauth.gramps_custom = MagicMock()
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + "/oidc/login/?provider=custom&tree=no_such_tree"
            )
        self.assertEqual(rv.status_code, 422)
        self.assertIn("does not exist", rv.get_json()["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name", return_value="testuser")
    @patch(
        "gramps_webapi.api.resources.oidc.get_tree_id_and_permissions",
        return_value=("the_tree", {"EditObject"}),
    )
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_tree_survives_the_round_trip(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """The tree given at login reaches the callback with no query parameter.

        This is the regression test for multi-tree OIDC: the callback used to
        abort with "Tree is required" because nothing carried the tree across
        the redirect to the provider.
        """
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        # a real response, so that Flask can attach the session cookie to it
        mock_oidc_client.authorize_redirect.return_value = redirect(
            "https://idp.example.com/authorize"
        )
        mock_oidc_client.authorize_access_token.return_value = {
            "access_token": "test_token"
        }
        mock_oidc_client.userinfo.return_value = {"sub": "user123"}
        mock_create_user.return_value = "user-guid-123"
        mock_get_tokens.return_value = {
            "access_token": "jwt_access_token",
            "refresh_token": "jwt_refresh_token",
        }

        with (
            patch.dict(
                self.client.application.extensions,
                {"authlib.integrations.flask_client": mock_oauth},
                clear=False,
            ),
            patch("gramps_webapi.api.resources.oidc.tree_exists", return_value=True),
        ):
            # the test client keeps cookies between requests, like a browser
            rv = self.client.get(
                BASE_URL + "/oidc/login/?provider=custom&tree=the_tree"
            )
            self.assertEqual(rv.status_code, 302)

            # note: no tree query parameter, exactly as a provider would call it
            rv = self.client.get(BASE_URL + "/oidc/callback/custom?code=auth_code")

        self.assertEqual(rv.status_code, 302)
        self.assertIn("/oidc/complete", rv.location)
        # the tree from the login request was handed to user creation
        self.assertEqual(mock_create_user.call_args[0][1], "the_tree")

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_callback_without_login_is_refused(self, mock_providers, mock_oidc_enabled):
        """A callback with no tree in the session must not fall through."""
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        mock_oidc_client.authorize_access_token.return_value = {"access_token": "t"}
        mock_oidc_client.userinfo.return_value = {"sub": "user123"}

        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/callback/custom?code=auth_code")
        self.assertEqual(rv.status_code, 422)


class TestOIDCSingleTree(unittest.TestCase):
    """Test cases for OIDC in a single-tree installation."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_single_tree_test_client()

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_login_without_tree(self, mock_providers, mock_oidc_enabled):
        """No tree is needed, and none may be demanded."""
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        mock_oidc_client.authorize_redirect.return_value = redirect("https://idp/auth")

        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/login/?provider=custom")
        self.assertEqual(rv.status_code, 302)

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_login_with_the_configured_tree(self, mock_providers, mock_oidc_enabled):
        """Passing the configured tree is allowed.

        TREE holds the tree name in a single-tree setup, not the tree ID, so it
        must not be run through the tree ID existence check.
        """
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        mock_oidc_client.authorize_redirect.return_value = redirect("https://idp/auth")

        tree = self.client.application.config["TREE"]
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + f"/oidc/login/?provider=custom&tree={tree}"
            )
        self.assertEqual(rv.status_code, 302)

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    @patch("gramps_webapi.api.resources.oidc.create_or_update_oidc_user")
    @patch("gramps_webapi.api.resources.oidc.get_name", return_value="testuser")
    @patch(
        "gramps_webapi.api.resources.oidc.get_tree_id_and_permissions",
        return_value=("the_tree_id", set()),
    )
    @patch("gramps_webapi.api.resources.oidc.get_tokens")
    def test_configured_tree_name_is_not_stored_on_the_user(
        self,
        mock_get_tokens,
        mock_tree_and_perms,
        mock_get_name,
        mock_create_user,
        mock_providers,
        mock_oidc_enabled,
    ):
        """The tree *name* must never reach the user record.

        In a single-tree setup TREE is a name, while `users.tree` holds tree
        IDs. Storing the name there would make get_tree_id_or_none() hand back
        a name as if it were an ID - it only resolves the configured tree when
        the column is empty - so every later lookup would try to open a tree
        that does not exist, and a repeat login would be rejected as belonging
        to a different tree.
        """
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        mock_oidc_client.authorize_redirect.return_value = redirect("https://idp/auth")
        mock_oidc_client.authorize_access_token.return_value = {"access_token": "t"}
        mock_oidc_client.userinfo.return_value = {"sub": "user123"}
        mock_create_user.return_value = "user-guid"
        mock_get_tokens.return_value = {"access_token": "a", "refresh_token": "r"}

        tree_name = self.client.application.config["TREE"]
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + f"/oidc/login/?provider=custom&tree={tree_name}"
            )
            self.assertEqual(rv.status_code, 302)
            rv = self.client.get(BASE_URL + "/oidc/callback/custom?code=auth_code")

        self.assertEqual(rv.status_code, 302)
        # second positional argument of create_or_update_oidc_user is the tree
        stored_tree = mock_create_user.call_args[0][1]
        self.assertIsNone(stored_tree)
        self.assertNotEqual(stored_tree, tree_name)

    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True)
    @patch(
        "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
        return_value=["custom"],
    )
    def test_login_with_another_tree_is_refused(
        self, mock_providers, mock_oidc_enabled
    ):
        """A single-tree setup must not accept some other tree."""
        mock_oauth = MagicMock()
        mock_oauth.gramps_custom = MagicMock()
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(
                BASE_URL + "/oidc/login/?provider=custom&tree=some_other_tree"
            )
        self.assertEqual(rv.status_code, 422)


class TestOIDCCodeExchange(unittest.TestCase):
    """Test cases for the single-use exchange code and its redemption."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def _run_callback(self, frontend_url, id_token=None):
        """Run a successful callback and return the exchange code."""
        mock_oauth = MagicMock()
        mock_oidc_client = MagicMock()
        mock_oauth.gramps_custom = mock_oidc_client
        provider_token = {"access_token": "t"}
        if id_token:
            provider_token["id_token"] = id_token
        mock_oidc_client.authorize_access_token.return_value = provider_token
        mock_oidc_client.userinfo.return_value = {"sub": "user123"}

        with (
            patch(
                "gramps_webapi.api.resources.oidc.is_oidc_enabled", return_value=True
            ),
            patch(
                "gramps_webapi.api.resources.oidc.get_available_oidc_providers",
                return_value=["custom"],
            ),
            patch(
                "gramps_webapi.api.resources.oidc.create_or_update_oidc_user",
                return_value="user-guid",
            ),
            patch("gramps_webapi.api.resources.oidc.get_name", return_value="testuser"),
            patch(
                "gramps_webapi.api.resources.oidc.get_tree_id_and_permissions",
                return_value=("t", set()),
            ),
            patch(
                "gramps_webapi.api.resources.oidc.get_tokens",
                return_value={"access_token": "a", "refresh_token": "r"},
            ),
            patch("gramps_webapi.api.resources.oidc.tree_exists", return_value=True),
            patch.dict(
                self.client.application.extensions,
                {"authlib.integrations.flask_client": mock_oauth},
                clear=False,
            ),
            patch.dict(
                self.client.application.config,
                {"TREE": "t", "FRONTEND_URL": frontend_url, "BASE_URL": frontend_url},
            ),
        ):
            rv = self.client.get(
                BASE_URL + "/oidc/callback/custom?code=auth_code&tree=t"
            )
        self.assertEqual(rv.status_code, 302)
        return rv.location.partition("#code=")[2]

    def test_code_is_redeemed_exactly_once(self):
        """A replayed code must not yield a second set of tokens."""
        code = self._run_callback("https://app.example.com")

        rv = self.client.post(BASE_URL + "/oidc/tokens/", json={"code": code})
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertEqual(data["access_token"], "a")
        self.assertEqual(data["refresh_token"], "r")
        self.assertEqual(data["token_type"], "Bearer")

        rv = self.client.post(BASE_URL + "/oidc/tokens/", json={"code": code})
        self.assertEqual(rv.status_code, 400)
        self.assertIn("already been used", rv.get_json()["error"]["message"])

    def test_id_token_survives_the_exchange(self):
        """The id_token is needed later as id_token_hint on logout."""
        code = self._run_callback("https://app.example.com", id_token="id-1")
        rv = self.client.post(BASE_URL + "/oidc/tokens/", json={"code": code})
        self.assertEqual(rv.get_json()["id_token"], "id-1")

    def test_unsigned_code_is_rejected(self):
        """A guessed code carries no signature and cannot name a cache entry."""
        rv = self.client.post(
            BASE_URL + "/oidc/tokens/", json={"code": "not-a-real-code"}
        )
        self.assertEqual(rv.status_code, 400)
        self.assertIn("Invalid", rv.get_json()["error"]["message"])

    def test_expired_code_is_reported_as_expired(self):
        """Age is read from the signature, not from whether the entry survived."""
        code = self._run_callback("https://app.example.com")
        with patch(
            "gramps_webapi.api.resources.oidc.OIDC_CODE_TIMEOUT", -1
        ):
            rv = self.client.post(BASE_URL + "/oidc/tokens/", json={"code": code})
        self.assertEqual(rv.status_code, 400)
        self.assertIn("expired", rv.get_json()["error"]["message"])

    def test_lost_entry_names_the_unshared_cache(self):
        """A valid, unexpired code with no entry means the cache is not shared.

        This is what a per-worker cache looks like from the worker that did not
        handle the callback, and it must not be reported as an expired code.
        """
        code = self._run_callback("https://app.example.com")
        with self.client.application.app_context():
            persistent_cache.clear()

        rv = self.client.post(BASE_URL + "/oidc/tokens/", json={"code": code})
        self.assertEqual(rv.status_code, 500)
        self.assertIn("not shared", rv.get_json()["error"]["message"])


class TestOIDCLogoutEndpoint(unittest.TestCase):
    """Test cases for OIDC logout endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_oidc_logout_disabled(self):
        """Test OIDC logout endpoint when OIDC is disabled."""
        rv = self.client.get(BASE_URL + "/oidc/logout/?provider=google")
        self.assertEqual(rv.status_code, 404)
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
    def test_oidc_logout_incompletely_configured_provider(
        self, mock_oidc_enabled, mock_providers
    ):
        """A provider with no usable configuration is a client error, not a 500.

        get_available_oidc_providers() lists a built-in provider as soon as a
        client ID is set, but init_oidc() only registers a client once the
        secret is there too. /oidc/config/ does not advertise such a provider,
        so asking for it must be answered the same way as an unknown one.
        """
        mock_oidc_enabled.return_value = True
        mock_providers.return_value = ["google"]

        # init_oidc() registers the authlib extension whenever OIDC is enabled,
        # even when it then skips every provider, so the extension has to be
        # present for this to reproduce the real misconfiguration.
        mock_oauth = MagicMock()
        mock_oauth.gramps_google = None
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/logout/?provider=google")
        self.assertEqual(rv.status_code, 400)
        self.assertIn("not available", rv.get_json()["error"]["message"])

    @patch("gramps_webapi.api.resources.oidc.get_available_oidc_providers")
    @patch("gramps_webapi.api.resources.oidc.is_oidc_enabled")
    @patch("gramps_webapi.api.resources.oidc.get_provider_config")
    def test_oidc_logout_configured_but_unregistered_client(
        self, mock_provider_config, mock_oidc_enabled, mock_providers
    ):
        """A fully configured provider with no client really is a 500."""
        mock_oidc_enabled.return_value = True
        mock_providers.return_value = ["google"]
        mock_provider_config.return_value = {"name": "Google"}

        mock_oauth = MagicMock()
        mock_oauth.gramps_google = None
        with patch.dict(
            self.client.application.extensions,
            {"authlib.integrations.flask_client": mock_oauth},
            clear=False,
        ):
            rv = self.client.get(BASE_URL + "/oidc/logout/?provider=google")
        self.assertEqual(rv.status_code, 500)


class TestOIDCTokenClaims(unittest.TestCase):
    """Test cases for OIDC-specific JWT claims."""

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
