"""Utility functions for celery."""

from celery import Task
from celery import current_app as current_celery_app
from celery.exceptions import Ignore
from werkzeug.exceptions import HTTPException


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
                    # Utility functions like check_quota_people and run_import
                    # use abort_with_message (a Flask/HTTP construct) for both
                    # request handlers and Celery tasks. Preserve the standard
                    # API error shape here so task consumers do not need
                    # special-case parsing for background-task failures.
                    # Ideally these utilities would raise a dedicated
                    # TaskError instead of an HTTPException.
                    self.update_state(
                        state="FAILURE",
                        meta={"error": {"code": exc.code, "message": exc.description}},
                    )
                    raise Ignore()

    celery.Task = ContextTask
    return celery
