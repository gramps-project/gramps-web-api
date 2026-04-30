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

"""Tests for Trusted JWT authentication logic."""

import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Flask
from jwt.algorithms import ECAlgorithm
from werkzeug.exceptions import HTTPException

from gramps_webapi.auth import trusted_jwt as trusted_jwt_module
from gramps_webapi.auth.const import ROLE_DISABLED, ROLE_EDITOR, ROLE_OWNER
from gramps_webapi.auth.oidc import ROLE_FROM_CLAIMS_UNSET
from gramps_webapi.auth.trusted_jwt import (
    TrustedJWTError,
    get_role_from_trusted_jwt_claims,
    get_trusted_jwt_provider_config,
    get_trusted_jwt_provider_id,
    get_trusted_jwt_userinfo_and_role,
    verify_trusted_jwt,
)
from gramps_webapi.api.resources.oidc import (
    _complete_external_login,
    _is_oidc_or_trusted_jwt_enabled,
    _trusted_jwt_login,
)


def _mock_app(config):
    app = MagicMock()
    defaults = {
        "TRUSTED_JWT_ENABLED": True,
        "TRUSTED_JWT_PROVIDER_ID": "trusted-jwt",
        "TRUSTED_JWT_NAME": "Trusted JWT",
        "TRUSTED_JWT_HEADER": "X-Pomerium-Jwt-Assertion",
        "TRUSTED_JWT_JWKS_URL": "https://app.example.com/.well-known/pomerium/jwks.json",
        "TRUSTED_JWT_ISSUER": "https://auth.example.com",
        "TRUSTED_JWT_AUDIENCE": "https://app.example.com",
        "TRUSTED_JWT_ALGORITHMS": ["ES256"],
        "TRUSTED_JWT_LEEWAY": 30,
        "TRUSTED_JWT_REQUIRE_HTTPS_JWKS": True,
        "TRUSTED_JWT_SUBJECT_CLAIM": "sub",
        "TRUSTED_JWT_USERNAME_CLAIM": "email",
        "TRUSTED_JWT_EMAIL_CLAIM": "email",
        "TRUSTED_JWT_NAME_CLAIM": "name",
        "TRUSTED_JWT_ROLE_CLAIM": "groups",
        "TRUSTED_JWT_DEFAULT_ROLE": ROLE_DISABLED,
        "TRUSTED_JWT_ALLOWED_EMAILS": [],
        "TRUSTED_JWT_GROUP_ADMIN": "",
        "TRUSTED_JWT_GROUP_OWNER": "",
        "TRUSTED_JWT_GROUP_EDITOR": "",
        "TRUSTED_JWT_GROUP_CONTRIBUTOR": "",
        "TRUSTED_JWT_GROUP_MEMBER": "",
        "TRUSTED_JWT_GROUP_GUEST": "",
        "TRUSTED_JWT_LOGOUT_URL": "",
    }
    defaults.update(config)
    app.config.get.side_effect = lambda key, default=None: defaults.get(key, default)
    return app


def test_provider_config_disabled():
    app = _mock_app({"TRUSTED_JWT_ENABLED": False})
    assert get_trusted_jwt_provider_config(app) is None


def test_provider_config_requires_header_jwks_issuer_and_audience():
    app = _mock_app({"TRUSTED_JWT_HEADER": ""})
    assert get_trusted_jwt_provider_config(app) is None


def test_provider_config_parses_strings_and_role_names():
    app = _mock_app(
        {
            "TRUSTED_JWT_PROVIDER_ID": "pomerium",
            "TRUSTED_JWT_ALGORITHMS": "RS256,ES256",
            "TRUSTED_JWT_ALLOWED_EMAILS": "a@example.com, b@example.com",
            "TRUSTED_JWT_DEFAULT_ROLE": "owner",
        }
    )
    config = get_trusted_jwt_provider_config(app)
    assert get_trusted_jwt_provider_id(app) == "pomerium"
    assert config["algorithms"] == ["RS256", "ES256"]
    assert config["allowed_emails"] == ["a@example.com", "b@example.com"]
    assert config["default_role"] == ROLE_OWNER


def test_provider_id_is_derived_from_issuer_when_not_configured():
    app = _mock_app({"TRUSTED_JWT_PROVIDER_ID": ""})
    assert get_trusted_jwt_provider_id(app) == "trusted-jwt-auth-example-com"


def test_provider_config_rejects_insecure_jwks_url_by_default():
    app = _mock_app({"TRUSTED_JWT_JWKS_URL": "http://app.example.com/jwks.json"})
    assert get_trusted_jwt_provider_config(app) is None


def test_provider_config_can_allow_non_https_jwks_for_dev():
    app = _mock_app(
        {
            "TRUSTED_JWT_JWKS_URL": "http://localhost:8080/jwks.json",
            "TRUSTED_JWT_REQUIRE_HTTPS_JWKS": False,
        }
    )
    assert get_trusted_jwt_provider_config(app)["jwks_url"].startswith("http://")


def test_provider_config_rejects_unsigned_and_symmetric_algorithms():
    app = _mock_app({"TRUSTED_JWT_ALGORITHMS": "RS256,HS256"})
    assert get_trusted_jwt_provider_config(app) is None


def test_trusted_jwt_enabled_without_oidc_flag():
    app = Flask(__name__)
    app.config.update(
        {
            "OIDC_ENABLED": False,
            "TRUSTED_JWT_ENABLED": True,
            "TRUSTED_JWT_PROVIDER_ID": "pomerium",
            "TRUSTED_JWT_NAME": "Pomerium",
            "TRUSTED_JWT_HEADER": "X-Pomerium-Jwt-Assertion",
            "TRUSTED_JWT_JWKS_URL": "https://app.example.com/.well-known/pomerium/jwks.json",
            "TRUSTED_JWT_ISSUER": "https://auth.example.com",
            "TRUSTED_JWT_AUDIENCE": "https://app.example.com",
        }
    )

    with app.app_context():
        assert _is_oidc_or_trusted_jwt_enabled() is True


def test_verify_trusted_jwt_uses_strict_validation_options():
    app = _mock_app({})
    claims = {
        "sub": "user-123",
        "email": "person@example.com",
        "iss": "https://auth.example.com",
        "aud": "https://app.example.com",
        "exp": 1893456000,
    }
    mock_key = MagicMock()
    mock_key.key = "public-key"

    with patch("gramps_webapi.auth.trusted_jwt._get_jwk_client") as mock_client:
        with patch("gramps_webapi.auth.trusted_jwt.jwt.decode") as mock_decode:
            mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
            mock_decode.return_value = claims
            assert verify_trusted_jwt("assertion", app) == claims
            mock_client.assert_called_once_with(
                "https://app.example.com/.well-known/pomerium/jwks.json"
            )
            mock_decode.assert_called_once_with(
                "assertion",
                "public-key",
                algorithms=["ES256"],
                audience=["https://app.example.com"],
                issuer="https://auth.example.com",
                leeway=30,
                options={"require": ["exp", "iss", "aud"]},
            )


def test_verify_trusted_jwt_rejects_invalid_tokens():
    app = _mock_app({})
    with patch("gramps_webapi.auth.trusted_jwt._get_jwk_client") as mock_client:
        mock_client.return_value.get_signing_key_from_jwt.side_effect = (
            jwt.InvalidTokenError("bad token")
        )
        with pytest.raises(TrustedJWTError, match="Invalid trusted JWT"):
            verify_trusted_jwt("assertion", app)


def test_verify_trusted_jwt_rejects_disallowed_email():
    app = _mock_app({"TRUSTED_JWT_ALLOWED_EMAILS": ["allowed@example.com"]})
    claims = {
        "sub": "user-123",
        "email": "blocked@example.com",
        "iss": "https://auth.example.com",
        "aud": "https://app.example.com",
        "exp": 1893456000,
    }
    mock_key = MagicMock()
    mock_key.key = "public-key"

    with patch("gramps_webapi.auth.trusted_jwt._get_jwk_client") as mock_client:
        with patch("gramps_webapi.auth.trusted_jwt.jwt.decode", return_value=claims):
            mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
            with pytest.raises(TrustedJWTError) as exc_info:
                verify_trusted_jwt("assertion", app)
            assert exc_info.value.status_code == 403


def _signed_es256_token(claims):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "ES256"})
    token = jwt.encode(
        claims,
        private_key,
        algorithm="ES256",
        headers={"kid": "test-key"},
    )
    return token, {"keys": [public_jwk]}


def test_verify_trusted_jwt_validates_real_signed_token():
    app = _mock_app({})
    token, jwks = _signed_es256_token(
        {
            "sub": "user-123",
            "email": "person@example.com",
            "iss": "https://auth.example.com",
            "aud": "https://app.example.com",
            "exp": int(time.time()) + 3600,
        }
    )

    trusted_jwt_module._get_jwk_client.cache_clear()
    with patch(
        "gramps_webapi.auth.trusted_jwt.PyJWKClient.fetch_data",
        return_value=jwks,
    ):
        claims = verify_trusted_jwt(token, app)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "person@example.com"


def test_verify_trusted_jwt_rejects_wrong_issuer_with_real_signature():
    app = _mock_app({})
    token, jwks = _signed_es256_token(
        {
            "sub": "user-123",
            "email": "person@example.com",
            "iss": "https://wrong.example.com",
            "aud": "https://app.example.com",
            "exp": int(time.time()) + 3600,
        }
    )

    trusted_jwt_module._get_jwk_client.cache_clear()
    with patch(
        "gramps_webapi.auth.trusted_jwt.PyJWKClient.fetch_data",
        return_value=jwks,
    ):
        with pytest.raises(TrustedJWTError, match="Invalid trusted JWT"):
            verify_trusted_jwt(token, app)


def test_verify_trusted_jwt_rejects_alg_none_token():
    app = _mock_app({})
    claims = {
        "sub": "user-123",
        "email": "person@example.com",
        "iss": "https://auth.example.com",
        "aud": "https://app.example.com",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(claims, key=None, algorithm="none")
    mock_key = MagicMock()
    mock_key.key = "public-key"

    with patch("gramps_webapi.auth.trusted_jwt._get_jwk_client") as mock_client:
        mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
        with pytest.raises(TrustedJWTError, match="Invalid trusted JWT"):
            verify_trusted_jwt(token, app)


def test_role_mapping_uses_highest_configured_role():
    app = _mock_app(
        {
            "TRUSTED_JWT_GROUP_OWNER": "owners",
            "TRUSTED_JWT_GROUP_EDITOR": "editors",
        }
    )
    role = get_role_from_trusted_jwt_claims({"groups": ["editors", "owners"]}, app)
    assert role == ROLE_OWNER


def test_role_mapping_returns_none_when_not_configured():
    app = _mock_app({})
    assert get_role_from_trusted_jwt_claims({"groups": ["editors"]}, app) is None


def test_role_mapping_returns_none_when_claim_missing():
    app = _mock_app({"TRUSTED_JWT_GROUP_OWNER": "owners"})
    assert get_role_from_trusted_jwt_claims({}, app) is None


def test_role_mapping_returns_disabled_when_groups_do_not_match():
    app = _mock_app({"TRUSTED_JWT_GROUP_OWNER": "owners"})
    assert (
        get_role_from_trusted_jwt_claims({"groups": ["non-owner"]}, app)
        == ROLE_DISABLED
    )


def test_get_userinfo_and_role_maps_configured_claims():
    app = _mock_app(
        {
            "TRUSTED_JWT_SUBJECT_CLAIM": "identity.sub",
            "TRUSTED_JWT_USERNAME_CLAIM": "preferred_username",
            "TRUSTED_JWT_GROUP_EDITOR": "editors",
            "TRUSTED_JWT_DEFAULT_ROLE": ROLE_OWNER,
        }
    )
    claims = {
        "identity": {"sub": "user-123"},
        "email": "person@example.com",
        "name": "Person Example",
        "preferred_username": "person",
        "groups": ["editors"],
        "iss": "https://auth.example.com",
        "aud": "https://app.example.com",
        "exp": 1893456000,
    }
    with patch(
        "gramps_webapi.auth.trusted_jwt.verify_trusted_jwt", return_value=claims
    ):
        userinfo, role, default_role = get_trusted_jwt_userinfo_and_role(
            "assertion", app
        )
    assert userinfo["sub"] == "user-123"
    assert userinfo["email"] == "person@example.com"
    assert userinfo["name"] == "Person Example"
    assert userinfo["preferred_username"] == "person"
    assert "trusted_jwt_claims" not in userinfo
    assert role == ROLE_EDITOR
    assert default_role == ROLE_OWNER


def test_complete_external_login_preserves_oidc_role_mapping_sentinel():
    """Standard OIDC callbacks must still compute custom-provider role mapping."""
    app = Flask(__name__)
    app.config["TREE"] = "bdd-family"

    with app.test_request_context("/api/oidc/callback/custom"):
        with patch(
            "gramps_webapi.api.resources.oidc.create_or_update_oidc_user",
            return_value="user-guid",
        ) as mock_create:
            with patch("gramps_webapi.api.resources.oidc.get_name", return_value="u"):
                with patch(
                    "gramps_webapi.api.resources.oidc.get_tree_id",
                    return_value="bdd-family",
                ):
                    with patch(
                        "gramps_webapi.api.resources.oidc.is_tree_disabled",
                        return_value=False,
                    ):
                        with patch(
                            "gramps_webapi.api.resources.oidc.get_user_details",
                            return_value={"role": ROLE_OWNER},
                        ):
                            with patch(
                                "gramps_webapi.api.resources.oidc.get_permissions",
                                return_value=set(),
                            ):
                                with patch(
                                    "gramps_webapi.api.resources.oidc.get_tokens",
                                    return_value={
                                        "access_token": "access",
                                        "refresh_token": "refresh",
                                    },
                                ):
                                    with patch(
                                        "gramps_webapi.api.resources.oidc.get_config",
                                        return_value="http://localhost:5000",
                                    ):
                                        response = _complete_external_login(
                                            {"sub": "user-123"},
                                            "bdd-family",
                                            "custom",
                                            provider_config={"username_claim": "email"},
                                        )

    assert response.status_code == 302
    assert mock_create.call_args.kwargs["role_from_claims"] is ROLE_FROM_CLAIMS_UNSET


def test_complete_external_login_reports_trusted_jwt_misconfig_as_server_error():
    app = Flask(__name__)
    app.config["TREE"] = "bdd-family"

    with app.test_request_context("/api/oidc/login/?provider=pomerium"):
        with patch(
            "gramps_webapi.api.resources.oidc.create_or_update_oidc_user",
            side_effect=ValueError("Provider 'pomerium' is not configured"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _complete_external_login(
                    {"sub": "user-123"},
                    "bdd-family",
                    "pomerium",
                    provider_config={"trusted_jwt": True},
                )

    assert exc_info.value.code == 500


def test_trusted_jwt_login_rejects_missing_assertion_header():
    """Test Trusted JWT login rejects requests without the assertion header."""
    app = Flask(__name__)
    with app.test_request_context("/api/oidc/login/?provider=trusted-jwt"):
        with patch(
            "gramps_webapi.api.resources.oidc.get_trusted_jwt_provider_config",
            return_value={"header": "X-Pomerium-Jwt-Assertion"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                _trusted_jwt_login({}, "trusted-jwt")

    assert exc_info.value.code == 401
    assert "assertion header is missing" in exc_info.value.description


def test_trusted_jwt_login_completes_existing_oidc_bridge():
    """Test Trusted JWT login completes through the existing OIDC bridge."""
    app = Flask(__name__)
    with app.test_request_context(
        "/api/oidc/login/?provider=trusted-jwt",
        headers={"X-Pomerium-Jwt-Assertion": "signed.assertion"},
    ):
        with patch(
            "gramps_webapi.api.resources.oidc.get_trusted_jwt_provider_config",
            return_value={"header": "X-Pomerium-Jwt-Assertion"},
        ):
            with patch(
                "gramps_webapi.api.resources.oidc.get_trusted_jwt_userinfo_and_role",
                return_value=(
                    {"sub": "user-123", "email": "person@example.com"},
                    ROLE_OWNER,
                    ROLE_DISABLED,
                ),
            ) as mock_userinfo_and_role:
                with patch(
                    "gramps_webapi.api.resources.oidc._complete_external_login",
                    return_value=("ok", 200),
                ) as mock_complete_login:
                    response = _trusted_jwt_login({}, "trusted-jwt")

    assert response == ("ok", 200)
    mock_userinfo_and_role.assert_called_once_with("signed.assertion")
    mock_complete_login.assert_called_once()
    assert mock_complete_login.call_args.args[2] == "trusted-jwt"
