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

"""Gunicorn config serving the optional Prometheus metrics of all workers.

Use it with `gunicorn -c python:gramps_webapi.gunicorn_config`.

Importing this module sets environment variables, so the app must not import it.
"""

import os
import shutil
import sys
import tempfile

# prometheus_client chooses its multiprocess mode on import, so this must be set
# before the app is loaded; it is unused if metrics are disabled
_created_multiproc_dir = None
if not os.getenv("PROMETHEUS_MULTIPROC_DIR"):
    _created_multiproc_dir = tempfile.mkdtemp(prefix="gramps_webapi_metrics_")
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = _created_multiproc_dir


def when_ready(server):
    """Serve the metrics from the master, which outlives the workers."""
    from gramps_webapi.metrics import start_metrics_server

    # without --preload, this loads the app in the master and the workers
    # inherit it, as with --preload
    start_metrics_server(server.app.wsgi())


def child_exit(server, worker):
    """Drop the live gauges of an exited worker."""
    # only imported if metrics are enabled, and may not be installed
    if "prometheus_client" not in sys.modules:
        return

    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(worker.pid)


def on_exit(server):
    """Remove the metrics directory this module created."""
    if _created_multiproc_dir:
        shutil.rmtree(_created_multiproc_dir, ignore_errors=True)
