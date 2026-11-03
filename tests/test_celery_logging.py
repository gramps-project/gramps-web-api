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

"""Tests that Celery does not log task return values."""

import logging

from celery import shared_task
from celery.app.trace import build_tracer

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


@shared_task()
def _ocr_task():
    return "secret OCR text"


def test_task_result_not_logged(monkeypatch, caplog):
    monkeypatch.setenv(ENV_CONFIG_FILE, TEST_AUTH_CONFIG)
    create_app(config={"TESTING": True})
    create_app(config={"TESTING": True})
    trace_logger = logging.getLogger("celery.app.trace")
    assert len(trace_logger.filters) == 1
    with caplog.at_level(logging.INFO, logger="celery.app.trace"):
        # the tracer checks the log level when it is built
        tracer = build_tracer(
            _ocr_task.name, _ocr_task, app=_ocr_task._get_app(), eager=True
        )
        retval = tracer("some-id", (), {}, {})
    assert retval.retval == "secret OCR text"
    records = [r for r in caplog.records if "succeeded" in r.getMessage()]
    assert len(records) == 1
    assert records[0].getMessage().endswith(": <hidden>")
    assert records[0].data["return_value"] == "<hidden>"
    assert "secret OCR text" not in caplog.text
