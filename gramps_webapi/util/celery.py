"""Utility functions for celery."""

import logging

from celery import Task
from celery import current_app as current_celery_app
from werkzeug.exceptions import HTTPException

from .task_state import run_tracked


class TaskError(Exception):
    """Task failure carrying an API-style error payload as its only argument.

    Celery serialises exception args, so the payload survives the round trip
    through the result backend.
    """


class TaskRejection(TaskError):
    """Failure caused by the request itself rather than by a fault (4xx).

    An expected outcome: the payload is the client's answer, not a defect.
    """


class HideTaskResultFilter(logging.Filter):
    """Hide task return values in Celery's "Task ... succeeded" log records.

    Results can contain private tree data, e.g. OCR text or AI chat answers.
    Celery has no setting for this, but passes the log context as ``data`` in
    ``extra`` for custom handlers, so the value is replaced there too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        context = record.args
        if isinstance(context, dict) and "return_value" in context:
            context = {**context, "return_value": "<hidden>"}
            record.args = context
            if isinstance(getattr(record, "data", None), dict):
                record.data = context
        return True


_hide_task_result_filter = HideTaskResultFilter()


def create_celery(app):
    """App factory for celery."""
    # no-op if already added, create_celery runs once per app
    logging.getLogger("celery.app.trace").addFilter(_hide_task_result_filter)
    celery = current_celery_app
    celery.conf.name = app.import_name
    celery.conf.update(app.config["CELERY_CONFIG"])
    # Always track started state so task status is accurate regardless of user config.
    celery.conf.task_track_started = True

    class ContextTask(Task):
        """Celery task which is aware of the flask app context."""

        def __call__(self, *args, **kwargs):
            if self.request.called_directly:
                return self.run(*args, **kwargs)
            with app.app_context():
                try:
                    return run_tracked(
                        self.request.id,
                        lambda: self.run(*args, **kwargs),
                        fence=True,
                    )
                except HTTPException as exc:
                    # Utilities like check_quota_people abort with an
                    # HTTPException inside tasks too; preserve the API error
                    # shape. It must be raised, not stored via update_state:
                    # Celery can only decode serialised exceptions in exception
                    # states, and chokes on a plain dict when reading it back.
                    payload = {"error": {"code": exc.code, "message": exc.description}}
                    if (exc.code or 500) < 500:
                        raise TaskRejection(payload) from exc
                    raise TaskError(payload) from exc

    celery.Task = ContextTask
    return celery
