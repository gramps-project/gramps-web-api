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

"""Tests for reporting aborts that happen inside a background task."""

import unittest

import pytest
from celery import Celery
from celery.backends.base import Backend
from flask import Flask, Response
from werkzeug.exceptions import HTTPException

from gramps_webapi.api.resources.tasks import _task_error_payload, _task_meta
from gramps_webapi.util.celery import TaskError, TaskRejection, create_celery

PAYLOAD = {"error": {"code": 405, "message": "Not allowed by people quota"}}


def _backend(serializer="json"):
    """Return a result backend not connected to any broker."""
    return Backend(app=Celery(), serializer=serializer)


class TestTaskErrorSerialization(unittest.TestCase):
    """The error payload must survive a round trip through the result backend."""

    def test_round_trip(self):
        backend = _backend()
        stored = backend.decode(
            backend.encode(backend.prepare_exception(TaskError(PAYLOAD)))
        )
        exc = backend.exception_to_python(stored)
        assert isinstance(exc, TaskError)
        assert exc.args[0] == PAYLOAD

    def test_round_trip_meta(self):
        """The full meta dict as stored for a failed task decodes fine."""
        backend = _backend()
        meta = {
            "status": "FAILURE",
            "result": backend.prepare_exception(TaskError(PAYLOAD)),
        }
        decoded = backend.meta_from_decoded(backend.decode(backend.encode(meta)))
        assert decoded["status"] == "FAILURE"
        assert _task_error_payload(decoded["result"]) == PAYLOAD

    def test_plain_dict_result_is_unreadable(self):
        """Storing the payload directly under FAILURE poisons the result.

        This is what update_state(state="FAILURE", meta=payload) used to do and
        the reason TaskError exists; Celery refuses to decode it.
        """
        backend = _backend()
        with pytest.raises(ValueError):
            backend.meta_from_decoded({"status": "FAILURE", "result": PAYLOAD})


class TestTaskErrorPayload(unittest.TestCase):
    """Extraction of the API error shape from a task result."""

    def test_task_error(self):
        assert _task_error_payload(TaskError(PAYLOAD)) == PAYLOAD

    def test_synthesized_exception_class(self):
        """Celery rebuilds unknown exception types dynamically."""
        cls = type("TaskError", (Exception,), {})
        assert _task_error_payload(cls(PAYLOAD)) == PAYLOAD

    def test_other_exception(self):
        assert _task_error_payload(ValueError("Failed importing gramps file")) is None

    def test_non_exception_result(self):
        assert _task_error_payload({"people": 3}) is None


def _abort(status, message):
    """Raise the same exception as api.util.abort_with_message."""
    exc = HTTPException(response=Response(status=status), description=message)
    exc.code = status
    raise exc


def _celery_app():
    """Return a celery app wired to a Flask app, as gramps_webapi.celery does."""
    app = Flask(__name__)
    app.config["CELERY_CONFIG"] = {}
    return create_celery(app)


_celery = _celery_app()


@_celery.task()
def _rejected_task():
    _abort(405, "Not allowed by people quota")


@_celery.task()
def _failed_task():
    _abort(500, "Import failed")


class TestAbortClassification(unittest.TestCase):
    """Aborts inside a task are split by who is at fault.

    Only a fault deserves to reach error reporting, so the distinction has to
    survive as far as the exception type.
    """

    def test_client_error_is_a_rejection(self):
        with pytest.raises(TaskRejection) as info:
            _rejected_task.apply(throw=True)
        assert info.value.args[0] == PAYLOAD

    def test_server_error_stays_a_task_error(self):
        with pytest.raises(TaskError) as info:
            _failed_task.apply(throw=True)
        assert not isinstance(info.value, TaskRejection)


class _PoisonedAsyncResult:
    """Result stored in the pre-TaskError shape, which Celery cannot decode."""

    @property
    def state(self):
        raise ValueError("Exception information must include the exception type")

    result = state


class TestLegacyResultFallback(unittest.TestCase):
    """Results stored in the pre-TaskError shape must not raise."""

    def test_does_not_raise(self):
        meta = _task_meta(_PoisonedAsyncResult())
        assert meta.state == "FAILURE"
        assert isinstance(meta.result, str)
