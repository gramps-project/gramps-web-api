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


def test_unprefixed_env_var_is_not_flagged_if_overridden():
    """A leftover unprefixed variable has no effect if the prefixed one is set."""
    environ = {"TREE": "Old Tree", "GRAMPSWEB_TREE": "My Tree"}
    assert check_deprecations(DEFAULTS, environ=environ) == []


def test_customized_search_index_dir_is_flagged():
    config = {**DEFAULTS, "SEARCH_INDEX_DIR": "/data/index"}
    assert [d["option"] for d in check_deprecations(config, environ={})] == [
        "SEARCH_INDEX_DIR"
    ]


def test_email_use_tls_only_flagged_if_email_configured():
    assert check_deprecations(DEFAULTS, environ={}) == []
    config = {**DEFAULTS, "DEFAULT_FROM_EMAIL": "gramps@example.com"}
    assert [d["option"] for d in check_deprecations(config, environ={})] == [
        "EMAIL_USE_TLS"
    ]


def test_email_use_tls_replacement_depends_on_its_value():
    """`EMAIL_USE_TLS` means implicit TLS, its absence STARTTLS - see #942."""
    config = {**DEFAULTS, "DEFAULT_FROM_EMAIL": "gramps@example.com"}
    assert DefaultConfig.EMAIL_USE_TLS is True
    assert check_deprecations(config, environ={})[0]["replacement"] == "EMAIL_USE_SSL"
    config["EMAIL_USE_TLS"] = False
    assert (
        check_deprecations(config, environ={})[0]["replacement"] == "EMAIL_USE_STARTTLS"
    )


def test_email_use_tls_not_flagged_if_ssl_configured():
    """Setting one of the replacement options is enough to not be flagged."""
    config = {
        **DEFAULTS,
        "DEFAULT_FROM_EMAIL": "gramps@example.com",
        "EMAIL_USE_SSL": True,
    }
    assert check_deprecations(config, environ={}) == []


def test_email_use_tls_flagged_if_sender_stored_in_db():
    """The sender address can be stored in the database rather than the config."""
    stored = {"DEFAULT_FROM_EMAIL": "gramps@example.com"}
    deprecations = check_deprecations(DEFAULTS, environ={}, get_option=stored.get)
    assert [d["option"] for d in deprecations] == ["EMAIL_USE_TLS"]
