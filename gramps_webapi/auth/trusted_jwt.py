#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026           Gramps Development Team
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

"""Trusted JWT authentication support.

This module verifies JWT assertions from identity-aware proxies such as
Pomerium, Cloudflare Access, and Google Cloud IAP. It intentionally verifies
the signed assertion instead of trusting unsigned convenience headers.
"""

import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import jwt
from flask import current_app
from jwt import PyJWKClient

from .const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_DISABLED,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)

logger = logging.getLogger(__name__)

PROVIDER_TRUSTED_JWT = "trusted-jwt"
DEFAULT_JWT_ALGORITHMS = ["RS256", "ES256"]
FORBIDDEN_JWT_ALGORITHMS = {"NONE", "HS256", "HS384", "HS512"}

_ROLE_CONFIG = {
    ROLE_ADMIN: "TRUSTED_JWT_GROUP_ADMIN",
    ROLE_OWNER: "TRUSTED_JWT_GROUP_OWNER",
    ROLE_EDITOR: "TRUSTED_JWT_GROUP_EDITOR",
    ROLE_CONTRIBUTOR: "TRUSTED_JWT_GROUP_CONTRIBUTOR",
    ROLE_MEMBER: "TRUSTED_JWT_GROUP_MEMBER",
    ROLE_GUEST: "TRUSTED_JWT_GROUP_GUEST",
}

_ROLE_NAMES = {
    "admin": ROLE_ADMIN,
    "owner": ROLE_OWNER,
    "editor": ROLE_EDITOR,
    "contributor": ROLE_CONTRIBUTOR,
    "member": ROLE_MEMBER,
    "guest": ROLE_GUEST,
    "disabled": ROLE_DISABLED,
}


class TrustedJWTError(ValueError):
    """Trusted JWT authentication error with an HTTP status code."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def _get_app(app=None):
    return app or current_app


def _as_list(value: Any) -> List[str]:
    """Normalize config values that may be a string, list, tuple, or set."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_role(value: Any) -> int:
    """Normalize configured default role values."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _ROLE_NAMES:
            return _ROLE_NAMES[normalized]
        if normalized:
            try:
                return int(normalized)
            except ValueError as exc:
                raise ValueError(f"Invalid TRUSTED_JWT_DEFAULT_ROLE: {value}") from exc
    return ROLE_DISABLED


def _as_int(value: Any, default: int) -> int:
    """Normalize integer configuration values."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            logger.warning("Invalid Trusted JWT integer config value: %s", value)
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    """Normalize boolean configuration values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _claim_value(claims: Dict[str, Any], claim_name: str, default: Any = None) -> Any:
    """Read a direct or dotted claim from a JWT claims mapping."""
    if not claim_name:
        return default
    value: Any = claims
    for part in claim_name.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part)
        if value is None:
            return default
    return value


def _derived_provider_id(issuer: str) -> str:
    """Derive a stable provider ID from the issuer when one is not configured."""
    if not issuer:
        return PROVIDER_TRUSTED_JWT
    parsed = urlparse(issuer)
    source = parsed.netloc or parsed.path or issuer
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", source).strip("-").lower()
    return f"{PROVIDER_TRUSTED_JWT}-{slug}" if slug else PROVIDER_TRUSTED_JWT


def get_trusted_jwt_provider_id(app=None) -> str:
    """Return the configured Trusted JWT provider identifier."""
    app = _get_app(app)
    configured_provider_id = app.config.get("TRUSTED_JWT_PROVIDER_ID")
    if configured_provider_id:
        return configured_provider_id
    return _derived_provider_id(app.config.get("TRUSTED_JWT_ISSUER", ""))


def _contains_forbidden_algorithms(algorithms: Sequence[str]) -> bool:
    """Return True if a configured JWT algorithm is symmetric or unsigned."""
    normalized = {str(algorithm).upper() for algorithm in algorithms}
    return any(
        algorithm in FORBIDDEN_JWT_ALGORITHMS or algorithm.startswith("HS")
        for algorithm in normalized
    )


@lru_cache(maxsize=16)
def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    """Return a cached JWK client for a JWKS URL."""
    return PyJWKClient(jwks_url)


def get_trusted_jwt_provider_config(app=None) -> Optional[Dict[str, Any]]:
    """Get Trusted JWT provider configuration if it is complete enough to use."""
    app = _get_app(app)
    if not app.config.get("TRUSTED_JWT_ENABLED", False):
        return None

    header = app.config.get("TRUSTED_JWT_HEADER")
    jwks_url = app.config.get("TRUSTED_JWT_JWKS_URL")
    issuer = app.config.get("TRUSTED_JWT_ISSUER")
    audience = app.config.get("TRUSTED_JWT_AUDIENCE")
    if not (header and jwks_url and issuer and audience):
        logger.warning(
            "Trusted JWT is enabled but TRUSTED_JWT_HEADER, TRUSTED_JWT_JWKS_URL, "
            "TRUSTED_JWT_ISSUER, or TRUSTED_JWT_AUDIENCE is missing"
        )
        return None

    if _as_bool(app.config.get("TRUSTED_JWT_REQUIRE_HTTPS_JWKS", True), True):
        parsed_jwks_url = urlparse(jwks_url)
        if parsed_jwks_url.scheme != "https":
            logger.error("Trusted JWT JWKS URL must use https")
            return None

    algorithms = _as_list(app.config.get("TRUSTED_JWT_ALGORITHMS")) or list(
        DEFAULT_JWT_ALGORITHMS
    )
    if _contains_forbidden_algorithms(algorithms):
        logger.error(
            "Trusted JWT only supports asymmetric signature algorithms, got %s",
            algorithms,
        )
        return None

    return {
        "name": app.config.get("TRUSTED_JWT_NAME") or "Trusted JWT",
        "header": header,
        "jwks_url": jwks_url,
        "issuer": issuer,
        "audience": _as_list(audience),
        "algorithms": algorithms,
        "leeway": _as_int(app.config.get("TRUSTED_JWT_LEEWAY"), 30),
        "subject_claim": app.config.get("TRUSTED_JWT_SUBJECT_CLAIM", "sub"),
        "username_claim": app.config.get("TRUSTED_JWT_USERNAME_CLAIM", "email"),
        "email_claim": app.config.get("TRUSTED_JWT_EMAIL_CLAIM", "email"),
        "name_claim": app.config.get("TRUSTED_JWT_NAME_CLAIM", "name"),
        "role_claim": app.config.get("TRUSTED_JWT_ROLE_CLAIM", "groups"),
        "default_role": _as_role(app.config.get("TRUSTED_JWT_DEFAULT_ROLE")),
        "allowed_emails": _as_list(app.config.get("TRUSTED_JWT_ALLOWED_EMAILS")),
        "logout_url": app.config.get("TRUSTED_JWT_LOGOUT_URL", ""),
        "trusted_jwt": True,
    }


def is_trusted_jwt_provider(provider_id: str, app=None) -> bool:
    """Check whether a provider ID is the configured Trusted JWT provider."""
    config = get_trusted_jwt_provider_config(app)
    return bool(config and provider_id == get_trusted_jwt_provider_id(app))


def get_role_from_trusted_jwt_claims(claims: Dict[str, Any], app=None) -> Optional[int]:
    """Map Trusted JWT claims to a Gramps role.

    Returns a role only when TRUSTED_JWT_GROUP_* mapping is configured. If no
    mapping is configured, callers should use the default role for new users and
    preserve existing roles for existing users.
    """
    app = _get_app(app)
    role_mapping = {
        role: app.config.get(config_key, "")
        for role, config_key in _ROLE_CONFIG.items()
    }
    if not any(str(group).strip() for group in role_mapping.values()):
        logger.info("No Trusted JWT role mapping configured")
        return None

    role_claim = app.config.get("TRUSTED_JWT_ROLE_CLAIM", "groups")
    claim_value = _claim_value(claims, role_claim, [])
    if isinstance(claim_value, str):
        user_groups = [claim_value]
    elif isinstance(claim_value, Sequence):
        user_groups = [str(group) for group in claim_value]
    else:
        user_groups = []

    if not user_groups:
        logger.warning(
            "No '%s' claim found in Trusted JWT claims. Preserving existing roles.",
            role_claim,
        )
        return None

    for role_level in sorted(role_mapping.keys(), reverse=True):
        group_name = role_mapping[role_level]
        if group_name and group_name in user_groups:
            logger.info(
                "Trusted JWT %s %s mapped to role %s",
                role_claim,
                user_groups,
                role_level,
            )
            return role_level
    return ROLE_DISABLED


def verify_trusted_jwt(assertion: str, app=None) -> Dict[str, Any]:
    """Verify and decode a Trusted JWT assertion."""
    config = get_trusted_jwt_provider_config(app)
    if not config:
        raise TrustedJWTError("Trusted JWT authentication is not configured", 500)

    try:
        jwk_client = _get_jwk_client(config["jwks_url"])
        signing_key = jwk_client.get_signing_key_from_jwt(assertion)
        claims = jwt.decode(
            assertion,
            signing_key.key,
            algorithms=config["algorithms"],
            audience=config["audience"],
            issuer=config["issuer"],
            leeway=config["leeway"],
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid Trusted JWT: %s", exc)
        raise TrustedJWTError("Invalid trusted JWT") from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Could not verify Trusted JWT")
        raise TrustedJWTError("Could not verify trusted JWT") from exc

    subject_claim = config["subject_claim"]
    if not _claim_value(claims, subject_claim):
        raise TrustedJWTError(
            f"Trusted JWT is missing required subject claim '{subject_claim}'"
        )

    email_claim = config["email_claim"]
    email = _claim_value(claims, email_claim, "")
    allowed_emails = config["allowed_emails"]
    if allowed_emails and email not in allowed_emails:
        raise TrustedJWTError("Trusted JWT email is not allowed", 403)

    return claims


def get_trusted_jwt_userinfo_and_role(
    assertion: str, app=None
) -> Tuple[Dict[str, Any], Optional[int], int]:
    """Return userinfo, mapped role, and default role from a verified assertion."""
    app = _get_app(app)
    config = get_trusted_jwt_provider_config(app)
    if not config:
        raise TrustedJWTError("Trusted JWT authentication is not configured", 500)

    claims = verify_trusted_jwt(assertion, app)
    subject = _claim_value(claims, config["subject_claim"])
    userinfo = {
        "sub": str(subject),
        "email": _claim_value(claims, config["email_claim"], "") or "",
        "name": _claim_value(claims, config["name_claim"], "") or "",
    }

    username_claim = config["username_claim"]
    username = _claim_value(claims, username_claim)
    if username and username_claim not in userinfo:
        userinfo[username_claim] = username

    role_from_claims = get_role_from_trusted_jwt_claims(claims, app)
    return userinfo, role_from_claims, config["default_role"]
