"""Tests for the detection of deprecated configuration options."""

from gramps_webapi.api.deprecations import check_deprecations
from gramps_webapi.config import DefaultConfig

DEFAULTS = {
    key: getattr(DefaultConfig, key) for key in dir(DefaultConfig) if key.isupper()
}


def test_default_config_is_not_deprecated():
    """A deployment that sets nothing must not be flagged."""
    assert check_deprecations(DEFAULTS, environ={}) == []


def test_unprefixed_env_var_is_flagged():
    deprecations = check_deprecations(DEFAULTS, environ={"TREE": "My Tree"})
    assert [d["option"] for d in deprecations] == ["TREE"]
    assert deprecations[0]["replacement"] == "GRAMPSWEB_TREE"


def test_prefixed_env_var_is_not_flagged():
    assert check_deprecations(DEFAULTS, environ={"GRAMPSWEB_TREE": "My Tree"}) == []


def test_customized_search_index_dir_is_flagged():
    config = {**DEFAULTS, "SEARCH_INDEX_DIR": "/data/index"}
    assert [d["option"] for d in check_deprecations(config, environ={})] == [
        "SEARCH_INDEX_DIR"
    ]


def test_email_use_tls_only_flagged_if_email_configured():
    assert check_deprecations({**DEFAULTS, "EMAIL_USE_TLS": False}, environ={}) == []
    config = {**DEFAULTS, "DEFAULT_FROM_EMAIL": "gramps@example.com"}
    assert [d["option"] for d in check_deprecations(config, environ={})] == [
        "EMAIL_USE_TLS"
    ]
