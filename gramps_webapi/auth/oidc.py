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


def get_role_from_claims(user_claims: dict, role_claim: str = "groups") -> Optional[int]:
    """Map OIDC claims to Gramps roles based on environment variables.

    Args:
        user_claims: The user claims from OIDC token
        role_claim: The claim to look for roles/groups (e.g., 'groups', 'roles', 'realm_access.roles')

    Returns the highest role the user is entitled to based on claim membership,
    or None if no role mapping is configured (to preserve existing roles).
    Environment variables should be named OIDC_GROUP_<ROLE>.
    """
    role_mapping = {
        ROLE_ADMIN: os.getenv("OIDC_GROUP_ADMIN", ""),
        ROLE_OWNER: os.getenv("OIDC_GROUP_OWNER", ""),
        ROLE_EDITOR: os.getenv("OIDC_GROUP_EDITOR", ""),
        ROLE_CONTRIBUTOR: os.getenv("OIDC_GROUP_CONTRIBUTOR", ""),
        ROLE_MEMBER: os.getenv("OIDC_GROUP_MEMBER", ""),
        ROLE_GUEST: os.getenv("OIDC_GROUP_GUEST", ""),
    }

    # Check if any role mapping is configured
    has_role_mapping = any(group_name.strip() for group_name in role_mapping.values())
    if not has_role_mapping:
        logger.info("No OIDC role mapping configured (no OIDC_GROUP_* environment variables set). Preserving existing user roles.")
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
    tree: Optional[str] = None
) -> str:
    """Create or update a user based on OIDC userinfo.

    Returns the user GUID.
    """
    from flask import current_app

    # Get username from configurable claim with fallback to 'sub'
    username_claim = current_app.config.get("OIDC_USERNAME_CLAIM", "preferred_username")
    username = userinfo.get(username_claim) or userinfo.get("sub")

    email = userinfo.get("email", "")
    full_name = userinfo.get("name", "")
    groups = userinfo.get("groups", [])

    if not username:
        available_claims = ", ".join(userinfo.keys())
        raise ValueError(f"No username found in OIDC userinfo. Tried claim '{username_claim}' and fallback 'sub'. Available claims: {available_claims}")

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

    oidc_client = oauth.register(
        name="gramps",
        client_id=app.config["OIDC_CLIENT_ID"],
        client_secret=app.config["OIDC_CLIENT_SECRET"],
        server_metadata_url=app.config.get(
            "OIDC_OPENID_CONFIG_URL",
            f"{app.config['OIDC_ISSUER']}/.well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": app.config.get("OIDC_SCOPES", "openid email profile"),
        },
    )

    return oidc_client


def is_oidc_enabled() -> bool:
    """Check if OIDC is enabled in the current app."""
    return current_app.config.get("OIDC_ENABLED", False)