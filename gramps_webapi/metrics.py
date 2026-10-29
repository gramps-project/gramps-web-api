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

"""Optional Prometheus metrics."""

import logging
import os
import sys

_LOG = logging.getLogger(__name__)

EXTENSION_KEY = "prometheus_metrics"


def path(request) -> str:
    """Return the URL rule of the request, to keep the label cardinality low.

    The function name becomes the label name.
    """
    if request.url_rule is None:
        return "<unmatched>"
    return request.url_rule.rule


def init_metrics(app) -> bool:
    """Record HTTP metrics if enabled. Returns True if enabled.

    This only records them. They are served on their own port by
    `start_metrics_server`, which the server entry points call, since
    `create_app` must not start threads.
    """
    if not app.config["METRICS_ENABLED"]:
        return False

    try:
        from prometheus_client import CollectorRegistry
        from prometheus_flask_exporter import PrometheusMetrics
        from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics
    except ImportError:
        _LOG.warning(
            "METRICS_ENABLED is set but the prometheus-flask-exporter package is "
            "not installed. Install gramps-webapi[metrics] to enable metrics."
        )
        return False

    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        # several worker processes, aggregated through files in that directory
        metrics = GunicornPrometheusMetrics(app, group_by=path)
    else:
        if "gunicorn" in sys.modules:
            # its hooks would have set the directory and started the server
            _LOG.warning(
                "METRICS_ENABLED is set but gunicorn was started without the "
                "metrics config, so the metrics are not served. Add "
                "`-c python:gramps_webapi.gunicorn_config` to the gunicorn command."
            )
        # own registry, so that several apps in one process don't clash
        metrics = PrometheusMetrics(
            app, path=None, group_by=path, registry=CollectorRegistry()
        )
    app.extensions[EXTENSION_KEY] = metrics
    return True


def start_metrics_server(app) -> None:
    """Serve the metrics on METRICS_PORT in a background thread, if enabled."""
    metrics = app.extensions.get(EXTENSION_KEY)
    if metrics is None:
        return

    from prometheus_client import start_http_server

    start_http_server(app.config["METRICS_PORT"], registry=metrics.registry)
    app.logger.info("Serving metrics on port %s.", app.config["METRICS_PORT"])
