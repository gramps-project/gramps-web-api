"""Utility functions for celery."""

from celery import Task
from celery import current_app as current_celery_app


def create_celery(app):
    """App factory for celery."""
    celery = current_celery_app
    celery.conf.name = app.import_name
    celery.conf.update(app.config["CELERY_CONFIG"])

    class ContextTask(Task):
        """Celery task which is aware of the flask app context."""

        def __call__(self, *args, **kwargs):
            if self.request.called_directly:
                return self.run(*args, **kwargs)
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
