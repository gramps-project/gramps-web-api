#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for optional Sentry error reporting."""

import logging
import sys
import types
from unittest.mock import patch

import pytest

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

DSN = "https://abc123@o0.ingest.sentry.io/1"


@pytest.fixture
def fake_sdk(monkeypatch):
    """Install a stub sentry_sdk recording the kwargs passed to init()."""
    module = types.ModuleType("sentry_sdk")
    module.calls = []
    module.init = lambda **kwargs: module.calls.append(kwargs)
    monkeypatch.setitem(sys.modules, "sentry_sdk", module)
    return module


@pytest.fixture
def missing_sdk(monkeypatch):
    """Make `import sentry_sdk` fail even where the package is installed."""
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)


def create_test_app(**config):
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        return create_app(config={"TESTING": True, **config}, config_from_env=False)


class TestSentry:
    def test_not_initialized_by_default(self, fake_sdk):
        """No DSN configured means no reporting at all."""
        create_test_app()
        assert fake_sdk.calls == []

    def test_initialized_with_release_when_dsn_configured(self, fake_sdk):
        app = create_test_app(SENTRY_DSN=DSN)
        assert len(fake_sdk.calls) == 1
        assert fake_sdk.calls[0]["dsn"] == DSN
        assert fake_sdk.calls[0]["release"] == app.config["API_VERSION"]

    def test_no_tracing_or_pii_unless_asked_for(self, fake_sdk):
        """Family tree data is sensitive, so PII capture must be opt-in."""
        create_test_app(SENTRY_DSN=DSN)
        assert fake_sdk.calls[0]["traces_sample_rate"] == 0.0
        assert fake_sdk.calls[0]["send_default_pii"] is False

    def test_unset_environment_becomes_none(self, fake_sdk):
        """The SDK treats "" as a real environment name, unlike the config default."""
        create_test_app(SENTRY_DSN=DSN)
        assert fake_sdk.calls[0]["environment"] is None

    def test_missing_package_warns_and_disables(self, missing_sdk, caplog):
        with caplog.at_level(logging.WARNING, logger="gramps_webapi.sentry"):
            create_test_app(SENTRY_DSN=DSN)
        assert "sentry-sdk" in caplog.text

    def test_app_starts_without_the_package(self, missing_sdk):
        app = create_test_app(SENTRY_DSN=DSN)
        assert app.test_client().get("/ready").status_code == 200
