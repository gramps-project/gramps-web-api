"""Utility functions for celery."""

from celery import Task
from celery import current_app as current_celery_app
from werkzeug.exceptions import HTTPException


class TaskError(Exception):
    """Task failure carrying an API-style error payload as its only argument.

    Celery serialises exception args, so the payload survives the round trip
    through the result backend.
    """


def create_celery(app):
    """App factory for celery."""
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
                    return self.run(*args, **kwargs)
                except HTTPException as exc:
                    # Utilities like check_quota_people abort with an
                    # HTTPException inside tasks too; preserve the API error
                    # shape. It must be raised, not stored via update_state:
                    # Celery can only decode serialised exceptions in exception
                    # states, and chokes on a plain dict when reading it back.
                    raise TaskError(
                        {"error": {"code": exc.code, "message": exc.description}}
                    ) from exc

    celery.Task = ContextTask
    return celery
