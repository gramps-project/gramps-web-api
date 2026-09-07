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

"""OIDC authentication support."""

import logging
import secrets
import uuid
from typing import Any

from authlib.integrations.flask_client import OAuth
from flask import current_app

from ..const import TREE_MULTI
from . import (
    add_user,
    create_oidc_account,
    get_guid,
    get_name,
    get_oidc_account,
    get_user_details,
    modify_user,
)
from .const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_DISABLED,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)

# NOTE: Imports from api.tasks and api.util are done inside functions to avoid
# circular import (oidc.py -> api -> oidc.py). This is an intentional exception
# to the top-level import standard.


logger = logging.getLogger(__name__)

# Provider identifier for custom OIDC configurations
PROVIDER_CUSTOM = "custom"

# Built-in provider configurations.
#
# Every entry describes a standards-compliant OpenID Connect provider and is
# consumed as data - there is deliberately no per-provider branching in the
# request handlers. Recognised keys beyond the obvious ones:
#
#   relax_issuer: do not require the ID token `iss` claim to match the issuer
#                 advertised in the discovery document.
#
# The value type is Any because entries hold both strings and flags; without
# the annotation mypy joins the differently shaped entries down to `object`.
BUILTIN_PROVIDERS: dict[str, dict[str, Any]] = {
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
        # The multi-tenant `/common` endpoint issues tokens whose `iss` claim is
        # tenant-specific and therefore never matches the issuer in the
        # discovery document. Relaxing the check is safe here because the
        # provider is preconfigured: the token is fetched from the token
        # endpoint of that discovery document, not from an attacker-supplied
        # one. Deployments pinned to a single tenant should configure the
        # tenant-specific issuer via the `custom` provider instead.
        "relax_issuer": True,
    },
}


def get_available_oidc_providers(app=None) -> list[str]:
    """Auto-detect available OIDC providers from Flask configuration.

    Scans for OIDC_{PROVIDER}_CLIENT_ID configuration values to determine
    which providers are configured.

    Returns:
        List of provider names (e.g., ['google', 'microsoft', 'custom'])
    """
    if app is None:
        app = current_app

    providers = []

    # Check for built-in providers
    for provider_id in BUILTIN_PROVIDERS.keys():
        client_id_key = f"OIDC_{provider_id.upper()}_CLIENT_ID"
        if app.config.get(client_id_key):
            providers.append(provider_id)

    # Check for custom provider (optional)
    if app.config.get("OIDC_CLIENT_ID") and app.config.get("OIDC_ISSUER"):
        providers.append(PROVIDER_CUSTOM)

    return providers


def get_provider_config(provider_id: str, app=None) -> dict | None:
    """Get configuration for a specific OIDC provider.

    Args:
        provider_id: Provider identifier (e.g., 'google', 'microsoft', 'custom')
        app: Flask app instance (optional, defaults to current_app)

    Returns:
        Provider configuration dict or None if not configured
    """
    if app is None:
        app = current_app

    if provider_id == PROVIDER_CUSTOM:
        # Custom provider configuration
        client_id = app.config.get("OIDC_CLIENT_ID")
        issuer = app.config.get("OIDC_ISSUER")

        if not (client_id and issuer):
            return None

        return {
            "name": app.config.get("OIDC_NAME", "OIDC"),
            "client_id": client_id,
            "client_secret": app.config.get("OIDC_CLIENT_SECRET"),
            "issuer": issuer,
            "scopes": app.config.get("OIDC_SCOPES", "openid email profile"),
            "username_claim": app.config.get(
                "OIDC_USERNAME_CLAIM", "preferred_username"
            ),
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
    config.update(
        {
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )

    return config


def get_role_from_claims(user_claims: dict, role_claim: str = "groups") -> int | None:
    """Map OIDC claims to Gramps roles based on environment variables.

    Args:
        user_claims: The user claims from OIDC token
        role_claim: The claim to look for roles/groups (e.g., 'groups', 'roles', 'realm_access.roles')

    Returns the highest role the user is entitled to based on claim membership,
    or None if no role mapping is configured (to preserve existing roles).
    Environment variables should be named GRAMPSWEB_OIDC_GROUP_<ROLE>.
    """

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
        logger.info(
            "No OIDC role mapping configured (no OIDC_GROUP_* configuration options set). Preserving existing user roles."
        )
        return None

    # Extract user groups/roles from claims. A claim that is absent altogether
    # means something different from a claim that is present but empty: the
    # first says the provider sends no group information, the second that the
    # user belongs to no group.
    claim_value = user_claims
    claim_present = True
    for part in role_claim.split("."):  # handles nested 'realm_access.roles'
        if not isinstance(claim_value, dict) or part not in claim_value:
            claim_present = False
            break
        claim_value = claim_value[part]

    if not claim_present:
        # Nothing to map. Preserve whatever role the account already has -
        # new accounts are defaulted to ROLE_DISABLED by the caller. Demoting
        # an existing user because the provider does not send the claim (Google
        # never does) would lock working accounts out on their next login.
        logger.warning(
            f"No '{role_claim}' claim found in user claims. Leaving role unchanged."
        )
        return None

    user_groups: list[str] = []
    if isinstance(claim_value, list):
        user_groups = claim_value
    elif isinstance(claim_value, str):
        user_groups = [claim_value]

    # The claim is there and the user is in no group it maps: fail closed.
    if not user_groups:
        logger.info(f"User is in no '{role_claim}' group. Assigning disabled role.")
        return ROLE_DISABLED

    highest_role = ROLE_DISABLED

    for role_level in sorted(role_mapping.keys(), reverse=True):
        group_name = role_mapping[role_level]
        if group_name and group_name in user_groups:
            highest_role = role_level
            break

    logger.info(f"User {role_claim} {user_groups} mapped to role {highest_role}")
    return highest_role


def get_usable_email(userinfo: dict) -> str | None:
    """Return an e-mail address that can safely be stored for this user.

    An address the provider explicitly marks as unverified is discarded; a
    missing `email_verified` claim is accepted, as many providers omit it.
    """
    email = userinfo.get("email") or None
    if not email:
        return None

    if userinfo.get("email_verified") is False:
        logger.warning(
            "OIDC provider reported e-mail address as unverified; not storing it."
        )
        return None

    return email


def create_or_update_oidc_user(
    userinfo: dict, tree_id: str | None, provider_id: str
) -> str:
    """Create or update a user based on OIDC userinfo using secure sub claim mapping.

    Authentication flow:
    1. Extract sub claim from ID token (this is the unique, non-reassignable identifier)
    2. Look up oidc_accounts table for (provider_id, subject_id) pair
    3. If found: Log in existing user and update last login
    4. If not found: Create new user account and store new oidc_accounts entry

    Args:
        userinfo: User information from OIDC provider
        tree_id: Tree identifier (optional)
        provider_id: OIDC provider identifier

    Returns the user GUID.
    """

    # Extract required claims
    subject_id = userinfo.get("sub")
    if not subject_id:
        available_claims = ", ".join(userinfo.keys())
        raise ValueError(
            f"No 'sub' claim found in OIDC userinfo for provider '{provider_id}'. Available claims: {available_claims}"
        )

    full_name = userinfo.get("name", "")

    # Get provider-specific configuration for username display
    provider_config = get_provider_config(provider_id)
    if not provider_config:
        raise ValueError(f"Provider '{provider_id}' is not configured")

    username_claim = provider_config.get("username_claim", "preferred_username")
    display_username = userinfo.get(username_claim) or userinfo.get("sub")

    # Role mapping applies to every provider; get_role_from_claims returns None
    # when no OIDC_GROUP_* option is configured, which preserves existing roles.
    role_claim = current_app.config.get("OIDC_ROLE_CLAIM", "groups")
    role_from_claims = get_role_from_claims(userinfo, role_claim)

    # Step 1: Check if OIDC account association already exists
    existing_user_id = get_oidc_account(provider_id, subject_id)

    if existing_user_id:
        # Existing OIDC account found - log in user and update info
        logger.info(f"Existing OIDC user found for {provider_id}:{subject_id}")

        # Get the existing username and update user info if needed
        existing_username = get_name(existing_user_id)

        # An OIDC identity is bound to a single Gramps account, which in turn
        # belongs to a single tree. Passing a different tree ID must not
        # silently move the account - only fill in one that is not set yet.
        from ..api.util import get_tree_id_or_none  # circular import

        current_tree_id = get_tree_id_or_none(existing_user_id)
        if current_tree_id and tree_id and current_tree_id != tree_id:
            raise ValueError(
                f"This account belongs to a different tree than '{tree_id}'."
            )

        # role and email are None unless they should be changed; modify_user
        # leaves the stored value untouched in that case
        modify_user(
            name=existing_username,
            fullname=full_name,
            email=get_usable_email(userinfo),
            role=role_from_claims,
            tree=None if current_tree_id else tree_id,
        )

        return existing_user_id

    # Step 2: Create new user account (email linking removed for security)
    logger.info(f"Creating new OIDC user for {provider_id}:{subject_id}")

    # Generate a clean username - for custom providers use the display username as-is,
    # for others prefix with provider to avoid conflicts
    if provider_id == PROVIDER_CUSTOM:
        final_username = display_username or f"user_{uuid.uuid4().hex[:8]}"
    else:
        final_username = f"{provider_id}_{display_username or uuid.uuid4().hex[:8]}"

    # Ensure username is unique by appending a suffix if needed
    base_username = final_username
    counter = 1
    while get_user_details(final_username):
        final_username = f"{base_username}_{counter}"
        counter += 1

    random_password = secrets.token_urlsafe(32)

    # For new users, use role from claims if role mapping is configured,
    # otherwise default to DISABLED so an admin has to approve the account
    final_role = role_from_claims if role_from_claims is not None else ROLE_DISABLED

    email = get_usable_email(userinfo)

    add_user(
        name=final_username,
        password=random_password,
        fullname=full_name,
        email=email,
        role=final_role,
        tree=tree_id,
    )

    user_guid = get_guid(final_username)

    # Create OIDC account association. The address the provider actually sent is
    # recorded here even when it could not be stored on the user, so that an
    # admin can still tell which identity the account belongs to.
    create_oidc_account(user_guid, provider_id, subject_id, userinfo.get("email"))

    # Send notification email to admins about new user (only for new users with ROLE_DISABLED)
    if final_role == ROLE_DISABLED:
        # Lazy imports to avoid circular dependency
        from ..api.tasks import run_task, send_email_new_user
        from ..api.util import get_tree_id

        user_tree_id = get_tree_id(user_guid)
        is_multi = current_app.config["TREE"] == TREE_MULTI
        run_task(
            send_email_new_user,
            username=final_username,
            fullname=full_name or "",
            # report the address the provider sent, even if it was not stored
            email=userinfo.get("email") or "",
            tree=user_tree_id,
            # for single-tree setups, send e-mail also to admins
            include_admins=not is_multi,
            include_treeless=not is_multi,
        )

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
            logger.warning(
                f"Skipping provider '{provider_id}' - configuration incomplete"
            )
            continue

        # Use explicit config URL if provided, otherwise construct from issuer
        server_metadata_url = provider_config.get("openid_config_url")
        if not server_metadata_url:
            server_metadata_url = (
                f"{provider_config['issuer']}/.well-known/openid-configuration"
            )

        try:
            client = oauth.register(
                name=f"gramps_{provider_id}",
                client_id=provider_config["client_id"],
                client_secret=provider_config["client_secret"],
                server_metadata_url=server_metadata_url,
                client_kwargs={"scope": provider_config["scopes"]},
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"Failed to register OIDC provider '{provider_id}': {e}")
            continue

        logger.info(
            f"Registered OIDC provider: {provider_config['name']} ({provider_id})"
        )

        # Warm the discovery document so misconfiguration shows up in the log at
        # startup rather than on a user's first login. A failure here is not
        # fatal: the provider may simply not be up yet, and authlib will retry
        # the fetch on demand.
        try:
            client.load_server_metadata()
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(
                f"Could not load discovery document for OIDC provider "
                f"'{provider_id}' from {server_metadata_url}: {e}. "
                f"It will be retried on first use."
            )

    return oauth
