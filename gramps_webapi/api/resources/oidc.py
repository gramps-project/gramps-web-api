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
import secrets
from gettext import gettext as _
from urllib.parse import urlencode

from flask import (
    current_app,
    redirect,
    render_template,
    session,
)
from flask_jwt_extended import get_jwt_identity
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from marshmallow import EXCLUDE, Schema
from sqlalchemy.exc import IntegrityError
from webargs import fields

from ...auth import (
    create_oidc_account,
    get_name,
    get_oidc_account,
    get_user_details,
    user_db,
)
from ...auth.oidc import (
    configure_pkce,
    create_or_update_oidc_user,
    get_available_oidc_providers,
    get_provider_config,
)
from ...auth.oidc_helpers import is_oidc_enabled
from ...const import TREE_MULTI
from ..blueprint import api_blueprint
from ..cache import persistent_cache
from ..ratelimiter import limiter
from ..util import abort_with_message, get_config, tree_exists
from . import FreshProtectedResource, Resource
from .schemas import (
    OIDCConfigSchema,
    OIDCLinkSchema,
    OIDCLinkTicketSchema,
    OIDCLogoutSchema,
    OIDCTokenExchangeSchema,
    OIDCTokensSchema,
)
from .token import get_tokens, get_tree_id_and_permissions

logger = logging.getLogger(__name__)

# Session key used to carry the tree ID across the round trip to the provider.
# It cannot be a query parameter on the redirect URI because providers require
# the redirect URI to match the registered one exactly.
SESSION_TREE_KEY = "oidc_tree"

# Prefix for the server-side entry holding the tokens of a pending exchange.
OIDC_CODE_PREFIX = "oidc_code:"

# Seconds a code stays redeemable, i.e. how long the frontend has to load.
OIDC_CODE_TIMEOUT = 120

# The cached entries outlive the code itself, so that an expired code is always
# reported as expired rather than as a missing entry, and so that a redeemed one
# is still known to have been redeemed.
OIDC_CODE_CACHE_TIMEOUT = OIDC_CODE_TIMEOUT + 60

# Session key holding a pending link: the user and provider the next callback
# adds the identity for, instead of logging in.
SESSION_LINK_KEY = "oidc_link"

# Session key holding the nonce that binds a link ticket to the browser that
# requested it, so that a ticket sent to someone else cannot be completed with
# their identity.
SESSION_LINK_NONCE_KEY = "oidc_link_nonce"

# Prefix for the cache entry marking a link ticket as used.
OIDC_LINK_PREFIX = "oidc_link_ticket:"

# Seconds a link ticket stays valid.
OIDC_LINK_TICKET_TIMEOUT = 120


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


def _validate_tree_id(tree_id: str | None) -> str | None:
    """Validate the tree an OIDC login is scoped to.

    Mirrors the checks the registration endpoint applies, so that an OIDC login
    cannot create an account somewhere a registration could not.
    """
    is_multi = current_app.config["TREE"] == TREE_MULTI
    if not tree_id:
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
        if tree_id != current_app.config["TREE"]:
            abort_with_message(422, "Not allowed in single-tree setup")
        return None
    if not tree_exists(tree_id):
        abort_with_message(422, "Tree does not exist")
    return tree_id


def _code_serializer() -> URLSafeTimedSerializer:
    """Serializer signing the exchange code, so its origin and age are provable."""
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt="oidc-exchange-code"
    )


def _store_exchange_code(tokens: dict) -> str:
    """Park the tokens server-side and return the code that redeems them."""
    code_id = secrets.token_urlsafe(32)
    persistent_cache.set(
        f"{OIDC_CODE_PREFIX}{code_id}", tokens, timeout=OIDC_CODE_CACHE_TIMEOUT
    )
    return _code_serializer().dumps(code_id)


def _redeem_exchange_code(code: str) -> dict:
    """Return the tokens for a code, consuming it so it works only once."""
    try:
        code_id = _code_serializer().loads(code, max_age=OIDC_CODE_TIMEOUT)
    except SignatureExpired:
        abort_with_message(
            400, "The OIDC exchange code has expired, please log in again"
        )
    except BadSignature:
        abort_with_message(400, "Invalid OIDC exchange code")

    key = f"{OIDC_CODE_PREFIX}{code_id}"
    claim_key = f"{key}:claimed"
    entry = persistent_cache.get(key)

    # Claiming with add() rather than checking and then writing, so that two
    # simultaneous requests cannot both redeem the same code.
    if not persistent_cache.add(claim_key, "1", timeout=OIDC_CODE_CACHE_TIMEOUT):
        abort_with_message(400, "The OIDC exchange code has already been used")

    if entry is None:
        # The signature proves this server issued the code and that it is not
        # yet expired, so the entry it names should still be in the cache.
        persistent_cache.delete(claim_key)
        logger.error(
            "The persistent cache did not retain a valid OIDC exchange code."
            " OIDC login requires a cache shared by every worker and replica,"
            " such as Redis; a per-process or disabled cache cannot work."
        )
        abort_with_message(
            500,
            "Login could not be completed because the server did not retain the"
            " pending tokens. The persistent cache is most likely disabled, or"
            " not shared between workers.",
        )

    persistent_cache.delete(key)
    return entry


def _link_serializer() -> URLSafeTimedSerializer:
    """Serializer signing link tickets."""
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt="oidc-link-ticket"
    )


def _redeem_link_ticket(ticket: str, provider_id: str) -> dict:
    """Check a link ticket and return the pending link it stands for.

    The ticket must be unexpired and unused, name the provider being logged in
    to, and come from the browser that requested it.
    """
    try:
        data = _link_serializer().loads(ticket, max_age=OIDC_LINK_TICKET_TIMEOUT)
    except SignatureExpired:
        abort_with_message(400, "The link ticket has expired, please try again")
    except BadSignature:
        abort_with_message(400, "Invalid link ticket")

    if data.get("provider") != provider_id:
        abort_with_message(400, "The link ticket is for a different provider")

    nonce = session.pop(SESSION_LINK_NONCE_KEY, None)
    if not nonce or not secrets.compare_digest(nonce, data.get("nonce", "")):
        abort_with_message(
            403, "Linking must be completed in the browser where it was started"
        )

    if not persistent_cache.add(
        f"{OIDC_LINK_PREFIX}{data['id']}", "1", timeout=OIDC_LINK_TICKET_TIMEOUT + 60
    ):
        abort_with_message(400, "The link ticket has already been used")

    return {"user_id": data["user_id"], "provider": provider_id}


def _complete_url(**fragment: str) -> str:
    """Return the frontend's OIDC completion URL with a result in the fragment."""
    frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")
    return f"{frontend_url.rstrip('/')}/oidc/complete#{urlencode(fragment)}"


def _complete_link(link: dict, provider_id: str, userinfo: dict):
    """Add the provider identity to the user of a pending link.

    The callback is a browser redirect, so the result is reported in the
    fragment of the frontend's completion page rather than as an HTTP error.
    No tokens are issued, and the user's role, name and email are left alone.
    """
    user_id = link["user_id"]
    subject_id = userinfo.get("sub")
    if link["provider"] != provider_id or not subject_id:
        return redirect(_complete_url(error="link_failed"))

    try:
        user_details = get_user_details(get_name(user_id))
    except ValueError:
        user_details = None
    if not user_details or user_details["role"] < 0:
        return redirect(_complete_url(error="link_failed"))

    owner_id = get_oidc_account(provider_id, subject_id)
    if owner_id is not None:
        if str(owner_id) != str(user_id):
            logger.info(
                "Refused to link %s identity already used by another account",
                provider_id,
            )
            return redirect(_complete_url(error="identity_in_use"))
        return redirect(_complete_url(linked=provider_id))

    try:
        create_oidc_account(user_id, provider_id, subject_id, userinfo.get("email"))
    except IntegrityError:
        # Linked to another account between the check and the insert.
        user_db.session.rollback()  # pylint: disable=no-member
        return redirect(_complete_url(error="identity_in_use"))
    logger.info("Linked a %s identity to an existing account", provider_id)
    return redirect(_complete_url(linked=provider_id))


class OIDCLinkResource(FreshProtectedResource):
    """Resource for starting to link an OIDC identity to the current user.

    Endpoint: /api/oidc/link/
    """

    @api_blueprint.response(200, OIDCLinkTicketSchema())
    @api_blueprint.arguments(OIDCLinkSchema, location="json")
    @limiter.limit("5/minute")
    def post(self, args):
        """Return a ticket for linking a provider identity to the current user.

        Requires a fresh login. The client then navigates to
        /oidc/login/?provider=...&link=<ticket> in the same browser; the
        callback reports the result in the fragment of the frontend's
        /oidc/complete page, as `linked=<provider>` or `error=<reason>`.
        """
        provider_id = args["provider"]
        _get_oidc_client(provider_id)
        nonce = secrets.token_urlsafe(16)
        session[SESSION_LINK_NONCE_KEY] = nonce
        ticket = _link_serializer().dumps(
            {
                "id": secrets.token_urlsafe(16),
                "user_id": str(get_jwt_identity()),
                "provider": provider_id,
                "nonce": nonce,
            }
        )
        return {"ticket": ticket}


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
                "ID of the tree to associate with the OIDC login. Required for"
                " multi-tree installations, optional in single-tree ones."
                " Ignored when linking."
            )
        },
    )
    link = fields.Str(
        required=False,
        metadata={
            "description": (
                "Ticket from /oidc/link/. If given, the identity is linked to"
                " the ticket's user instead of logging in."
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

        if args.get("link"):
            session[SESSION_LINK_KEY] = _redeem_link_ticket(args["link"], provider_id)
            session.pop(SESSION_TREE_KEY, None)
        else:
            # A link started earlier in this browser and never completed must
            # not turn this login into a link.
            session.pop(SESSION_LINK_KEY, None)
            # Validate the tree up front so a misconfigured request fails here
            # with a useful message instead of after a round trip to the
            # provider, and stash it in the session for the callback to pick
            # up. It cannot be passed on the redirect URI, which has to match
            # the registered one.
            session[SESSION_TREE_KEY] = _validate_tree_id(args.get("tree"))

        # Build redirect URI with provider in path (Microsoft-compatible)
        # Using path parameter instead of query parameter for broader compatibility
        base_url = get_config("BASE_URL")
        redirect_uri = f"{base_url.rstrip('/')}/api/oidc/callback/{provider_id}"

        configure_pkce(oidc_client, _config)
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
                "ID of the tree to associate with the OIDC login. Deprecated:"
                " the tree is now carried in the session from /oidc/login/,"
                " since providers require an exact redirect URI match."
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
        link = session.pop(SESSION_LINK_KEY, None)

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
            if link:
                return redirect(_complete_url(error="link_failed"))
            abort_with_message(401, f"OIDC authentication failed for {provider_id}")

        if link:
            return _complete_link(link, provider_id, userinfo)

        # The tree is put into the session by /oidc/login/. The query parameter
        # is only a fallback for logins started before this was introduced.
        tree_id = _validate_tree_id(
            session.pop(SESSION_TREE_KEY, None) or args.get("tree")
        )

        try:
            user_id = create_or_update_oidc_user(userinfo, tree_id, provider_id)
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

            exchange_tokens = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
            }
            # Keep the id_token around, it is needed as id_token_hint on logout.
            if token.get("id_token"):
                exchange_tokens["id_token"] = token["id_token"]

            code = _store_exchange_code(exchange_tokens)

            # In the fragment, which is not sent to the frontend's web server.
            frontend_url = get_config("FRONTEND_URL") or get_config("BASE_URL")
            complete_url = f"{frontend_url.rstrip('/')}/oidc/complete#code={code}"

            logger.debug(f"Redirecting to {frontend_url}/oidc/complete with code")
            return redirect(complete_url)

        except ValueError as e:
            logger.exception(
                f"Error creating/updating OIDC user for provider '{provider_id}'"
            )
            abort_with_message(400, f"Error processing user: {str(e)}")


class OIDCTokenExchangeResource(Resource):
    """Resource for exchanging a single-use OIDC code for tokens."""

    @api_blueprint.response(200, OIDCTokensSchema())
    @api_blueprint.arguments(OIDCTokenExchangeSchema, location="json")
    @limiter.limit("10/minute")
    def post(self, args):
        """Exchange the code from the login redirect for tokens."""
        tokens = _redeem_exchange_code(args["code"])

        response_data = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "Bearer",
        }

        # Include id_token if available (needed for OIDC logout)
        if tokens.get("id_token"):
            response_data["id_token"] = tokens["id_token"]

        logger.debug("OIDC token exchange successful, code consumed")
        return response_data


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
