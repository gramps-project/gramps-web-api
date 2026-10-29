#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Tests for optional Prometheus metrics."""

import logging
import sys
import urllib.request
from unittest.mock import patch

import pytest

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.metrics import EXTENSION_KEY, start_metrics_server

prometheus_client = pytest.importorskip("prometheus_client")
pytest.importorskip("prometheus_flask_exporter")


@pytest.fixture
def missing_exporter(monkeypatch):
    """Make `import prometheus_flask_exporter` fail even where it is installed."""
    monkeypatch.setitem(sys.modules, "prometheus_flask_exporter", None)


def create_test_app(**config):
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        return create_app(config={"TESTING": True, **config}, config_from_env=False)


def scrape(app) -> str:
    registry = app.extensions[EXTENSION_KEY].registry
    return prometheus_client.generate_latest(registry).decode()


class TestMetrics:
    def test_not_enabled_by_default(self):
        app = create_test_app()
        assert EXTENSION_KEY not in app.extensions

    def test_requests_are_counted(self):
        app = create_test_app(METRICS_ENABLED=True)
        app.test_client().get("/ready")
        assert 'flask_http_request_total{method="GET",status="200"} 1.0' in scrape(app)

    def test_duration_is_grouped_by_url_rule(self):
        """The raw URL would give every person and SPA route its own series."""
        app = create_test_app(METRICS_ENABLED=True)
        app.test_client().get("/some/spa/route")
        metrics = scrape(app)
        assert 'path="/<path:path>"' in metrics
        assert "/some/spa/route" not in metrics

    def test_not_served_on_the_api_port(self):
        app = create_test_app(METRICS_ENABLED=True)
        client = app.test_client()
        client.get("/ready")
        for url in ["/metrics", "/api/metrics"]:
            assert b"flask_http_request_total" not in client.get(url).data

    def test_server_serves_on_metrics_port(self):
        app = create_test_app(METRICS_ENABLED=True, METRICS_PORT=0)
        app.test_client().get("/ready")
        servers = []
        start_http_server = prometheus_client.start_http_server

        def start(*args, **kwargs):
            servers.append(start_http_server(*args, **kwargs))
            return servers[-1]

        with patch("prometheus_client.start_http_server", start):
            start_metrics_server(app)
        httpd, _ = servers[0]
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/metrics"
            with urllib.request.urlopen(url) as response:
                assert b'path="/ready"' in response.read()
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_server_not_started_when_disabled(self):
        app = create_test_app()
        with patch("prometheus_client.start_http_server") as start:
            start_metrics_server(app)
        start.assert_not_called()

    def test_missing_package_warns_and_disables(self, missing_exporter, caplog):
        with caplog.at_level(logging.WARNING, logger="gramps_webapi.metrics"):
            app = create_test_app(METRICS_ENABLED=True)
        assert "prometheus-flask-exporter" in caplog.text
        assert EXTENSION_KEY not in app.extensions

    def test_app_starts_without_the_package(self, missing_exporter):
        app = create_test_app(METRICS_ENABLED=True)
        assert app.test_client().get("/ready").status_code == 200
