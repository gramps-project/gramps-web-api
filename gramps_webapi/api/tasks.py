#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021-2023      David Straub
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

"""Execute tasks."""

import os
from http import HTTPStatus
from gettext import gettext as _
from typing import Callable, Optional

from celery import shared_task
from celery.result import AsyncResult
from flask import abort, current_app

from .emails import email_confirm_email, email_new_user, email_reset_pw
from .util import get_config, send_email
from .resources.util import run_import


def run_task(task: Callable, **kwargs) -> Optional[AsyncResult]:
    """Send a task to the task queue or run immediately if no queue set up."""
    if not current_app.config["CELERY_CONFIG"]:
        with current_app.app_context():
            return task(**kwargs)
    return task.delay(**kwargs)


def make_task_response(task: AsyncResult):
    """Make a 202 response with the location of the task status endpoint."""
    url = f"/api/tasks/{task.id}"
    payload = {"task": {"href": url, "id": task.id}}
    return payload, HTTPStatus.ACCEPTED


@shared_task()
def send_email_reset_password(email: str, token: str):
    """Send an email for password reset."""
    base_url = get_config("BASE_URL").rstrip("/")
    body = email_reset_pw(base_url=base_url, token=token)
    subject = _("Reset your Gramps password")
    send_email(subject=subject, body=body, to=[email])


@shared_task()
def send_email_confirm_email(email: str, token: str):
    """Send an email to confirm an e-mail address."""
    base_url = get_config("BASE_URL").rstrip("/")
    body = email_confirm_email(base_url=base_url, token=token)
    subject = _("Confirm your e-mail address")
    send_email(subject=subject, body=body, to=[email])


@shared_task()
def send_email_new_user(username: str, fullname: str, email: str):
    """Send an email to owners to notify of a new registered user."""
    base_url = get_config("BASE_URL").rstrip("/")
    body = email_new_user(
        base_url=base_url, username=username, fullname=fullname, email=email
    )
    subject = _("New registered user")
    auth = current_app.config.get("AUTH_PROVIDER")
    if auth is None:
        abort(405)
    emails = auth.get_owner_emails()
    if emails:
        send_email(subject=subject, body=body, to=emails)


def _search_reindex_full() -> None:
    """Rebuild the search index."""
    indexer = current_app.config["SEARCH_INDEXER"]
    db = current_app.config["DB_MANAGER"].get_db().db
    try:
        indexer.reindex_full(db)
    finally:
        db.close()


@shared_task()
def search_reindex_full() -> None:
    """Rebuild the search index."""
    return _search_reindex_full()


@shared_task()
def search_reindex_incremental() -> None:
    """Run an incremental reindex of the search index."""
    indexer = current_app.config["SEARCH_INDEXER"]
    db = current_app.config["DB_MANAGER"].get_db().db
    try:
        indexer.search_reindex_incremental(db)
    finally:
        db.close()


@shared_task()
def import_file(file_name: str, extension: str, delete: bool = True):
    """Import a file."""
    db_handle = current_app.config["DB_MANAGER"].get_db().db
    run_import(
        db_handle=db_handle,
        file_name=file_name,
        extension=extension.lower(),
        delete=delete,
    )
    _search_reindex_full()
