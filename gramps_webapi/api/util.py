#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024      David Straub
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

"""Utility functions."""

from __future__ import annotations

import io
import json
import logging
import os
import smtplib
import socket
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from http import HTTPStatus
from typing import Any, BinaryIO, NoReturn, Sequence

import gramps.gen.lib
from celery import Task
from flask import (
    Response,
    abort,
    current_app,
    g,
    has_app_context,
    jsonify,
    make_response,
    request,
)
from flask_jwt_extended import get_jwt, get_jwt_identity
from flask_jwt_extended.exceptions import WrongTokenError
from gramps.cli.clidbman import NAME_FILE, CLIDbManager
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import (
    CITATION_KEY,
    DBBACKEND,
    EVENT_KEY,
    FAMILY_KEY,
    KEY_TO_NAME_MAP,
    MEDIA_KEY,
    NOTE_KEY,
    PERSON_KEY,
    PLACE_KEY,
    REPOSITORY_KEY,
    SOURCE_KEY,
)
from gramps.gen.db.exceptions import DbUpgradeRequiredError
from gramps.gen.dbstate import DbState
from gramps.gen.errors import HandleError
from gramps.gen.lib.json_utils import data_to_object, object_to_dict
from gramps.gen.proxy import PrivateProxyDb
from gramps.gen.proxy.private import sanitize_media
from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.gen.user import UserBase
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.plugins.db.dbapi.dbapi import DBAPI
from marshmallow import RAISE
from webargs.flaskparser import FlaskParser
from werkzeug.exceptions import HTTPException
from werkzeug.security import safe_join

from ..auth import config_get, get_tree, get_tree_usage, set_tree_usage
from ..auth.const import PERM_VIEW_PRIVATE
from ..const import (
    DB_CONFIG_ALLOWED_KEYS,
    LOCALE_MAP,
    PRIMARY_GRAMPS_OBJECTS,
    TREE_MULTI,
)
from ..dbmanager import WebDbManager
from .auth import has_permissions


class Parser(FlaskParser):
    # raise in case of unknown query arguments
    DEFAULT_UNKNOWN_BY_LOCATION = {"query": RAISE}

    def handle_error(self, error, req, schema, *, error_status_code, error_headers):
        status_code = error_status_code or self.DEFAULT_VALIDATION_STATUS
        pretty_message = "".join([c for c in str(error.messages) if c not in "{}[]()'"])
        payload = {
            "error": {
                "code": status_code,
                "message": pretty_message,
                "messages": error.messages,
            }
        }
        abort(
            make_response(jsonify(payload), status_code),
            exc=error,
            messages=error.messages,
            schema=schema,
            headers=error_headers,
        )


parser = Parser()
use_args = parser.use_args


class ModifiedPrivateProxyDb(PrivateProxyDb):
    """PrivateProxyDb with additional methods."""

    def __init__(self, *args, **kwargs):
        """Initialize self."""
        super().__init__(*args, **kwargs)
        self.name_formats = self.db.name_formats
        self.is_dbapi = isinstance(self.basedb, DBAPI)

    def get_dbname(self):
        """Get the name of the database."""
        return self.db.get_dbname()

    def get_summary(self):
        """Return dictionary of summary item."""
        return self.db.get_summary()

    def get_surname_list(self):
        """Return the list of locale-sorted surnames contained in the database."""
        return self.db.get_surname_list()

    def get_place_types(self):
        """Return custom place types assocated with places in the database."""
        return self.db.get_place_types()

    def set_name_group_mapping(self, name, group):
        """Set a name group mapping."""
        return self.db.set_name_group_mapping(name, group)

    # the below methods are to fix a bug in Gramps.
    # can be removed once bug is fixed in Gramps and version
    # requirement is updated.
    def get_media_from_handle(self, handle):
        """
        Finds an Object in the database from the passed Gramps ID.
        If no such Object exists, None is returned.
        """
        media = self.db.get_media_from_handle(handle)
        if media and not media.get_privacy():
            return _sanitize_media_patched(self.db, media)
        return None

    def get_media_from_gramps_id(self, val):
        """
        Finds a Media in the database from the passed Gramps ID.
        If no such Media exists, None is returned.
        """
        obj = self.db.get_media_from_gramps_id(val)
        if obj and not obj.get_privacy():
            return _sanitize_media_patched(self.db, obj)
        return None

    def _iter_handles(self, obj_key):
        """
        Return an iterator over handles in the database
        """
        table = KEY_TO_NAME_MAP[obj_key]
        sql = "SELECT handle FROM %s WHERE private=0" % table
        self.basedb.dbapi.execute(sql)
        rows = self.basedb.dbapi.fetchall()
        for row in rows:
            yield row[0]

    def iter_person_handles(self):
        """
        Return an iterator over database handles, one handle for each Person in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(PERSON_KEY)
        return filter(self.include_person, self.db.iter_person_handles())

    def iter_family_handles(self):
        """
        Return an iterator over database handles, one handle for each Family in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(FAMILY_KEY)
        return filter(self.include_family, self.db.iter_family_handles())

    def iter_event_handles(self):
        """
        Return an iterator over database handles, one handle for each Event in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(EVENT_KEY)
        return filter(self.include_event, self.db.iter_event_handles())

    def iter_source_handles(self):
        """
        Return an iterator over database handles, one handle for each Source in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(SOURCE_KEY)
        return filter(self.include_source, self.db.iter_source_handles())

    def iter_citation_handles(self):
        """
        Return an iterator over database handles, one handle for each Citation
        in the database.
        """
        if self.is_dbapi:
            return self._iter_handles(CITATION_KEY)
        return filter(self.include_citation, self.db.iter_citation_handles())

    def iter_place_handles(self):
        """
        Return an iterator over database handles, one handle for each Place in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(PLACE_KEY)
        return filter(self.include_place, self.db.iter_place_handles())

    def iter_media_handles(self):
        """
        Return an iterator over database handles, one handle for each Media
        Object in the database.
        """
        if self.is_dbapi:
            return self._iter_handles(MEDIA_KEY)
        return filter(self.include_media, self.db.iter_media_handles())

    def iter_repository_handles(self):
        """
        Return an iterator over database handles, one handle for each
        Repository in the database.
        """
        if self.is_dbapi:
            return self._iter_handles(REPOSITORY_KEY)
        return filter(self.include_repository, self.db.iter_repository_handles())

    def iter_note_handles(self):
        """
        Return an iterator over database handles, one handle for each Note in
        the database.
        """
        if self.is_dbapi:
            return self._iter_handles(NOTE_KEY)
        return filter(self.include_note, self.db.iter_note_handles())


class UserTaskProgress(UserBase):
    """Web API specific implementation of `gramps.gen.user.UserBase`.

    Needed for implementing progress displays. This has nothing
    to do with Gramps Web API user management."""

    def __init__(self, task: Task):
        """Init."""
        UserBase.__init__(
            self, callback=self._callback, error=None, uistate=None, dbstate=None
        )
        self.task = task
        self.steps = 0
        self.current_step = 0
        self.progress_title = ""
        self.progress_message = ""

    def _callback(self, percentage, text=None):
        """Report only the percentage."""
        if percentage >= 0 and percentage < 100:
            self.task.update_state(
                state="PROGRESS",
                meta={
                    "progress": percentage / 100,
                },
            )

    def _report_progress(self) -> None:
        """Report the progress in the task result."""
        if self.steps == 0:
            progress = -1.0
        else:
            progress = self.current_step / self.steps
            if progress < 0 or progress >= 1:
                progress = -1
        self.task.update_state(
            state="PROGRESS",
            meta={
                "current": self.current_step,
                "total": self.steps,
                "progress": progress,
                "title": self.progress_title,
                "message": self.progress_message,
            },
        )

    def begin_progress(self, title: str, message: str, steps: int) -> None:
        """Start showing a progress indicator to the user."""
        self.steps = steps
        self.current_step = 0
        self.progress_title = title or ""
        self.progress_message = message or ""
        self._report_progress()

    def step_progress(self) -> None:
        """Advance the progress meter."""
        self.current_step += 1
        self._report_progress()

    def end_progress(self) -> None:
        """Stop showing the progress indicator to the user."""
        # do nothing - celery will handle task completion status itself

    def prompt(self, *args, **kwargs):
        """Prompt the user with a message to select an alternative."""
        # Not needed for Web API
        return True

    def warn(self, title: str, warning: str = "") -> None:
        """Warn the user."""

    def notify_error(self, title: str, error: str = "") -> None:
        """Notify the user of an error."""
        abort_with_message(HTTPStatus.INTERNAL_SERVER_ERROR, f"{title}\n\n{error}")

    def notify_db_error(self, error: str) -> None:
        """Notify the user of a DB error."""
        self.notify_error(title="Low level database corruption detected", error=error)

    def notify_db_repair(self, error: str) -> None:
        """Notify the user their DB might need repair."""
        self.notify_error(title="Error detected in database.", error=error)

    def info(self, msg1, infotext, parent=None, monospaced=False):
        """Displays information to the user."""


def _sanitize_media_patched(db, media):
    """Patched sanitize_media function."""
    obj = sanitize_media(db, media)
    obj.set_checksum(media.get_checksum())
    return obj


def get_db_manager(tree: str | None) -> WebDbManager:
    """Get an appropriate WebDbManager instance."""
    return WebDbManager(
        dirname=tree,
        username=current_app.config["POSTGRES_USER"],
        password=current_app.config["POSTGRES_PASSWORD"],
        create_if_missing=False,
        ignore_lock=current_app.config["IGNORE_DB_LOCK"],
    )


def get_tree_from_jwt() -> str | None:
    """Get the tree ID from the token.

    Needs request context. Can return None if no tree ID is present,
    e.g. for e-mail confirmation or password reset tokens.
    """
    try:
        claims = get_jwt()
    except WrongTokenError:
        # wrong token type, so no tree ID
        return None
    return claims.get("tree")


def get_tree_from_jwt_or_fail() -> str:
    """Get the tree ID from the token.

    Needs request context. Will fail if no tree ID is present.
    """
    tree = get_tree_from_jwt()
    if not tree:
        abort_with_message(403, "No tree ID in JWT")
        raise  # mypy; unreachable
    return tree


def get_db_outside_request(
    tree: str, view_private: bool, readonly: bool, user_id: str
) -> DbReadBase:
    """Open the database and get the current instance.

    Called before every request.

    If a user is not authorized to view private records,
    returns a proxy DB instance.

    If `readonly` is false, locks the database during the request.
    """
    dbmgr = get_db_manager(tree)
    try:
        dbstate = dbmgr.get_db(user_id=user_id, readonly=readonly)
    except DbUpgradeRequiredError:
        abort_with_message(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "The Gramps database needs a schema upgrade",
        )
    if not view_private:
        if not readonly:
            # requesting write access on a private proxy DB is impossible & forbidden!
            abort_with_message(
                HTTPStatus.FORBIDDEN, "Cannot write to a private proxy database"
            )
        # if we're not authorized to view private records,
        # return a proxy DB instead of the real one
        return ModifiedPrivateProxyDb(dbstate.db)
    return dbstate.db


def close_db(db_handle: DbReadBase) -> None:
    """Close the connection to the database including the undo log."""
    db_handle.close()
    if isinstance(db_handle, ProxyDbBase):
        db_handle.basedb.undodb.close()
    else:
        db_handle.undodb.close()


def get_db_handle(readonly: bool = True) -> DbReadBase:
    """Open the database and get the current instance.

    Called before every request.

    If a user is not authorized to view private records,
    returns a proxy DB instance.

    If `readonly` is false, locks the database during the request.
    """
    view_private = has_permissions({PERM_VIEW_PRIVATE})
    tree = get_tree_from_jwt_or_fail()
    user_id = get_jwt_identity()

    if readonly and "db" not in g:
        # cache the db instance for the duration of
        # the request
        db = get_db_outside_request(
            tree=tree,
            view_private=view_private,
            readonly=True,
            user_id=user_id,
        )
        g.db = db

    if not view_private:
        if not readonly:
            # requesting write access on a private proxy DB is impossible & forbidden!
            abort_with_message(
                HTTPStatus.FORBIDDEN, "Cannot write to a private proxy database"
            )
        return ModifiedPrivateProxyDb(g.db)

    if not readonly and "db_write" not in g:
        # cache the DbState instance for the duration of
        # the request
        # cache the db instance for the duration of
        # the request
        db_write = get_db_outside_request(
            tree=tree,
            view_private=view_private,
            readonly=False,
            user_id=user_id,
        )
        g.db_write = db_write
    if not readonly:
        return g.db_write
    return g.db


def get_locale_for_language(language: str, default: bool = False) -> GrampsLocale:
    """Get GrampsLocale set to specified language."""
    if language is not None:
        catalog = GRAMPS_LOCALE.get_language_dict()
        for entry in catalog:
            if catalog[entry] == language:
                # translate language code (e.g. "da") to locale code (e.g. "da_DK")
                locale_code = LOCALE_MAP.get(language, language)
                if "UTF" not in locale_code.upper():
                    locale_code = f"{locale_code}.UTF-8"
                return GrampsLocale(lang=locale_code)
    if default:
        return GRAMPS_LOCALE
    return None


def get_buffer_for_file(filename: str, delete=True, not_found=False) -> BinaryIO:
    """Return binary buffer with file contents."""
    try:
        with open(filename, "rb") as file_handle:
            buffer = io.BytesIO(file_handle.read())
    except FileNotFoundError:
        if not_found:
            raise FileNotFoundError
        abort_with_message(500, "File not found")
    if delete:
        os.remove(filename)
    return buffer


def send_email(
    subject: str,
    body: str,
    to: Sequence[str],
    from_email: str | None = None,
    body_html: str | None = None,
) -> None:
    """Send an e-mail message."""
    msg = EmailMessage()
    msg.set_content(body)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    msg["Subject"] = subject
    if not from_email:
        from_email = get_config("DEFAULT_FROM_EMAIL")
    msg["From"] = from_email
    msg["To"] = ", ".join(to)
    msg["Message-ID"] = make_msgid()
    msg["Date"] = formatdate(localtime=True)

    host = get_config("EMAIL_HOST")
    port = int(get_config("EMAIL_PORT"))
    user = get_config("EMAIL_HOST_USER")
    password = get_config("EMAIL_HOST_PASSWORD")
    use_tls = get_config("EMAIL_USE_TLS")
    try:
        smtp: smtplib.SMTP | smtplib.SMTP_SSL
        if use_tls:
            smtp = smtplib.SMTP_SSL(host=host, port=port, timeout=10)
        else:
            smtp = smtplib.SMTP(host=host, port=port, timeout=10)
            smtp.ehlo()
            if port != 25:
                smtp.starttls()
                smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)
        smtp.quit()
    except ConnectionRefusedError:
        current_app.logger.error("Connection to SMTP server refused.")
        raise ValueError("Connection was refused.")
    except socket.timeout:
        current_app.logger.error("SMTP connection attempt timed out.")
        raise ValueError("Connection attempt timed out.")
    except OSError:
        current_app.logger.error("Error while trying to send e-mail.")
        raise ValueError("Error while trying to send e-mail.")


def get_config(key: str) -> Any:
    """Get a config item.

    If exists, returns the config item from the database.
    Else, uses the app.config dictionary.
    """
    if key in DB_CONFIG_ALLOWED_KEYS:
        val = config_get(key)
        if val is not None:
            return val
    return current_app.config.get(key)


def list_trees() -> list[tuple[str, str]]:
    """Get a list of tree dirnames and names."""
    dbstate = DbState()
    dbman = CLIDbManager(dbstate)
    return dbman.current_names


def get_tree_id(guid: str) -> str:
    """Get the appropriate tree ID for a user."""
    tree_id = get_tree(guid)
    if not tree_id:
        if current_app.config["TREE"] == TREE_MULTI:
            # multi-tree support enabled but user has no tree ID: forbidden!
            abort_with_message(403, "Forbidden")
        # needed for backwards compatibility: single-tree mode but user without tree ID
        dbmgr = WebDbManager(
            name=current_app.config["TREE"],
            create_if_missing=False,
            ignore_lock=current_app.config["IGNORE_DB_LOCK"],
        )
        tree_id = dbmgr.dirname
    return tree_id


def tree_exists(tree_id: str) -> bool:
    """Check if a tree exists."""
    dbdir = config.get("database.path")
    dir_path = safe_join(dbdir, tree_id)
    if not dir_path:
        return False
    if not os.path.isdir(dir_path):
        return False
    name_path = os.path.join(dir_path, NAME_FILE)
    if not os.path.isfile(name_path):
        return False
    dbid_path = os.path.join(dir_path, DBBACKEND)
    if not os.path.isfile(dbid_path):
        return False
    return True


def update_usage_people(tree: str | None = None, user_id: str | None = None) -> int:
    """Update the usage of people."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    if not user_id:
        user_id = get_jwt_identity()
    assert user_id is not None, "Unexpected error while looking up user ID."
    db_handle = get_db_outside_request(
        tree=tree,
        view_private=True,
        readonly=True,
        user_id=user_id,
    )
    try:
        usage_people = db_handle.get_number_of_people()
    finally:
        close_db(db_handle)
    set_tree_usage(tree, usage_people=usage_people)
    return usage_people


def check_quota_people(
    to_add: int, tree: str | None = None, user_id: str | None = None
) -> None:
    """Check whether the quota allows adding `to_add` people and abort if not."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    if not user_id:
        user_id = get_jwt_identity()
    usage_dict = get_tree_usage(tree)
    if not usage_dict or usage_dict.get("usage_people") is None:
        update_usage_people(tree=tree, user_id=user_id)
        usage_dict = get_tree_usage(tree)
    assert usage_dict is not None, "Unexpected error while looking up usage data."
    usage = usage_dict["usage_people"]
    quota = usage_dict.get("quota_people")
    if quota is None:
        return
    if usage + to_add > quota:
        abort_with_message(405, "Not allowed by people quota")


def update_usage_ai(new: int, tree: str | None = None) -> int:
    """Update the usage of AI by adding `new` units to the usage."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    usage_dict = get_tree_usage(tree)
    if not usage_dict:
        old_usage = 0
    else:
        old_usage = usage_dict.get("usage_ai") or 0
    new_usage = old_usage + new
    set_tree_usage(tree, usage_ai=new_usage)
    return new_usage


def check_quota_ai(requested: int, tree: str | None = None) -> None:
    """Check whether the AI quota allows consuming another `requested` units."""
    if not tree:
        tree = get_tree_from_jwt_or_fail()
    usage_dict = get_tree_usage(tree)
    if not usage_dict:
        return
    usage = usage_dict.get("usage_ai") or 0
    quota = usage_dict.get("quota_ai")
    if quota is None:
        return
    if usage + requested > quota:
        abort_with_message(405, "Not allowed by AI quota")


def abort_with_message(status: int, message: str) -> NoReturn:
    """Abort with a JSON response."""
    payload = {"error": {"code": status, "message": message}}
    response = Response(
        response=json.dumps(payload),
        status=status,
        mimetype="application/json",
    )
    exc = HTTPException(response=response, description=message)
    exc.code = status
    raise exc


def upgrade_gramps_database(tree: str, user_id: str, task: Task | None = None) -> None:
    """Upgrade the Gramps database for a tree."""
    dbmgr = get_db_manager(tree=tree)
    dbmgr.upgrade_if_needed(user_id=user_id, user=UserTaskProgress(task=task))
    dbstate = dbmgr.get_db(user_id=user_id, readonly=True)
    dbstate.db.close()


def get_total_number_of_objects(db_handle: DbReadBase):
    """Get the total number of searchable objects in the database."""
    return (
        db_handle.get_number_of_people()
        + db_handle.get_number_of_families()
        + db_handle.get_number_of_sources()
        + db_handle.get_number_of_citations()
        + db_handle.get_number_of_events()
        + db_handle.get_number_of_media()
        + db_handle.get_number_of_places()
        + db_handle.get_number_of_repositories()
        + db_handle.get_number_of_notes()
        + db_handle.get_number_of_tags()
    )


def get_object_timestamps(db_handle: DbReadBase):
    """Get a dictionary with change timestamps of all objects in the DB."""
    d: dict[str, set[tuple[int, float | int]]] = {}
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        d[class_name] = set()
        iter_method = db_handle.method("iter_%s_handles", class_name)
        assert iter_method is not None, f"Method iter_{class_name}_handles not found"
        for handle in iter_method():
            query_method = db_handle.method("get_%s_from_handle", class_name)
            obj = query_method(handle)
            d[class_name].add((handle, obj.change))
    return d


def get_logger() -> logging.Logger:
    """Get an appropriate logger instance."""
    if has_app_context() and current_app.logger:
        return current_app.logger
    else:
        # Fallback to a standard logger
        logger = logging.getLogger(__name__)
        if not logger.hasHandlers():
            # If the logger is not configured yet, set up basic configuration
            logging.basicConfig(level=logging.INFO)
        return logger


def complete_gramps_object_dict(data: dict[str, Any]):
    """Restore a JSON dictionary to its full form, adding placeholders
    for missing attributes."""
    for key, value in data.items():
        if isinstance(value, list):
            for i in range(len(value)):
                if isinstance(value[i], dict):
                    value[i] = complete_gramps_object_dict(value[i])
        elif isinstance(value, dict):
            data[key] = complete_gramps_object_dict(value)
    _class = data.get("_class")
    if _class is None:
        return data
    cls = gramps.gen.lib.__dict__[_class]
    empty_obj = cls()
    empty_obj_dict = object_to_dict(empty_obj)
    for key, value in empty_obj_dict.items():
        if key not in data:
            data[key] = value
    return data


def gramps_object_from_dict(data: dict[str, Any]):
    """Instantiate a Gramps object from a dictionary.

    The dictionary can be incomplete, i.e. not contain all properties of
    the object class."""
    return data_to_object(complete_gramps_object_dict(data))
