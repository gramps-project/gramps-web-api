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

"""OIDC authentication support."""

import logging
import os
import secrets
import uuid
from typing import Dict, List, Optional, Set

from authlib.integrations.flask_client import OAuth
from flask import current_app, session

from . import add_user, get_all_user_details, get_guid, get_user_details, modify_user
from .const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)

logger = logging.getLogger(__name__)

# Built-in provider configurations
BUILTIN_PROVIDERS = {
    "google": {
        "name": "Google",
        "issuer": "https://accounts.google.com",
        "scopes": "openid email profile",
        "username_claim": "email",
    },
    "microsoft": {
        "name": "Microsoft",
        "issuer": "https://login.microsoftonline.com/common/v2.0",
        "scopes": "openid email profile",
        "username_claim": "preferred_username",
    },
    "github": {
        "name": "GitHub",
        "issuer": "https://github.com",
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": "user:email",
        "username_claim": "login",
    }
}


def get_available_oidc_providers(app=None) -> List[str]:
    """Auto-detect available OIDC providers from Flask configuration.

    Scans for OIDC_{PROVIDER}_CLIENT_ID configuration values to determine
    which providers are configured.

    Returns:
        List of provider names (e.g., ['google', 'microsoft', 'github', 'custom'])
    """
    if app is None:
        from flask import current_app
        app = current_app

    providers = []

    # Check for built-in providers
    for provider_id in BUILTIN_PROVIDERS.keys():
        client_id_key = f"OIDC_{provider_id.upper()}_CLIENT_ID"
        if app.config.get(client_id_key):
            providers.append(provider_id)

    # Check for custom provider (optional)
    if app.config.get("OIDC_CLIENT_ID") and app.config.get("OIDC_ISSUER"):
        providers.append("custom")

    return providers


def get_provider_config(provider_id: str, app=None) -> Optional[Dict]:
    """Get configuration for a specific OIDC provider.

    Args:
        provider_id: Provider identifier (e.g., 'google', 'microsoft', 'github', 'custom')
        app: Flask app instance (optional, defaults to current_app)

    Returns:
        Provider configuration dict or None if not configured
    """
    if app is None:
        from flask import current_app
        app = current_app

    if provider_id == "custom":
        # Custom provider configuration
        client_id = app.config.get("OIDC_CLIENT_ID")
        issuer = app.config.get("OIDC_ISSUER")

        if not (client_id and issuer):
            return None

        return {
            "name": "OIDC",
            "client_id": client_id,
            "client_secret": app.config.get("OIDC_CLIENT_SECRET"),
            "issuer": issuer,
            "scopes": app.config.get("OIDC_SCOPES", "openid email profile"),
            "username_claim": app.config.get("OIDC_USERNAME_CLAIM", "preferred_username"),
            "openid_config_url": app.config.get("OIDC_OPENID_CONFIG_URL"),
        }

    if provider_id not in BUILTIN_PROVIDERS:
        return None

    # Built-in provider configuration
    provider_upper = provider_id.upper()
    client_id = app.config.get(f"OIDC_{provider_upper}_CLIENT_ID")
    client_secret = app.config.get(f"OIDC_{provider_upper}_CLIENT_SECRET")

    if not (client_id and client_secret):
        return None

    config = BUILTIN_PROVIDERS[provider_id].copy()
    config.update({
        "client_id": client_id,
        "client_secret": client_secret,
    })

    return config


def get_role_from_claims(user_claims: dict, role_claim: str = "groups") -> Optional[int]:
    """Map OIDC claims to Gramps roles based on environment variables.

    Args:
        user_claims: The user claims from OIDC token
        role_claim: The claim to look for roles/groups (e.g., 'groups', 'roles', 'realm_access.roles')

    Returns the highest role the user is entitled to based on claim membership,
    or None if no role mapping is configured (to preserve existing roles).
    Environment variables should be named GRAMPSWEB_OIDC_GROUP_<ROLE>.
    """
    from flask import current_app

    role_mapping = {
        ROLE_ADMIN: current_app.config.get("OIDC_GROUP_ADMIN", ""),
        ROLE_OWNER: current_app.config.get("OIDC_GROUP_OWNER", ""),
        ROLE_EDITOR: current_app.config.get("OIDC_GROUP_EDITOR", ""),
        ROLE_CONTRIBUTOR: current_app.config.get("OIDC_GROUP_CONTRIBUTOR", ""),
        ROLE_MEMBER: current_app.config.get("OIDC_GROUP_MEMBER", ""),
        ROLE_GUEST: current_app.config.get("OIDC_GROUP_GUEST", ""),
    }

    # Check if any role mapping is configured
    has_role_mapping = any(group_name.strip() for group_name in role_mapping.values())
    if not has_role_mapping:
        logger.info("No OIDC role mapping configured (no GRAMPSWEB_OIDC_GROUP_* environment variables set). Preserving existing user roles.")
        return None

    # Extract user groups/roles from claims
    user_groups = []

    # Handle nested claims like 'realm_access.roles'
    if '.' in role_claim:
        claim_parts = role_claim.split('.')
        claim_value = user_claims
        for part in claim_parts:
            claim_value = claim_value.get(part, {})
        if isinstance(claim_value, list):
            user_groups = claim_value
    else:
        # Handle direct claims like 'groups' or 'roles'
        claim_value = user_claims.get(role_claim, [])
        if isinstance(claim_value, list):
            user_groups = claim_value
        elif isinstance(claim_value, str):
            user_groups = [claim_value]

    # Fallback: if no groups found in claims, assign default guest role
    if not user_groups:
        logger.warning(f"No {role_claim} found in user claims. Available claims: {list(user_claims.keys())}. Assigning guest role.")
        return ROLE_GUEST

    highest_role = ROLE_GUEST

    for role_level in sorted(role_mapping.keys(), reverse=True):
        group_name = role_mapping[role_level]
        if group_name and group_name in user_groups:
            highest_role = role_level
            break

    logger.info(f"User {role_claim} {user_groups} mapped to role {highest_role}")
    return highest_role


def create_or_update_oidc_user(
    userinfo: Dict,
    tree: Optional[str] = None,
    provider_id: str = "custom"
) -> str:
    """Create or update a user based on OIDC userinfo.

    Args:
        userinfo: User information from OIDC provider
        tree: Tree identifier (optional)
        provider_id: OIDC provider identifier

    Returns the user GUID.
    """
    from flask import current_app

    # Get provider-specific configuration
    provider_config = get_provider_config(provider_id)
    if not provider_config:
        raise ValueError(f"Provider '{provider_id}' is not configured")

    # Get username from provider-specific claim with fallback to 'sub'
    username_claim = provider_config.get("username_claim", "preferred_username")
    username = userinfo.get(username_claim) or userinfo.get("sub")

    email = userinfo.get("email", "")
    full_name = userinfo.get("name", "")

    # For GitHub, get email from separate API call if not in userinfo
    if provider_id == "github" and not email:
        email = userinfo.get("email") or f"{userinfo.get('login', 'user')}@users.noreply.github.com"

    if not username:
        available_claims = ", ".join(userinfo.keys())
        raise ValueError(f"No username found in OIDC userinfo for provider '{provider_id}'. Tried claim '{username_claim}' and fallback 'sub'. Available claims: {available_claims}")

    # Add provider prefix to username to avoid conflicts between providers
    # Custom provider gets no prefix for cleaner usernames in self-hosted systems
    if provider_id != "custom":
        username = f"{provider_id}:{username}"

    role_claim = current_app.config.get("OIDC_ROLE_CLAIM", "groups")
    role_from_claims = get_role_from_claims(userinfo, role_claim)

    existing_user = get_user_details(username)

    if existing_user:
        user_guid = get_guid(username)
        logger.info(f"Updating existing OIDC user: {username}")

        # Only update role if role mapping is configured
        if role_from_claims is not None:
            modify_user(
                name=username,
                fullname=full_name,
                email=email,
                role=role_from_claims,
                tree=tree,
            )
        else:
            # Preserve existing role when no role mapping is configured
            modify_user(
                name=username,
                fullname=full_name,
                email=email,
                tree=tree,
            )
    else:
        logger.info(f"Creating new OIDC user: {username}")
        random_password = secrets.token_urlsafe(32)

        # For new users, use role from claims if available, otherwise default to GUEST
        final_role = role_from_claims if role_from_claims is not None else ROLE_GUEST

        add_user(
            name=username,
            password=random_password,
            fullname=full_name,
            email=email,
            role=final_role,
            tree=tree,
        )
        user_guid = get_guid(username)

    return user_guid


def init_oidc(app):
    """Initialize OIDC authentication for Flask app."""
    if not app.config.get("OIDC_ENABLED"):
        return None

    oauth = OAuth(app)
    providers = get_available_oidc_providers(app)

    if not providers:
        logger.warning("OIDC is enabled but no providers are configured")
        return None

    # Register each available provider
    for provider_id in providers:
        provider_config = get_provider_config(provider_id, app)
        if not provider_config:
            logger.warning(f"Skipping provider '{provider_id}' - configuration incomplete")
            continue

        try:
            # Use provider-specific configuration
            client_kwargs = {"scope": provider_config["scopes"]}

            # Handle different provider types
            if provider_id == "github":
                # GitHub uses OAuth 2.0, not OIDC
                oauth.register(
                    name=f"gramps_{provider_id}",
                    client_id=provider_config["client_id"],
                    client_secret=provider_config["client_secret"],
                    access_token_url=provider_config["token_url"],
                    authorize_url=provider_config["auth_url"],
                    api_base_url="https://api.github.com/",
                    client_kwargs=client_kwargs,
                )
            else:
                # Standard OIDC providers
                server_metadata_url = provider_config.get(
                    "openid_config_url",
                    f"{provider_config['issuer']}/.well-known/openid-configuration"
                )

                oauth.register(
                    name=f"gramps_{provider_id}",
                    client_id=provider_config["client_id"],
                    client_secret=provider_config["client_secret"],
                    server_metadata_url=server_metadata_url,
                    client_kwargs=client_kwargs,
                )

            logger.info(f"Registered OIDC provider: {provider_config['name']} ({provider_id})")

        except Exception as e:
            logger.error(f"Failed to register OIDC provider '{provider_id}': {e}")

    return oauth


def is_oidc_enabled() -> bool:
    """Check if OIDC is enabled in the current app."""
    return current_app.config.get("OIDC_ENABLED", False)