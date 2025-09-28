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
from urllib.parse import urlencode

from flask import current_app, request, session, url_for
from webargs import fields

from ...auth import get_name, get_permissions, is_tree_disabled
from ...auth.oidc import create_or_update_oidc_user, is_oidc_enabled, get_available_oidc_providers, get_provider_config
from ...const import TREE_MULTI
from ..ratelimiter import limiter
from ..util import abort_with_message, get_config, get_tree_id, use_args
from . import Resource
from .token import get_tokens

logger = logging.getLogger(__name__)


class OIDCLoginResource(Resource):
    """Resource for initiating OIDC login flow.

    Endpoint: /api/oidc/login/
    """

    @limiter.limit("5/minute")
    @use_args(
        {
            "provider": fields.Str(required=True),
        },
        location="query",
    )
    def get(self, args):
        """Redirect to OIDC provider for authentication."""
        if not is_oidc_enabled():
            abort_with_message(405, "OIDC authentication is not enabled")

        provider_id = args.get("provider")

        # Validate provider is available
        available_providers = get_available_oidc_providers()
        if provider_id not in available_providers:
            abort_with_message(400, f"Provider '{provider_id}' is not available")

        oauth = current_app.extensions.get("authlib.integrations.flask_client")
        if not oauth:
            abort_with_message(500, "OIDC client not properly initialized")

        oidc_client = getattr(oauth, f"gramps_{provider_id}", None)
        if not oidc_client:
            abort_with_message(500, f"OIDC client for provider '{provider_id}' not found")

        # Build redirect URI with provider parameter
        redirect_uri = url_for("api.oidccallbackresource", provider=provider_id, _external=True)

        authorization_url = oidc_client.authorize_redirect(redirect_uri)
        return authorization_url


class OIDCCallbackResource(Resource):
    """Resource for handling OIDC callback.

    Endpoint: /api/oidc/callback/
    """

    @limiter.limit("5/minute")
    @use_args(
        {
            "provider": fields.Str(required=True),
            "tree": fields.Str(required=False),
            "code": fields.Str(required=False),
            "state": fields.Str(required=False),
            "session_state": fields.Str(required=False),
            "error": fields.Str(required=False),
            "error_description": fields.Str(required=False),
        },
        location="query",
    )
    def get(self, args):
        """Handle OIDC callback and create JWT tokens."""
        if not is_oidc_enabled():
            abort_with_message(405, "OIDC authentication is not enabled")

        provider_id = args.get("provider")

        # Validate provider is available
        available_providers = get_available_oidc_providers()
        if provider_id not in available_providers:
            abort_with_message(400, f"Provider '{provider_id}' is not available")

        oauth = current_app.extensions.get("authlib.integrations.flask_client")
        if not oauth:
            abort_with_message(500, "OIDC client not properly initialized")

        oidc_client = getattr(oauth, f"gramps_{provider_id}", None)
        if not oidc_client:
            abort_with_message(500, f"OIDC client for provider '{provider_id}' not found")

        try:
            token = oidc_client.authorize_access_token()

            # Handle different provider types for userinfo
            if provider_id == "github":
                # GitHub OAuth 2.0 - get user info from API
                resp = oidc_client.get("user", token=token)
                userinfo = resp.json()
            else:
                # Standard OIDC - get userinfo from userinfo endpoint
                userinfo = oidc_client.userinfo(token=token)

        except Exception as e:
            logger.exception(f"OIDC callback error for provider '{provider_id}'")
            abort_with_message(401, f"OIDC authentication failed for {provider_id}")

        tree = args.get("tree")
        if (
            tree
            and current_app.config["TREE"] != TREE_MULTI
            and tree != current_app.config["TREE"]
        ):
            abort_with_message(403, "Not allowed in single-tree setup")

        try:
            user_id = create_or_update_oidc_user(userinfo, tree, provider_id)
            username = get_name(user_id)
            tree_id = get_tree_id(user_id)

            if is_tree_disabled(tree=tree_id):
                abort_with_message(503, "This tree is temporarily disabled")

            permissions = get_permissions(username=username, tree=tree_id)

            tokens = get_tokens(
                user_id=user_id,
                permissions=permissions,
                tree_id=tree_id,
                include_refresh=True,
                fresh=True,
            )

            # Check if this is a browser request vs API request
            from flask import redirect, request as flask_request
            frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")

            # Check Accept header to determine if this is a browser or API request
            accept_header = flask_request.headers.get('Accept', '')
            is_browser_request = 'text/html' in accept_header

            if is_browser_request:
                # Browser request: redirect to frontend with secure HTTP-only cookies
                from flask import make_response
                response = make_response(redirect(f"{frontend_url}/oidc/complete"))

                # Set HTTP-only cookies (secure=False for localhost development)
                import os
                is_development = os.getenv('FLASK_ENV') == 'development' or 'localhost' in frontend_url or '127.0.0.1' in frontend_url

                response.set_cookie(
                    'oidc_access_token',
                    tokens['access_token'],
                    max_age=300,  # 5 minutes
                    httponly=True,
                    secure=not is_development,  # Allow HTTP in development
                    samesite='Lax',
                    path='/'
                )
                response.set_cookie(
                    'oidc_refresh_token',
                    tokens['refresh_token'],
                    max_age=300,  # 5 minutes
                    httponly=True,
                    secure=not is_development,  # Allow HTTP in development
                    samesite='Lax',
                    path='/'
                )

                logger.info(f"Set OIDC cookies, redirecting to {frontend_url}/oidc/complete")
                return response
            else:
                # API request: return JSON response
                from flask import jsonify
                return jsonify({
                    'access_token': tokens['access_token'],
                    'refresh_token': tokens['refresh_token'],
                    'token_type': 'Bearer',
                    'frontend_url': frontend_url
                })

        except ValueError as e:
            logger.error(f"Error creating/updating OIDC user for provider '{provider_id}': {e}")
            abort_with_message(400, f"Error processing user: {str(e)}")


class OIDCTokenExchangeResource(Resource):
    """Resource for securely exchanging OIDC tokens from cookies."""

    @limiter.limit("10/minute")
    def get(self):
        """Exchange HTTP-only cookies for tokens that can be stored in localStorage."""
        from flask import request as flask_request, make_response, jsonify
        import os

        logger.info("OIDC token exchange request received")
        logger.info(f"Cookies received: {list(flask_request.cookies.keys())}")

        # Get tokens from HTTP-only cookies
        access_token = flask_request.cookies.get('oidc_access_token')
        refresh_token = flask_request.cookies.get('oidc_refresh_token')

        logger.info(f"Access token found: {bool(access_token)}")
        logger.info(f"Refresh token found: {bool(refresh_token)}")

        if not access_token or not refresh_token:
            logger.error("No OIDC tokens found in cookies")
            abort_with_message(400, "No OIDC tokens found in cookies")

        # Return tokens and clear cookies
        response = make_response(jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer'
        }))

        # Clear the temporary cookies with same settings as when they were set
        frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")
        is_development = os.getenv('FLASK_ENV') == 'development' or 'localhost' in frontend_url or '127.0.0.1' in frontend_url

        response.set_cookie(
            'oidc_access_token',
            '',
            expires=0,
            httponly=True,
            secure=not is_development,
            samesite='Lax',
            path='/'
        )
        response.set_cookie(
            'oidc_refresh_token',
            '',
            expires=0,
            httponly=True,
            secure=not is_development,
            samesite='Lax',
            path='/'
        )

        logger.info("OIDC token exchange successful, cookies cleared")
        return response


class OIDCConfigResource(Resource):
    """Resource for getting OIDC configuration."""

    def get(self):
        """Get OIDC configuration for frontend."""
        if not is_oidc_enabled():
            return {"enabled": False}

        available_providers = get_available_oidc_providers()
        if not available_providers:
            return {"enabled": False}

        # Build provider list with display information
        providers = []
        for provider_id in available_providers:
            provider_config = get_provider_config(provider_id)
            if provider_config:
                providers.append({
                    "id": provider_id,
                    "name": provider_config["name"],
                    "login_url": url_for("api.oidcloginresource", provider=provider_id, _external=True),
                })

        return {
            "enabled": True,
            "providers": providers,
            "disable_local_auth": current_app.config.get("OIDC_DISABLE_LOCAL_AUTH", False),
            "auto_redirect": current_app.config.get("OIDC_AUTO_REDIRECT", True),
        }