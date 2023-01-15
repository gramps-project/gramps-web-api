"""Celery task scheduler."""

from .app import create_app
from .util.celery import make_celery


celery = make_celery(app=create_app())
