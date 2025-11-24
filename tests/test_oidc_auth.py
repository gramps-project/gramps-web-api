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

"""Tests for OIDC authentication logic."""

import pytest
from unittest.mock import MagicMock, patch

from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_DISABLED,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.auth.oidc import (
    BUILTIN_PROVIDERS,
    PROVIDER_CUSTOM,
    create_or_update_oidc_user,
    get_available_oidc_providers,
    get_provider_config,
    get_role_from_claims,
    init_oidc,
)


class TestGetRoleFromClaims:
    """Test cases for get_role_from_claims function."""

    def test_no_role_mapping_configured(self):
        """Test when no role mapping is configured - should return None to preserve existing roles."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = ""

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            user_claims = {"groups": ["some-group"]}
            role = get_role_from_claims(user_claims)
            assert role is None

    def test_empty_groups_with_mapping(self):
        """Test role mapping with empty groups list."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-group",
            "OIDC_GROUP_EDITOR": "editor-group",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            user_claims = {"groups": []}
            role = get_role_from_claims(user_claims)
            assert role == ROLE_DISABLED

    def test_no_matching_groups(self):
        """Test role mapping with no matching groups."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-group",
            "OIDC_GROUP_EDITOR": "editor-group",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            user_claims = {"groups": ["unknown-group", "another-unknown"]}
            role = get_role_from_claims(user_claims)
            assert role == ROLE_DISABLED

    def test_single_role_match(self):
        """Test role mapping with single matching group."""
        mock_app = MagicMock()

        # Test admin role
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-group",
        }.get(key, default)
        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            assert get_role_from_claims({"groups": ["admin-group"]}) == ROLE_ADMIN

        # Test editor role
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_EDITOR": "editor-group",
        }.get(key, default)
        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            assert get_role_from_claims({"groups": ["editor-group"]}) == ROLE_EDITOR

        # Test member role
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_MEMBER": "member-group",
        }.get(key, default)
        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            assert get_role_from_claims({"groups": ["member-group"]}) == ROLE_MEMBER

    def test_multiple_matches_highest_precedence_wins(self):
        """Test role mapping with multiple matching groups - highest precedence wins."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-group",
            "OIDC_GROUP_OWNER": "owner-group",
            "OIDC_GROUP_EDITOR": "editor-group",
            "OIDC_GROUP_CONTRIBUTOR": "contributor-group",
            "OIDC_GROUP_MEMBER": "member-group",
            "OIDC_GROUP_GUEST": "guest-group",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            # Admin (5) should win over all others
            role = get_role_from_claims(
                {"groups": ["member-group", "admin-group", "editor-group"]}
            )
            assert role == ROLE_ADMIN

            # Owner (4) should win over lower roles
            role = get_role_from_claims(
                {"groups": ["member-group", "owner-group", "contributor-group"]}
            )
            assert role == ROLE_OWNER

            # Editor (3) should win over lower roles
            role = get_role_from_claims(
                {"groups": ["member-group", "editor-group", "guest-group"]}
            )
            assert role == ROLE_EDITOR

    def test_case_sensitivity(self):
        """Test role mapping is case-sensitive."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "Admin-Group",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            assert get_role_from_claims({"groups": ["Admin-Group"]}) == ROLE_ADMIN
            assert get_role_from_claims({"groups": ["admin-group"]}) == ROLE_DISABLED
            assert get_role_from_claims({"groups": ["ADMIN-GROUP"]}) == ROLE_DISABLED

    def test_custom_role_claim(self):
        """Test using custom role claim (not 'groups')."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-role",
            "OIDC_GROUP_EDITOR": "editor-role",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            # Test with 'roles' claim
            user_claims = {"roles": ["admin-role", "other-role"]}
            role = get_role_from_claims(user_claims, role_claim="roles")
            assert role == ROLE_ADMIN

    def test_nested_role_claim(self):
        """Test using nested role claim like 'realm_access.roles'."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-role",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            user_claims = {"realm_access": {"roles": ["admin-role", "other-role"]}}
            role = get_role_from_claims(user_claims, role_claim="realm_access.roles")
            assert role == ROLE_ADMIN

    def test_string_claim_value(self):
        """Test handling claim value as string instead of list."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_GROUP_ADMIN": "admin-group",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            user_claims = {"groups": "admin-group"}  # String instead of list
            role = get_role_from_claims(user_claims)
            assert role == ROLE_ADMIN


class TestGetAvailableOidcProviders:
    """Test cases for get_available_oidc_providers function."""

    def test_no_providers_configured(self):
        """Test when no providers are configured."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = None

        providers = get_available_oidc_providers(mock_app)
        assert providers == []

    def test_single_builtin_provider(self):
        """Test with single built-in provider configured."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_GOOGLE_CLIENT_ID": "google-client-id",
        }.get(key, default)

        providers = get_available_oidc_providers(mock_app)
        assert "google" in providers
        assert "microsoft" not in providers
        assert "custom" not in providers

    def test_multiple_builtin_providers(self):
        """Test with multiple built-in providers configured."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_GOOGLE_CLIENT_ID": "google-client-id",
            "OIDC_MICROSOFT_CLIENT_ID": "microsoft-client-id",
            "OIDC_GITHUB_CLIENT_ID": "github-client-id",
        }.get(key, default)

        providers = get_available_oidc_providers(mock_app)
        assert "google" in providers
        assert "microsoft" in providers
        assert "github" in providers
        assert len(providers) == 3

    def test_custom_provider(self):
        """Test custom provider configuration."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_CLIENT_ID": "custom-client-id",
            "OIDC_ISSUER": "https://custom-issuer.com",
        }.get(key, default)

        providers = get_available_oidc_providers(mock_app)
        assert PROVIDER_CUSTOM in providers
        assert len(providers) == 1

    def test_custom_and_builtin_providers(self):
        """Test mix of custom and built-in providers."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_GOOGLE_CLIENT_ID": "google-client-id",
            "OIDC_CLIENT_ID": "custom-client-id",
            "OIDC_ISSUER": "https://custom-issuer.com",
        }.get(key, default)

        providers = get_available_oidc_providers(mock_app)
        assert "google" in providers
        assert PROVIDER_CUSTOM in providers
        assert len(providers) == 2

    def test_custom_provider_missing_issuer(self):
        """Test custom provider with missing issuer is not detected."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_CLIENT_ID": "custom-client-id",
            # Missing OIDC_ISSUER
        }.get(key, default)

        providers = get_available_oidc_providers(mock_app)
        assert PROVIDER_CUSTOM not in providers


class TestGetProviderConfig:
    """Test cases for get_provider_config function."""

    def test_google_provider_config(self):
        """Test getting Google provider configuration."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_GOOGLE_CLIENT_ID": "google-client-id",
            "OIDC_GOOGLE_CLIENT_SECRET": "google-secret",
        }.get(key, default)

        config = get_provider_config("google", mock_app)
        assert config is not None
        assert config["client_id"] == "google-client-id"
        assert config["client_secret"] == "google-secret"
        assert config["issuer"] == "https://accounts.google.com"
        assert config["username_claim"] == "email"

    def test_microsoft_provider_config(self):
        """Test getting Microsoft provider configuration."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_MICROSOFT_CLIENT_ID": "ms-client-id",
            "OIDC_MICROSOFT_CLIENT_SECRET": "ms-secret",
        }.get(key, default)

        config = get_provider_config("microsoft", mock_app)
        assert config is not None
        assert config["client_id"] == "ms-client-id"
        assert config["issuer"] == "https://login.microsoftonline.com/common/v2.0"
        assert config["username_claim"] == "preferred_username"

    def test_github_provider_config(self):
        """Test getting GitHub provider configuration."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_GITHUB_CLIENT_ID": "github-client-id",
            "OIDC_GITHUB_CLIENT_SECRET": "github-secret",
        }.get(key, default)

        config = get_provider_config("github", mock_app)
        assert config is not None
        assert config["client_id"] == "github-client-id"
        assert config["auth_url"] == "https://github.com/login/oauth/authorize"
        assert config["token_url"] == "https://github.com/login/oauth/access_token"
        assert config["username_claim"] == "login"

    def test_custom_provider_config(self):
        """Test getting custom provider configuration."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_CLIENT_ID": "custom-client-id",
            "OIDC_CLIENT_SECRET": "custom-secret",
            "OIDC_ISSUER": "https://custom-issuer.com",
            "OIDC_SCOPES": "openid email profile custom_scope",
            "OIDC_USERNAME_CLAIM": "sub",
            "OIDC_NAME": "My Custom Provider",
        }.get(key, default)

        config = get_provider_config(PROVIDER_CUSTOM, mock_app)
        assert config is not None
        assert config["client_id"] == "custom-client-id"
        assert config["client_secret"] == "custom-secret"
        assert config["issuer"] == "https://custom-issuer.com"
        assert config["scopes"] == "openid email profile custom_scope"
        assert config["username_claim"] == "sub"
        assert config["name"] == "My Custom Provider"

    def test_custom_provider_defaults(self):
        """Test custom provider with default values."""
        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default=None: {
            "OIDC_CLIENT_ID": "custom-client-id",
            "OIDC_ISSUER": "https://custom-issuer.com",
        }.get(key, default)

        config = get_provider_config(PROVIDER_CUSTOM, mock_app)
        assert config is not None
        assert config["scopes"] == "openid email profile"  # Default
        assert config["username_claim"] == "preferred_username"  # Default
        assert config["name"] == "OIDC"  # Default

    def test_provider_not_configured(self):
        """Test getting config for provider that isn't configured."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = None

        config = get_provider_config("google", mock_app)
        assert config is None

    def test_unknown_provider(self):
        """Test getting config for unknown provider."""
        mock_app = MagicMock()

        config = get_provider_config("unknown_provider", mock_app)
        assert config is None


class TestCreateOrUpdateOidcUser:
    """Test cases for create_or_update_oidc_user function."""

    @patch("gramps_webapi.auth.oidc.get_oidc_account")
    @patch("gramps_webapi.auth.oidc.get_name")
    @patch("gramps_webapi.auth.oidc.modify_user")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_existing_user_with_role_mapping(
        self, mock_get_config, mock_modify, mock_get_name, mock_get_oidc
    ):
        """Test updating an existing OIDC user with role mapping (custom provider only)."""
        # Mock existing OIDC account
        mock_get_oidc.return_value = "existing-user-guid"
        mock_get_name.return_value = "testuser"

        # Mock provider config
        mock_get_config.return_value = {
            "username_claim": "preferred_username",
        }

        userinfo = {
            "sub": "provider-sub-123",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "groups": ["editor-group"],
        }

        mock_app = MagicMock()
        mock_app.config.get.side_effect = lambda key, default="": {
            "OIDC_ROLE_CLAIM": "groups",
            "OIDC_GROUP_EDITOR": "editor-group",
            "OIDC_GROUP_ADMIN": "",
            "OIDC_GROUP_OWNER": "",
            "OIDC_GROUP_CONTRIBUTOR": "",
            "OIDC_GROUP_MEMBER": "",
            "OIDC_GROUP_GUEST": "",
        }.get(key, default)

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            result = create_or_update_oidc_user(userinfo, "test_tree", PROVIDER_CUSTOM)

        assert result == "existing-user-guid"
        mock_modify.assert_called_once_with(
            name="testuser",
            fullname="Test User",
            email="test@example.com",
            role=ROLE_EDITOR,
            tree="test_tree",
        )

    @patch("gramps_webapi.auth.oidc.get_oidc_account")
    @patch("gramps_webapi.auth.oidc.get_name")
    @patch("gramps_webapi.auth.oidc.modify_user")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_existing_user_no_role_mapping(
        self, mock_get_config, mock_modify, mock_get_name, mock_get_oidc
    ):
        """Test updating existing user without role mapping preserves role."""
        mock_get_oidc.return_value = "existing-user-guid"
        mock_get_name.return_value = "testuser"
        mock_get_config.return_value = {"username_claim": "preferred_username"}

        userinfo = {
            "sub": "provider-sub-123",
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
        }

        mock_app = MagicMock()
        mock_app.config.get.return_value = "groups"

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            with patch(
                "gramps_webapi.auth.oidc.get_role_from_claims", return_value=None
            ):
                result = create_or_update_oidc_user(userinfo, "test_tree", "google")

        # Should not pass role parameter
        mock_modify.assert_called_once_with(
            name="testuser",
            fullname="Test User",
            email="test@example.com",
            tree="test_tree",
        )

    @patch("gramps_webapi.auth.oidc.get_oidc_account", return_value=None)
    @patch("gramps_webapi.auth.oidc.get_user_details", return_value=None)
    @patch("gramps_webapi.auth.oidc.add_user")
    @patch("gramps_webapi.auth.oidc.get_guid")
    @patch("gramps_webapi.auth.oidc.create_oidc_account")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    @patch("gramps_webapi.auth.oidc.secrets.token_urlsafe")
    def test_new_user_google_provider(
        self,
        mock_token,
        mock_get_config,
        mock_create_oidc,
        mock_get_guid,
        mock_add_user,
        mock_get_user,
        mock_get_oidc,
    ):
        """Test creating new user with Google provider."""
        mock_token.return_value = "random-password-123"
        mock_get_guid.return_value = "new-user-guid"
        mock_get_config.return_value = {"username_claim": "email"}

        userinfo = {
            "sub": "google-sub-12345",
            "email": "newuser@gmail.com",
            "name": "New User",
        }

        mock_app = MagicMock()
        mock_app.config = {"TREE": "single_tree"}

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            with patch(
                "gramps_webapi.auth.oidc.get_role_from_claims",
                return_value=ROLE_DISABLED,
            ):
                # Mock get_tree_id and run_task to avoid database/task access in disabled role path
                with patch(
                    "gramps_webapi.api.util.get_tree_id", return_value="test_tree"
                ):
                    with patch("gramps_webapi.api.tasks.run_task"):
                        result = create_or_update_oidc_user(
                            userinfo, "test_tree", "google"
                        )

        assert result == "new-user-guid"

        # Username should be prefixed with provider for builtin providers
        mock_add_user.assert_called_once()
        call_kwargs = mock_add_user.call_args[1]
        assert call_kwargs["name"] == "google_newuser@gmail.com"
        assert call_kwargs["role"] == ROLE_DISABLED

        # Should create OIDC account association
        mock_create_oidc.assert_called_once_with(
            "new-user-guid", "google", "google-sub-12345", "newuser@gmail.com"
        )

    @patch("gramps_webapi.auth.oidc.get_oidc_account", return_value=None)
    @patch("gramps_webapi.auth.oidc.get_user_details", return_value=None)
    @patch("gramps_webapi.auth.oidc.add_user")
    @patch("gramps_webapi.auth.oidc.get_guid")
    @patch("gramps_webapi.auth.oidc.create_oidc_account")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    @patch("gramps_webapi.auth.oidc.secrets.token_urlsafe")
    def test_new_user_custom_provider(
        self,
        mock_token,
        mock_get_config,
        mock_create_oidc,
        mock_get_guid,
        mock_add_user,
        mock_get_user,
        mock_get_oidc,
    ):
        """Test creating new user with custom provider - no prefix."""
        mock_token.return_value = "random-password-123"
        mock_get_guid.return_value = "new-user-guid"
        mock_get_config.return_value = {"username_claim": "preferred_username"}

        userinfo = {
            "sub": "custom-sub-12345",
            "preferred_username": "customuser",
            "email": "custom@example.com",
        }

        mock_app = MagicMock()
        mock_app.config = {"TREE": "single_tree"}

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            with patch(
                "gramps_webapi.auth.oidc.get_role_from_claims",
                return_value=ROLE_DISABLED,
            ):
                # Mock get_tree_id and run_task to avoid database/task access in disabled role path
                with patch(
                    "gramps_webapi.api.util.get_tree_id", return_value="test_tree"
                ):
                    with patch("gramps_webapi.api.tasks.run_task"):
                        result = create_or_update_oidc_user(
                            userinfo, None, PROVIDER_CUSTOM
                        )

        # Username should NOT be prefixed for custom provider
        call_kwargs = mock_add_user.call_args[1]
        assert call_kwargs["name"] == "customuser"

    @patch("gramps_webapi.auth.oidc.get_oidc_account", return_value=None)
    @patch("gramps_webapi.auth.oidc.get_user_details")
    @patch("gramps_webapi.auth.oidc.add_user")
    @patch("gramps_webapi.auth.oidc.get_guid")
    @patch("gramps_webapi.auth.oidc.create_oidc_account")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    @patch("gramps_webapi.auth.oidc.secrets.token_urlsafe")
    def test_new_user_username_conflict_resolution(
        self,
        mock_token,
        mock_get_config,
        mock_create_oidc,
        mock_get_guid,
        mock_add_user,
        mock_get_user,
        mock_get_oidc,
    ):
        """Test username conflict resolution with counter suffix."""
        mock_token.return_value = "random-password"
        mock_get_guid.return_value = "new-user-guid"
        mock_get_config.return_value = {"username_claim": "preferred_username"}

        # Simulate existing users
        mock_get_user.side_effect = [
            {"name": "google_testuser"},  # First attempt - exists
            {"name": "google_testuser_1"},  # Second attempt - exists
            None,  # Third attempt - available
        ]

        userinfo = {
            "sub": "google-sub-123",
            "preferred_username": "testuser",
        }

        mock_app = MagicMock()
        mock_app.config = {"TREE": "single_tree"}

        with patch("gramps_webapi.auth.oidc.current_app", mock_app):
            with patch(
                "gramps_webapi.auth.oidc.get_role_from_claims",
                return_value=ROLE_DISABLED,
            ):
                # Mock get_tree_id and run_task to avoid database/task access in disabled role path
                with patch(
                    "gramps_webapi.api.util.get_tree_id", return_value="test_tree"
                ):
                    with patch("gramps_webapi.api.tasks.run_task"):
                        create_or_update_oidc_user(userinfo, None, "google")

        # Should use google_testuser_2
        call_kwargs = mock_add_user.call_args[1]
        assert call_kwargs["name"] == "google_testuser_2"

    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_missing_sub_claim(self, mock_get_config):
        """Test that missing 'sub' claim raises ValueError."""
        mock_get_config.return_value = {"username_claim": "preferred_username"}

        userinfo = {
            "preferred_username": "testuser",
            "email": "test@example.com",
            # Missing 'sub' claim
        }

        with pytest.raises(ValueError, match="No 'sub' claim found"):
            create_or_update_oidc_user(userinfo, None, "google")

    @patch("gramps_webapi.auth.oidc.get_provider_config", return_value=None)
    def test_invalid_provider(self, mock_get_config):
        """Test that invalid provider raises ValueError."""
        userinfo = {"sub": "test-sub"}

        with pytest.raises(ValueError, match="not configured"):
            create_or_update_oidc_user(userinfo, None, "invalid_provider")


class TestInitOidc:
    """Test cases for init_oidc function."""

    def test_oidc_disabled(self):
        """Test OIDC initialization when disabled."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = False

        result = init_oidc(mock_app)
        assert result is None

    @patch("gramps_webapi.auth.oidc.OAuth")
    @patch("gramps_webapi.auth.oidc.get_available_oidc_providers")
    def test_oidc_enabled_no_providers(self, mock_get_providers, mock_oauth_class):
        """Test OIDC initialization with no providers configured."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = True
        mock_get_providers.return_value = []

        result = init_oidc(mock_app)
        assert result is None

    @patch("gramps_webapi.auth.oidc.OAuth")
    @patch("gramps_webapi.auth.oidc.get_available_oidc_providers")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_init_google_provider(
        self, mock_get_config, mock_get_providers, mock_oauth_class
    ):
        """Test initializing Google provider."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = True
        mock_get_providers.return_value = ["google"]
        mock_get_config.return_value = {
            "name": "Google",
            "client_id": "google-client-id",
            "client_secret": "google-secret",
            "issuer": "https://accounts.google.com",
            "scopes": "openid email profile",
        }

        mock_oauth = MagicMock()
        mock_oauth_class.return_value = mock_oauth

        result = init_oidc(mock_app)

        assert result == mock_oauth
        mock_oauth.register.assert_called_once()
        call_kwargs = mock_oauth.register.call_args[1]
        assert call_kwargs["name"] == "gramps_google"
        assert call_kwargs["client_id"] == "google-client-id"

    @patch("gramps_webapi.auth.oidc.OAuth")
    @patch("gramps_webapi.auth.oidc.get_available_oidc_providers")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_init_github_provider(
        self, mock_get_config, mock_get_providers, mock_oauth_class
    ):
        """Test initializing GitHub provider (OAuth 2.0, not OIDC)."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = True
        mock_get_providers.return_value = ["github"]
        mock_get_config.return_value = {
            "name": "GitHub",
            "client_id": "github-client-id",
            "client_secret": "github-secret",
            "auth_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scopes": "user:email",
        }

        mock_oauth = MagicMock()
        mock_oauth_class.return_value = mock_oauth

        init_oidc(mock_app)

        # Should use OAuth 2.0 registration (not OIDC)
        call_kwargs = mock_oauth.register.call_args[1]
        assert (
            call_kwargs["access_token_url"]
            == "https://github.com/login/oauth/access_token"
        )
        assert (
            call_kwargs["authorize_url"] == "https://github.com/login/oauth/authorize"
        )

    @patch("gramps_webapi.auth.oidc.OAuth")
    @patch("gramps_webapi.auth.oidc.get_available_oidc_providers")
    @patch("gramps_webapi.auth.oidc.get_provider_config")
    def test_init_multiple_providers(
        self, mock_get_config, mock_get_providers, mock_oauth_class
    ):
        """Test initializing multiple providers."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = True
        mock_get_providers.return_value = ["google", "microsoft", PROVIDER_CUSTOM]

        # Return different configs for each provider
        def get_config_side_effect(provider_id, app=None):
            configs = {
                "google": {
                    "name": "Google",
                    "client_id": "g-id",
                    "client_secret": "g-secret",
                    "issuer": "https://accounts.google.com",
                    "scopes": "openid email",
                },
                "microsoft": {
                    "name": "Microsoft",
                    "client_id": "ms-id",
                    "client_secret": "ms-secret",
                    "issuer": "https://login.microsoftonline.com/common/v2.0",
                    "scopes": "openid email",
                },
                PROVIDER_CUSTOM: {
                    "name": "Custom",
                    "client_id": "c-id",
                    "client_secret": "c-secret",
                    "issuer": "https://custom.com",
                    "scopes": "openid email",
                },
            }
            return configs.get(provider_id)

        mock_get_config.side_effect = get_config_side_effect
        mock_oauth = MagicMock()
        mock_oauth_class.return_value = mock_oauth

        init_oidc(mock_app)

        # Should register all three providers
        assert mock_oauth.register.call_count == 3
