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

"""Tests for OIDC authentication logic."""

import unittest
from unittest.mock import MagicMock, patch

from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.auth.oidc import (
    create_or_update_oidc_user,
    get_role_from_groups,
    init_oidc,
)


class TestOIDCAuth(unittest.TestCase):
    """Test cases for OIDC authentication logic."""

    def test_get_role_from_groups_empty_groups(self):
        """Test role mapping with empty groups list."""
        with patch.dict("os.environ", {}, clear=True):
            role = get_role_from_groups([])
            self.assertEqual(role, ROLE_GUEST)

    def test_get_role_from_groups_no_matching_groups(self):
        """Test role mapping with no matching groups."""
        with patch.dict(
            "os.environ",
            {
                "OIDC_GROUP_ADMIN": "admin-group",
                "OIDC_GROUP_EDITOR": "editor-group",
            },
            clear=True,
        ):
            role = get_role_from_groups(["unknown-group", "another-unknown"])
            self.assertEqual(role, ROLE_GUEST)

    def test_get_role_from_groups_single_match(self):
        """Test role mapping with single matching group."""
        with patch.dict(
            "os.environ",
            {
                "OIDC_GROUP_ADMIN": "admin-group",
                "OIDC_GROUP_EDITOR": "editor-group",
                "OIDC_GROUP_MEMBER": "member-group",
            },
            clear=True,
        ):
            # Test each role level
            self.assertEqual(get_role_from_groups(["admin-group"]), ROLE_ADMIN)
            self.assertEqual(get_role_from_groups(["editor-group"]), ROLE_EDITOR)
            self.assertEqual(get_role_from_groups(["member-group"]), ROLE_MEMBER)

    def test_get_role_from_groups_multiple_matches_precedence(self):
        """Test role mapping with multiple matching groups - highest precedence wins."""
        with patch.dict(
            "os.environ",
            {
                "OIDC_GROUP_ADMIN": "admin-group",
                "OIDC_GROUP_OWNER": "owner-group",
                "OIDC_GROUP_EDITOR": "editor-group",
                "OIDC_GROUP_CONTRIBUTOR": "contributor-group",
                "OIDC_GROUP_MEMBER": "member-group",
                "OIDC_GROUP_GUEST": "guest-group",
            },
            clear=True,
        ):
            # Admin (5) should win over all others
            role = get_role_from_groups(["member-group", "admin-group", "editor-group"])
            self.assertEqual(role, ROLE_ADMIN)

            # Owner (4) should win over lower roles
            role = get_role_from_groups(["member-group", "owner-group", "contributor-group"])
            self.assertEqual(role, ROLE_OWNER)

            # Editor (3) should win over lower roles
            role = get_role_from_groups(["member-group", "editor-group", "guest-group"])
            self.assertEqual(role, ROLE_EDITOR)

    def test_get_role_from_groups_environment_variable_formats(self):
        """Test role mapping with various environment variable formats."""
        with patch.dict(
            "os.environ",
            {
                "OIDC_GROUP_ADMIN": "gramps-admins,super-admins",  # Comma-separated not supported
                "OIDC_GROUP_EDITOR": "gramps-editors",
            },
            clear=True,
        ):
            # Only exact matches should work
            self.assertEqual(get_role_from_groups(["gramps-editors"]), ROLE_EDITOR)
            self.assertEqual(get_role_from_groups(["super-admins"]), ROLE_GUEST)  # No match
            self.assertEqual(get_role_from_groups(["gramps-admins,super-admins"]), ROLE_ADMIN)  # Exact match

    def test_get_role_from_groups_case_sensitivity(self):
        """Test role mapping is case-sensitive."""
        with patch.dict(
            "os.environ",
            {"OIDC_GROUP_ADMIN": "Admin-Group"},
            clear=True,
        ):
            self.assertEqual(get_role_from_groups(["Admin-Group"]), ROLE_ADMIN)
            self.assertEqual(get_role_from_groups(["admin-group"]), ROLE_GUEST)
            self.assertEqual(get_role_from_groups(["ADMIN-GROUP"]), ROLE_GUEST)

    @patch("gramps_webapi.auth.oidc.get_user_details")
    @patch("gramps_webapi.auth.oidc.get_guid")
    @patch("gramps_webapi.auth.oidc.modify_user")
    def test_create_or_update_oidc_user_existing_user(self, mock_modify, mock_get_guid, mock_get_details):
        """Test updating an existing OIDC user."""
        # Mock existing user
        mock_get_details.return_value = {"name": "testuser", "role": ROLE_MEMBER}
        mock_get_guid.return_value = "user-guid-123"

        userinfo = {
            "preferred_username": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "groups": ["editor-group"],
        }

        with patch.dict(
            "os.environ",
            {"OIDC_GROUP_EDITOR": "editor-group"},
            clear=True,
        ):
            result = create_or_update_oidc_user(userinfo, "test_tree")

        self.assertEqual(result, "user-guid-123")
        mock_modify.assert_called_once_with(
            name="testuser",
            fullname="Test User",
            email="test@example.com",
            role=ROLE_EDITOR,
            tree="test_tree",
        )

    @patch("gramps_webapi.auth.oidc.get_user_details", return_value=None)
    @patch("gramps_webapi.auth.oidc.add_user")
    @patch("gramps_webapi.auth.oidc.get_guid")
    @patch("gramps_webapi.auth.oidc.secrets.token_urlsafe")
    def test_create_or_update_oidc_user_new_user(self, mock_token, mock_get_guid, mock_add_user, mock_get_details):
        """Test creating a new OIDC user."""
        mock_token.return_value = "random-password-123"
        mock_get_guid.return_value = "new-user-guid"

        userinfo = {
            "preferred_username": "newuser",
            "email": "new@example.com",
            "name": "New User",
            "groups": ["contributor-group"],
        }

        with patch.dict(
            "os.environ",
            {"OIDC_GROUP_CONTRIBUTOR": "contributor-group"},
            clear=True,
        ):
            result = create_or_update_oidc_user(userinfo, "test_tree")

        self.assertEqual(result, "new-user-guid")
        mock_add_user.assert_called_once_with(
            name="newuser",
            password="random-password-123",
            fullname="New User",
            email="new@example.com",
            role=ROLE_CONTRIBUTOR,
            tree="test_tree",
        )

    @patch("gramps_webapi.auth.oidc.get_user_details", return_value=None)
    def test_create_or_update_oidc_user_fallback_to_sub(self, mock_get_details):
        """Test user creation when preferred_username is missing."""
        userinfo = {
            "sub": "user-12345",
            "email": "sub@example.com",
            "groups": [],
        }

        with patch("gramps_webapi.auth.oidc.add_user") as mock_add_user:
            with patch("gramps_webapi.auth.oidc.get_guid", return_value="sub-user-guid"):
                result = create_or_update_oidc_user(userinfo)

        self.assertEqual(result, "sub-user-guid")
        # Should use 'sub' as username when preferred_username is missing
        mock_add_user.assert_called_once()
        args, kwargs = mock_add_user.call_args
        self.assertEqual(kwargs["name"], "user-12345")

    def test_create_or_update_oidc_user_no_username(self):
        """Test user creation fails when no username is available."""
        userinfo = {
            "email": "noname@example.com",
            "groups": [],
        }

        with self.assertRaises(ValueError) as context:
            create_or_update_oidc_user(userinfo)

        self.assertIn("No username found", str(context.exception))

    @patch("gramps_webapi.auth.oidc.get_user_details", return_value=None)
    @patch("gramps_webapi.auth.oidc.add_user")
    def test_create_or_update_oidc_user_default_guest_role(self, mock_add_user, mock_get_details):
        """Test new user gets guest role when no groups match."""
        userinfo = {
            "preferred_username": "guestuser",
            "groups": ["unknown-group"],
        }

        with patch("gramps_webapi.auth.oidc.get_guid", return_value="guest-guid"):
            result = create_or_update_oidc_user(userinfo)

        mock_add_user.assert_called_once()
        args, kwargs = mock_add_user.call_args
        self.assertEqual(kwargs["role"], ROLE_GUEST)

    def test_init_oidc_disabled(self):
        """Test OIDC initialization when disabled."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = False

        result = init_oidc(mock_app)
        self.assertIsNone(result)

    @patch("gramps_webapi.auth.oidc.OAuth")
    def test_init_oidc_enabled(self, mock_oauth_class):
        """Test OIDC initialization when enabled."""
        mock_app = MagicMock()
        mock_app.config = {
            "OIDC_ENABLED": True,
            "OIDC_CLIENT_ID": "test-client-id",
            "OIDC_CLIENT_SECRET": "test-secret",
            "OIDC_ISSUER": "https://test-issuer.com",
        }

        mock_oauth = MagicMock()
        mock_oauth_class.return_value = mock_oauth

        result = init_oidc(mock_app)

        # Verify OAuth was initialized
        mock_oauth_class.assert_called_once_with(mock_app)
        mock_oauth.register.assert_called_once()

        # Verify registration parameters
        args, kwargs = mock_oauth.register.call_args
        self.assertEqual(kwargs["name"], "gramps")
        self.assertEqual(kwargs["client_id"], "test-client-id")
        self.assertEqual(kwargs["client_secret"], "test-secret")
        self.assertIn("openid email profile groups", kwargs["client_kwargs"]["scope"])

    def test_userinfo_variations(self):
        """Test handling various userinfo formats from different OIDC providers."""
        test_cases = [
            # Standard OIDC userinfo
            {
                "userinfo": {
                    "preferred_username": "standarduser",
                    "email": "standard@example.com",
                    "name": "Standard User",
                    "groups": ["editor-group"],
                },
                "expected_username": "standarduser",
                "expected_role": ROLE_EDITOR,
            },
            # Azure AD format
            {
                "userinfo": {
                    "preferred_username": "azureuser@tenant.onmicrosoft.com",
                    "email": "azure@example.com",
                    "name": "Azure User",
                    "groups": ["admin-group"],
                },
                "expected_username": "azureuser@tenant.onmicrosoft.com",
                "expected_role": ROLE_ADMIN,
            },
            # Minimal userinfo
            {
                "userinfo": {
                    "sub": "minimal123",
                    "groups": ["member-group"],
                },
                "expected_username": "minimal123",
                "expected_role": ROLE_MEMBER,
            },
        ]

        with patch.dict(
            "os.environ",
            {
                "OIDC_GROUP_ADMIN": "admin-group",
                "OIDC_GROUP_EDITOR": "editor-group",
                "OIDC_GROUP_MEMBER": "member-group",
            },
            clear=True,
        ):
            for case in test_cases:
                with self.subTest(case=case):
                    with patch("gramps_webapi.auth.oidc.get_user_details", return_value=None):
                        with patch("gramps_webapi.auth.oidc.add_user") as mock_add_user:
                            with patch("gramps_webapi.auth.oidc.get_guid", return_value="test-guid"):
                                create_or_update_oidc_user(case["userinfo"])

                    mock_add_user.assert_called_once()
                    args, kwargs = mock_add_user.call_args
                    self.assertEqual(kwargs["name"], case["expected_username"])
                    self.assertEqual(kwargs["role"], case["expected_role"])

if __name__ == "__main__":
    unittest.main()