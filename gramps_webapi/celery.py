"""Celery task scheduler."""

from .app import create_app
from .util.celery import create_celery


celery = create_celery(app=create_app())
