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

"""OIDC authentication resources."""

import logging
from gettext import gettext as _
from urllib.parse import urlencode, urlparse

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
from marshmallow import EXCLUDE, Schema
from webargs import fields

from ...auth import get_name, get_user_details
from ...auth.oidc import (
    create_or_update_oidc_user,
    get_available_oidc_providers,
    get_provider_config,
)
from ...auth.oidc_helpers import is_oidc_enabled
from ...const import TREE_MULTI
from ..blueprint import api_blueprint
from ..ratelimiter import limiter
from ..util import abort_with_message, get_config, tree_exists
from . import Resource
from .schemas import OIDCConfigSchema, OIDCLogoutSchema, OIDCTokensSchema
from .token import get_tokens, get_tree_id_and_permissions

logger = logging.getLogger(__name__)

# Session key used to carry the tree across the round trip to the provider.
# It cannot be a query parameter on the redirect URI because providers require
# the redirect URI to match the registered one exactly.
SESSION_TREE_KEY = "oidc_tree"


def _get_oidc_client(provider_id: str | None) -> tuple[object, dict]:
    """Return the authlib client and configuration for a validated provider.

    Aborts the request if OIDC is disabled, the provider is unknown, or the
    client was not registered at startup.
    """
    if not is_oidc_enabled():
        abort_with_message(404, "OIDC authentication is not enabled")

    if not provider_id:
        abort_with_message(400, "Provider ID is required")

    if provider_id not in get_available_oidc_providers():
        abort_with_message(400, f"Provider '{provider_id}' is not available")

    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if not oauth:
        abort_with_message(500, "OIDC client not properly initialized")

    provider_config = get_provider_config(provider_id)

    oidc_client = getattr(oauth, f"gramps_{provider_id}", None)
    if not oidc_client:
        # get_available_oidc_providers() lists a built-in provider as soon as a
        # client ID is set, but init_oidc() only registers a client once the
        # secret is there too. In that case the provider is misconfigured
        # rather than broken - and /oidc/config/ does not advertise it either -
        # so answer as we would for an unknown provider.
        if not provider_config:
            abort_with_message(400, f"Provider '{provider_id}' is not available")
        abort_with_message(500, f"OIDC client for provider '{provider_id}' not found")

    return oidc_client, provider_config or {}


def _validate_tree(tree: str | None) -> str | None:
    """Validate the tree an OIDC login is scoped to.

    Mirrors the checks the registration endpoint applies, so that an OIDC login
    cannot create an account somewhere a registration could not.
    """
    is_multi = current_app.config["TREE"] == TREE_MULTI
    if not tree:
        if is_multi:
            abort_with_message(422, "tree is required")
        return None
    if not is_multi:
        # In a single-tree setup TREE holds the tree *name*, not the tree ID.
        # Accept it so that a client may pass it, but never propagate it: the
        # `users.tree` column holds tree IDs, and get_tree_id_or_none() already
        # resolves the single configured tree when the column is empty. Passing
        # the name on would store it verbatim and every later lookup would try
        # to open a tree by that name as if it were an ID.
        if tree != current_app.config["TREE"]:
            abort_with_message(422, "Not allowed in single-tree setup")
        return None
    if not tree_exists(tree):
        abort_with_message(422, "Tree does not exist")
    return tree


def _use_secure_cookies() -> bool:
    """Whether to set the Secure flag on the temporary OIDC cookies.

    Driven by the scheme actually in use rather than by hostname guessing: a
    Secure cookie is silently dropped by the browser over plain HTTP, while
    omitting the flag over HTTPS would expose the tokens. Both the configured
    frontend URL and the incoming request are consulted, because either one on
    its own can be misleading - `BASE_URL` is often left at its localhost
    default, and `request.is_secure` is false behind a TLS-terminating proxy
    unless forwarding headers are honoured.
    """
    frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")
    if urlparse(frontend_url or "").scheme == "https":
        return True
    return request.is_secure


class OIDCLoginQueryArgs(Schema):
    """Query arguments for GET /oidc/login."""

    provider = fields.Str(
        required=True,
        metadata={"description": "The OIDC provider ID (e.g. 'google', 'microsoft')."},
    )
    tree = fields.Str(
        required=False,
        metadata={
            "description": (
                "Tree ID to associate with the OIDC login. Required for"
                " multi-tree installations."
            )
        },
    )


class OIDCLoginResource(Resource):
    """Resource for initiating OIDC login flow.

    Endpoint: /api/oidc/login/
    """

    @limiter.limit("5/minute")
    @api_blueprint.arguments(OIDCLoginQueryArgs, location="query")
    def get(self, args):
        """Redirect to OIDC provider for authentication."""
        provider_id = args.get("provider")
        oidc_client, _config = _get_oidc_client(provider_id)

        # Validate the tree up front so a misconfigured request fails here with
        # a useful message instead of after a round trip to the provider, and
        # stash it in the session for the callback to pick up. It cannot be
        # passed on the redirect URI, which has to match the registered one.
        session[SESSION_TREE_KEY] = _validate_tree(args.get("tree"))

        # Build redirect URI with provider in path (Microsoft-compatible)
        # Using path parameter instead of query parameter for broader compatibility
        base_url = get_config("BASE_URL")
        redirect_uri = f"{base_url.rstrip('/')}/api/oidc/callback/{provider_id}"

        authorization_url = oidc_client.authorize_redirect(redirect_uri)
        return authorization_url


class OIDCCallbackQueryArgs(Schema):
    """Query arguments for GET /oidc/callback."""

    class Meta:
        unknown = EXCLUDE

    provider = fields.Str(
        required=False,
        metadata={"description": "The OIDC provider ID (e.g. 'google', 'microsoft')."},
    )  # Optional for backwards compatibility
    tree = fields.Str(
        required=False,
        metadata={
            "description": (
                "Tree ID to associate with the OIDC login. Deprecated: the tree"
                " is now carried in the session from /oidc/login/, since"
                " providers require an exact redirect URI match."
            )
        },
    )
    code = fields.Str(
        required=False,
        metadata={"description": "Authorization code returned by the OIDC provider."},
    )
    state = fields.Str(
        required=False,
        metadata={"description": "State parameter returned by the OIDC provider."},
    )
    session_state = fields.Str(
        required=False,
        metadata={
            "description": "Session state parameter returned by the OIDC provider."
        },
    )
    error = fields.Str(
        required=False,
        metadata={"description": "Error code returned by the OIDC provider."},
    )
    error_description = fields.Str(
        required=False,
        metadata={"description": "Error description returned by the OIDC provider."},
    )


class OIDCCallbackResource(Resource):
    """Resource for handling OIDC callback.

    Endpoint: /api/oidc/callback/ (legacy with query param)
    Endpoint: /api/oidc/callback/<provider_id> (path param, Microsoft-compatible)
    """

    @limiter.limit("5/minute")
    @api_blueprint.arguments(OIDCCallbackQueryArgs, location="query", unknown=EXCLUDE)
    def get(self, args, provider_id=None):
        """Handle OIDC callback and create JWT tokens.

        Args:
            args: Query parameters
            provider_id: Provider ID from path parameter (if using path-based route)
        """
        # Support both path parameter (new, Microsoft-compatible) and query parameter (legacy)
        provider_id = provider_id or args.get("provider")
        oidc_client, provider_config = _get_oidc_client(provider_id)

        try:
            # Some providers issue tokens whose `iss` claim does not match the
            # issuer in their discovery document (see `relax_issuer` in
            # BUILTIN_PROVIDERS). Security note: relaxing this does not allow
            # arbitrary OIDC providers, because `provider_id` was already
            # validated against the configured providers list and mapped to a
            # preconfigured client before reaching this code.
            if provider_config.get("relax_issuer"):
                token = oidc_client.authorize_access_token(
                    claims_options={"iss": {"essential": False}}
                )
            else:
                token = oidc_client.authorize_access_token()

            userinfo = dict(oidc_client.userinfo(token=token))
            # Some providers (e.g. Microsoft Entra) return authorization
            # claims such as app roles or group memberships only in the ID
            # token, not from the userinfo endpoint. Merge any ID-token
            # claims missing from the userinfo response so that role
            # mapping via OIDC_ROLE_CLAIM works consistently across
            # providers. userinfo endpoint values take precedence.
            # Guard against a non-mapping value under "userinfo": an
            # unexpected shape must be ignored, not turn a successful
            # login into a 401.
            id_token_claims = token.get("userinfo")
            if isinstance(id_token_claims, dict):
                for claim, value in id_token_claims.items():
                    userinfo.setdefault(claim, value)

        except Exception:  # pylint: disable=broad-except
            logger.exception("OIDC callback error for provider '%s'", provider_id)
            abort_with_message(401, f"OIDC authentication failed for {provider_id}")

        # The tree is put into the session by /oidc/login/. The query parameter
        # is only a fallback for logins started before this was introduced.
        tree = _validate_tree(session.pop(SESSION_TREE_KEY, None) or args.get("tree"))

        try:
            user_id = create_or_update_oidc_user(userinfo, tree, provider_id)
            username = get_name(user_id)

            # Resolve the tree, reject a disabled one and look up permissions
            # exactly as the local login endpoint does, so that the two ways of
            # obtaining a token cannot drift apart.
            tree_id, permissions = get_tree_id_and_permissions(
                user_id=user_id, username=username
            )

            # Check if user account is disabled (same as local auth flow)
            user_details = get_user_details(username)
            if user_details and user_details["role"] < 0:
                # User account is disabled - show confirmation page like local registration
                title = _("Account Under Review")
                message = _(
                    "Your account has been created successfully. "
                    "An administrator will review your account request and activate it shortly."
                )
                return render_template(
                    "confirmation.html", title=title, message=message
                )

            # User is enabled - proceed with normal token flow
            tokens = get_tokens(
                user_id=user_id,
                permissions=permissions,
                tree_id=tree_id,
                include_refresh=True,
                fresh=True,
                oidc_provider=provider_id,
            )

            # Redirect to frontend with secure HTTP-only cookies
            frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")
            response = redirect(f"{frontend_url.rstrip('/')}/oidc/complete")

            secure = _use_secure_cookies()

            response.set_cookie(
                "oidc_access_token",
                tokens["access_token"],
                max_age=300,  # 5 minutes
                httponly=True,
                secure=secure,
                samesite="Lax",
                path="/",
            )
            response.set_cookie(
                "oidc_refresh_token",
                tokens["refresh_token"],
                max_age=300,  # 5 minutes
                httponly=True,
                secure=secure,
                samesite="Lax",
                path="/",
            )

            # Store id_token if available (needed for OIDC logout)
            if token.get("id_token"):
                response.set_cookie(
                    "oidc_id_token",
                    token["id_token"],
                    max_age=300,  # 5 minutes
                    httponly=True,
                    secure=secure,
                    samesite="Lax",
                    path="/",
                )

            logger.debug(
                f"Set OIDC cookies, redirecting to {frontend_url}/oidc/complete"
            )
            return response

        except ValueError as e:
            logger.exception(
                f"Error creating/updating OIDC user for provider '{provider_id}'"
            )
            abort_with_message(400, f"Error processing user: {str(e)}")


class OIDCTokenExchangeResource(Resource):
    """Resource for securely exchanging OIDC tokens from cookies."""

    @api_blueprint.response(200, OIDCTokensSchema())
    @limiter.limit("10/minute")
    def get(self):
        """Exchange HTTP-only cookies for tokens that can be stored in localStorage."""
        # Get tokens from HTTP-only cookies
        access_token = request.cookies.get("oidc_access_token")
        refresh_token = request.cookies.get("oidc_refresh_token")
        id_token = request.cookies.get("oidc_id_token")

        if not access_token or not refresh_token:
            logger.warning(
                "OIDC token exchange with no tokens in cookies; "
                f"cookies present: {sorted(request.cookies)}"
            )
            abort_with_message(400, "No OIDC tokens found in cookies")

        # Return tokens and clear cookies
        response_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
        }

        # Include id_token if available (needed for OIDC logout)
        if id_token:
            response_data["id_token"] = id_token

        response = jsonify(response_data)

        # Clear the temporary cookies with same settings as when they were set
        secure = _use_secure_cookies()
        for name in ("oidc_access_token", "oidc_refresh_token", "oidc_id_token"):
            response.set_cookie(
                name,
                "",
                expires=0,
                httponly=True,
                secure=secure,
                samesite="Lax",
                path="/",
            )

        logger.debug("OIDC token exchange successful, cookies cleared")
        return response


class OIDCConfigResource(Resource):
    """Resource for getting OIDC configuration."""

    @api_blueprint.response(200, OIDCConfigSchema())
    def get(self):
        """Get OIDC configuration for frontend."""
        if not is_oidc_enabled():
            return {"enabled": False}

        available_providers = get_available_oidc_providers()
        if not available_providers:
            return {"enabled": False}

        # Build provider list with display information
        base_url = get_config("BASE_URL")
        providers = []
        for provider_id in available_providers:
            provider_config = get_provider_config(provider_id)
            if provider_config:
                providers.append(
                    {
                        "id": provider_id,
                        "name": provider_config["name"],
                        "login_url": f"{base_url.rstrip('/')}/api/oidc/login/?provider={provider_id}",
                    }
                )

        return {
            "enabled": True,
            "providers": providers,
            "disable_local_auth": current_app.config.get(
                "OIDC_DISABLE_LOCAL_AUTH", False
            ),
            "auto_redirect": current_app.config.get("OIDC_AUTO_REDIRECT", False),
        }


class OIDCLogoutQueryArgs(Schema):
    """Query arguments for GET /oidc/logout."""

    provider = fields.Str(
        required=True,
        metadata={"description": "The OIDC provider ID (e.g. 'google', 'microsoft')."},
    )
    id_token = fields.Str(
        required=False,
        metadata={"description": "ID token to use as id_token_hint for logout."},
    )
    post_logout_redirect_uri = fields.Str(
        required=False,
        metadata={"description": "URI to redirect to after logout."},
    )


class OIDCLogoutResource(Resource):
    """Resource for getting OIDC logout URL."""

    @api_blueprint.response(200, OIDCLogoutSchema())
    @api_blueprint.arguments(OIDCLogoutQueryArgs, location="query")
    def get(self, args):
        """Get OIDC logout URL for the specified provider.

        Returns the end_session_endpoint URL from the provider's OIDC discovery document.
        If the provider doesn't support logout, returns None for graceful degradation.
        """
        provider_id = args.get("provider")
        oidc_client, _config = _get_oidc_client(provider_id)

        try:
            # Load server metadata to get end_session_endpoint
            oidc_client.load_server_metadata()
            end_session_endpoint = oidc_client.server_metadata.get(
                "end_session_endpoint"
            )

            if not end_session_endpoint:
                # Provider doesn't support OIDC logout - graceful degradation
                return {"logout_url": None}

            # Build logout URL with optional parameters
            params = {}
            if args.get("id_token"):
                params["id_token_hint"] = args.get("id_token")
            if args.get("post_logout_redirect_uri"):
                params["post_logout_redirect_uri"] = args.get(
                    "post_logout_redirect_uri"
                )

            logout_url = end_session_endpoint
            if params:
                logout_url = f"{end_session_endpoint}?{urlencode(params)}"

            return {"logout_url": logout_url}

        except Exception:  # pylint: disable=broad-except
            logger.exception(f"Error getting logout URL for provider '{provider_id}'")
            # On error, gracefully degrade to local logout only
            return {"logout_url": None}
