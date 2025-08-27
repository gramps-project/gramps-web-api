# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021-2024      David Straub
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

from __future__ import annotations

import json
import os
import uuid
from gettext import gettext as _
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, Union

from celery import Task, shared_task
from celery.result import AsyncResult
from flask import current_app
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.json_utils import object_to_dict
from gramps.gen.merge.diff import diff_items

from gramps_webapi.api.search.indexer import SearchIndexer, SemanticSearchIndexer

from ..auth import get_owner_emails
from ..undodb import migrate as migrate_undodb
from .check import check_database
from .emails import email_confirm_email, email_new_user, email_reset_pw
from .export import prepare_options, run_export
from .media import get_media_handler
from .media_importer import MediaImporter
from .report import run_report
from .resources.delete import delete_all_objects
from .resources.util import (
    abort_with_message,
    app_has_semantic_search,
    dry_run_import,
    run_import,
    transaction_to_json,
)
from .search import get_search_indexer, get_semantic_search_indexer
from .telemetry import (
    get_telemetry_payload,
    send_telemetry,
    telemetry_sent_last_24h,
    update_telemetry_timestamp,
)
from .util import (
    check_quota_people,
    close_db,
    get_config,
    get_db_outside_request,
    gramps_object_from_dict,
    send_email,
    update_usage_people,
    upgrade_gramps_database,
)


def run_task(task: Task, **kwargs) -> Union[AsyncResult, Any]:
    """Send a task to the task queue or run immediately if no queue set up."""
    if not current_app.config["CELERY_CONFIG"]:
        with current_app.app_context():
            try:
                return task(**kwargs)
            except Exception as exc:
                abort_with_message(500, str(exc))
    return task.delay(**kwargs)


def make_task_response(task: AsyncResult):
    """Make a 202 response with the location of the task status endpoint."""
    url = f"/api/tasks/{task.id}"
    payload = {"task": {"href": url, "id": task.id}}
    return payload, HTTPStatus.ACCEPTED


def clip_progress(x: float) -> float:
    """Clip the progress to [0, 1), else return -1."""
    if x < 0 or x >= 1:
        return -1
    return x


@shared_task()
def send_email_reset_password(email: str, user_name: str, token: str):
    """Send an email for password reset."""
    base_url = get_config("BASE_URL").rstrip("/")
    body, body_html = email_reset_pw(
        base_url=base_url, user_name=user_name, token=token
    )
    subject = _("Reset your Gramps password")
    send_email(subject=subject, body=body, to=[email], body_html=body_html)


@shared_task()
def send_email_confirm_email(email: str, user_name: str, token: str):
    """Send an email to confirm an e-mail address."""
    base_url = get_config("BASE_URL").rstrip("/")
    body, body_html = email_confirm_email(
        base_url=base_url, user_name=user_name, token=token
    )
    subject = _("Confirm your e-mail address")
    send_email(subject=subject, body=body, to=[email], body_html=body_html)


@shared_task()
def send_email_new_user(
    username: str, fullname: str, email: str, tree: str, include_admins: bool
):
    """Send an email to owners to notify of a new registered user."""
    base_url = get_config("BASE_URL").rstrip("/")
    body = email_new_user(
        base_url=base_url, username=username, fullname=fullname, email=email
    )
    subject = _("New registered user")
    emails = get_owner_emails(tree=tree, include_admins=include_admins)
    if emails:
        send_email(subject=subject, body=body, to=emails)


def _search_reindex_full(
    tree: str, user_id: str, semantic: bool, progress_cb: Optional[Callable] = None
) -> None:
    """Rebuild the search index."""
    if semantic:
        indexer: SearchIndexer | SemanticSearchIndexer = get_semantic_search_indexer(
            tree
        )
    else:
        indexer = get_search_indexer(tree)
    db = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        indexer.reindex_full(db, progress_cb=progress_cb)
    finally:
        close_db(db)


def progress_callback_count(self, title: str = "", message: str = "") -> Callable:
    def callback(current: int, total: int, prev: int | None = None) -> None:
        if total == 0:
            return
        self.update_state(
            state="PROGRESS",
            meta={
                "current": current,
                "total": total,
                "progress": clip_progress(current / total),
                "title": title,
                "message": message,
            },
        )

    return callback


def set_progress_title(self, title: str = "", message: str = "") -> None:
    """Set a title/message indicating progress."""
    if self.request.id is not None:
        self.update_state(
            state="PROGRESS",
            meta={
                "title": title,
                "message": message,
            },
        )


@shared_task(bind=True)
def search_reindex_full(self, tree: str, user_id: str, semantic: bool) -> None:
    """Rebuild the search index."""
    return _search_reindex_full(
        tree=tree,
        user_id=user_id,
        semantic=semantic,
        progress_cb=progress_callback_count(self, title="Updating search index..."),
    )


def _search_reindex_incremental(
    tree: str, user_id: str, semantic: bool, progress_cb: Optional[Callable] = None
) -> None:
    """Run an incremental reindex of the search index."""
    if semantic:
        indexer: SearchIndexer | SemanticSearchIndexer = get_semantic_search_indexer(
            tree
        )
    else:
        indexer = get_search_indexer(tree)
    db = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        indexer.reindex_incremental(db, progress_cb=progress_cb)
    finally:
        close_db(db)


@shared_task(bind=True)
def search_reindex_incremental(self, tree: str, user_id: str, semantic: bool) -> None:
    """Run an incremental reindex of the search index."""
    return _search_reindex_incremental(
        tree=tree,
        user_id=user_id,
        semantic=semantic,
        progress_cb=progress_callback_count(self, title="Updating search index..."),
    )


@shared_task(bind=True)
def import_file(
    self, tree: str, user_id: str, file_name: str, extension: str, delete: bool = True
):
    """Import a file."""
    object_counts = dry_run_import(file_name=file_name)
    if object_counts is None:
        raise ValueError(f"Failed importing {extension} file")
    check_quota_people(to_add=object_counts["people"], tree=tree, user_id=user_id)
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        run_import(
            db_handle=db_handle,
            file_name=file_name,
            extension=extension.lower(),
            delete=delete,
            task=self,
        )
    finally:
        close_db(db_handle)
    update_usage_people(tree=tree, user_id=user_id)
    _search_reindex_incremental(
        tree=tree,
        user_id=user_id,
        semantic=False,
        progress_cb=progress_callback_count(
            self, title="Updating full-text search index..."
        ),
    )
    if current_app.config.get("VECTOR_EMBEDDING_MODEL"):
        _search_reindex_incremental(
            tree=tree,
            user_id=user_id,
            semantic=True,
            progress_cb=progress_callback_count(
                self, title="Updating semantic search index..."
            ),
        )


@shared_task(bind=True)
def export_db(
    self, tree: str, user_id: str, extension: str, options: Dict, view_private: bool
) -> Dict[str, str]:
    """Export a database."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=view_private, readonly=True, user_id=user_id
    )
    try:
        prepared_options = prepare_options(db_handle, options)
        file_name, file_type = run_export(
            db_handle, extension, prepared_options, task=self
        )
    finally:
        close_db(db_handle)

    extension = file_type.lstrip(".")
    return {
        "file_name": file_name,
        "file_type": file_type,
        "url": f"/api/exporters/{extension}/file/processed/{file_name}",
    }


@shared_task()
def generate_report(
    tree: str,
    user_id: str,
    report_id: str,
    options: Dict,
    view_private: bool,
    locale: Optional[str] = None,
) -> Dict[str, str]:
    """Generate a Gramps report."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=view_private, readonly=True, user_id=user_id
    )
    try:
        file_name, file_type = run_report(
            db_handle=db_handle,
            report_id=report_id,
            report_options=options,
            language=locale,
        )
    finally:
        close_db(db_handle)

    return {
        "file_name": file_name,
        "file_type": file_type,
        "url": f"/api/reports/{report_id}/file/processed/{file_name}",
    }


@shared_task(bind=True)
def export_media(
    self, tree: str, user_id: str, view_private: bool
) -> Dict[str, Union[str, int]]:
    """Export media files."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=view_private, readonly=True, user_id=user_id
    )
    try:
        media_handler = get_media_handler(db_handle, tree=tree)
        export_path = current_app.config["EXPORT_DIR"]
        os.makedirs(export_path, exist_ok=True)
        file_name = f"{uuid.uuid4()}.zip"
        zip_filename = os.path.join(export_path, file_name)
        media_handler.create_file_archive(
            db_handle=db_handle,
            zip_filename=zip_filename,
            include_private=view_private,
            progress_cb=progress_callback_count(self),
        )
    finally:
        close_db(db_handle)

    file_size = os.path.getsize(zip_filename)
    return {
        "file_name": file_name,
        "url": f"/api/media/archive/{file_name}",
        "file_size": file_size,
    }


@shared_task(bind=True)
def import_media_archive(
    self, tree: str, user_id: str, file_name: str, delete: bool = True
):
    """Import a media archive."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        importer = MediaImporter(
            tree=tree,
            user_id=user_id,
            db_handle=db_handle,
            file_name=file_name,
            delete=delete,
        )
        result = importer(progress_cb=progress_callback_count(self))
    finally:
        close_db(db_handle)
    return result


@shared_task()
def media_ocr(
    tree: str,
    user_id: str,
    handle: str,
    view_private: bool,
    lang: str,
    output_format: str = "string",
):
    """Perform text recognition (OCR) on a media object."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=view_private, readonly=True, user_id=user_id
    )
    try:
        handler = get_media_handler(db_handle, tree).get_file_handler(
            handle, db_handle=db_handle
        )
        return handler.get_ocr(lang=lang, output_format=output_format)
    finally:
        close_db(db_handle)


@shared_task(bind=True)
def check_repair_database(self, tree: str, user_id: str):
    """Check and repair a Gramps database (tree)"""
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        return check_database(db_handle, progress_cb=progress_callback_count(self))
    finally:
        close_db(db_handle)


@shared_task(bind=True)
def upgrade_database_schema(self, tree: str, user_id: str):
    """Upgrade the schema of the Gramps database and the associated undo database."""
    set_progress_title(self, title="Upgrading Gramps database schema...")
    upgrade_gramps_database(tree=tree, user_id=user_id, task=self)
    set_progress_title(self, title="Upgrading undo database schema...")
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        migrate_undodb(db_handle.undodb)
    finally:
        close_db(db_handle)


@shared_task(bind=True)
def upgrade_undodb_schema(self, tree: str, user_id: str):
    """Upgrade the schema of the undo database."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        migrate_undodb(db_handle.undodb)
    finally:
        close_db(db_handle)


@shared_task(bind=True)
def delete_objects(
    self, tree: str, user_id: str, namespaces: Optional[List[str]] = None
):
    """Delete all objects of a given type."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        delete_all_objects(
            db_handle=db_handle,
            namespaces=namespaces,
            progress_cb=progress_callback_count(self),
        )
    finally:
        close_db(db_handle)

    update_usage_people(tree=tree, user_id=user_id)
    _search_reindex_incremental(
        tree=tree,
        user_id=user_id,
        semantic=False,
        progress_cb=progress_callback_count(
            self, title="Updating full-text search index..."
        ),
    )
    if current_app.config.get("VECTOR_EMBEDDING_MODEL"):
        _search_reindex_incremental(
            tree=tree,
            user_id=user_id,
            semantic=True,
            progress_cb=progress_callback_count(
                self, title="Updating semantic search index..."
            ),
        )


@shared_task(bind=True)
def process_transactions(
    self, tree: str, user_id: str, payload: list[dict], force: bool
):
    """Process a set of database transactions, updating search indices as needed."""
    num_people_deleted = sum(
        item["type"] == "delete" and item["_class"] == "Person" for item in payload
    )
    num_people_added = sum(
        item["type"] == "add" and item["_class"] == "Person" for item in payload
    )
    num_people_new = num_people_added - num_people_deleted
    check_quota_people(to_add=num_people_new, tree=tree, user_id=user_id)
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    try:
        with DbTxn("Raw transaction", db_handle) as trans:
            for item in payload:
                try:
                    class_name = item["_class"]
                    trans_type = item["type"]
                    handle = item["handle"]
                    old_data = item["old"]
                    if not force and not old_unchanged(
                        db_handle, class_name, handle, old_data
                    ):
                        if num_people_added or num_people_deleted:
                            update_usage_people(tree=tree, user_id=user_id)
                        raise ValueError("Object has changed")
                    new_data = item["new"]
                    if new_data:
                        new_obj = gramps_object_from_dict(new_data)
                    if trans_type == "delete":
                        handle_delete(trans, class_name, handle)
                        if (
                            class_name == "Person"
                            and handle == db_handle.get_default_handle()
                        ):
                            db_handle.set_default_person_handle(None)
                    elif trans_type == "add":
                        handle_add(trans, class_name, new_obj)
                    elif trans_type == "update":
                        handle_commit(trans, class_name, new_obj)
                    else:
                        if num_people_added or num_people_deleted:
                            update_usage_people(tree=tree, user_id=user_id)
                        raise ValueError("Unexpected transaction type")
                except (KeyError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    if num_people_added or num_people_deleted:
                        update_usage_people(tree=tree, user_id=user_id)
                    raise ValueError("Error while processing transaction")
            trans_dict = transaction_to_json(trans)
    finally:
        # close the *writeable* db handle regardless of errors
        close_db(db_handle)
    # reopen a *readonly* db handle for seach index update
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        if num_people_new:
            update_usage_people(tree=tree, user_id=user_id)
        # update search index
        indexer: SearchIndexer = get_search_indexer(tree)
        for _trans_dict in trans_dict:
            handle = _trans_dict["handle"]
            class_name = _trans_dict["_class"]
            if _trans_dict["type"] == "delete":
                indexer.delete_object(handle, class_name)
            else:
                indexer.add_or_update_object(handle, db_handle, class_name)
        # update semantic search index
        if app_has_semantic_search():
            semantic_indexer: SemanticSearchIndexer = get_semantic_search_indexer(tree)
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                if _trans_dict["type"] == "delete":
                    semantic_indexer.delete_object(handle, class_name)
                else:
                    semantic_indexer.add_or_update_object(handle, db_handle, class_name)
    finally:
        close_db(db_handle)
    return trans_dict


def handle_delete(trans: DbTxn, class_name: str, handle: str) -> None:
    """Handle a delete action."""
    del_func = trans.db.method("remove_%s", class_name)
    del_func(handle, trans)


def handle_commit(trans: DbTxn, class_name: str, obj) -> None:
    """Handle an update action."""
    com_func = trans.db.method("commit_%s", class_name)
    com_func(obj, trans)


def handle_add(trans: DbTxn, class_name: str, obj) -> None:
    """Handle an add action."""
    if class_name != "Tag" and not obj.gramps_id:
        raise ValueError("Gramps ID missing")
    handle_commit(trans, class_name, obj)


def old_unchanged(db: DbReadBase, class_name: str, handle: str, old_data: Dict) -> bool:
    """Check if the "old" object is still unchanged."""
    handle_func = db.method("get_%s_from_handle", class_name)
    assert handle_func is not None, "No handle function found"
    try:
        obj = handle_func(handle)
    except HandleError:
        if old_data is None:
            return True
        return False
    obj_dict = object_to_dict(obj)  # json.loads(to_json(obj))
    if diff_items(class_name, old_data, obj_dict):
        return False
    return True


@shared_task(bind=True)
def update_search_indices_from_transaction(
    self, trans_dict: list[dict], tree: str, user_id: str
) -> None:
    """Update the search indices from a transaction."""
    db_handle = get_db_outside_request(
        tree=tree, view_private=True, readonly=True, user_id=user_id
    )
    try:
        indexer = get_search_indexer(tree)
        for _trans_dict in trans_dict:
            handle = _trans_dict["handle"]
            class_name = _trans_dict["_class"]
            indexer.add_or_update_object(handle, db_handle, class_name)
        if app_has_semantic_search():
            indexer_semantic = get_semantic_search_indexer(tree)
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer_semantic.add_or_update_object(handle, db_handle, class_name)
    finally:
        close_db(db_handle)


@shared_task()
def send_telemetry_task(tree: str):
    """Send telemetry"""
    if telemetry_sent_last_24h():
        # Although this task will only be called by the backend if it hasn't been
        # called in the last 24 hours, we check it here again because if a server
        # is misconfigured and the celery worker is run in a container that doesn't
        # have access to the same persistent cache as the backend, we don't want to
        # send telemetry every time a request hits the API.
        return None
    data = get_telemetry_payload(tree_id=tree)
    # if the request fails, an exception will be raised
    send_telemetry(data=data)
    update_telemetry_timestamp()
