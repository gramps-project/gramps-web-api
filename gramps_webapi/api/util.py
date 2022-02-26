#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

import hashlib
import io
import os
import smtplib
import socket
from email.message import EmailMessage
from http import HTTPStatus
from typing import BinaryIO, Optional, Sequence

from flask import abort, current_app, g, request
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.proxy import PrivateProxyDb
from gramps.gen.utils.file import expand_media_path
from gramps.gen.utils.grampslocale import GrampsLocale
from marshmallow import RAISE
from webargs.flaskparser import FlaskParser

from ..auth.const import PERM_VIEW_PRIVATE
from ..const import LOCALE_MAP
from ..dbmanager import WebDbManager
from .auth import has_permissions


class Parser(FlaskParser):
    # raise in case of unknown query arguments
    DEFAULT_UNKNOWN_BY_LOCATION = {"query": RAISE}


parser = Parser()
use_args = parser.use_args


class ModifiedPrivateProxyDb(PrivateProxyDb):
    """PrivateProxyDb with additional methods."""

    def __init__(self, *args, **kwargs):
        """Initialize self."""
        super().__init__(*args, **kwargs)
        self.name_formats = self.db.name_formats

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


def get_db_handle(readonly: bool = True) -> DbReadBase:
    """Open the database and get the current instance.

    Called before every request.

    If a user is not authorized to view private records,
    returns a proxy DB instance.

    If `readonly` is false, locks the database during the request.
    """
    if readonly and "dbstate" not in g:
        # cache the DbState instance for the duration of
        # the request
        dbmgr: WebDbManager = current_app.config["DB_MANAGER"]
        g.dbstate = dbmgr.get_db()
    if not has_permissions({PERM_VIEW_PRIVATE}):
        if not readonly:
            # requesting write access on a private proxy DB is impossible & forbidden!
            abort(HTTPStatus.FORBIDDEN)
        # if we're not authorized to view private records,
        # return a proxy DB instead of the real one
        return ModifiedPrivateProxyDb(g.dbstate.db)
    if not readonly and "dbstate_write" not in g:
        # cache the DbState instance for the duration of
        # the request
        dbmgr = current_app.config["DB_MANAGER"]
        g.dbstate_write = dbmgr.get_db(readonly=False)
    if not readonly:
        return g.dbstate_write.db
    return g.dbstate.db


def _get_db_handle_readonly(readonly: bool = True) -> DbReadBase:
    """Open the database in read-only mode and get the current instance."""
    if "dbstate" not in g:
        # cache the DbState instance for the duration of
        # the request
        dbmgr: WebDbManager = current_app.config["DB_MANAGER"]
        g.dbstate = dbmgr.get_db()
    if not has_permissions({PERM_VIEW_PRIVATE}):
        # if we're not authorized to view private records,
        # return a proxy DB instead of the real one
        return ModifiedPrivateProxyDb(g.dbstate.db)
    return g.dbstate.db


def get_media_base_dir():
    """Get the media base directory set in the database."""
    db = get_db_handle()
    return expand_media_path(db.get_mediapath(), db)


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
        abort(500)
    if delete:
        os.remove(filename)
    return buffer


def send_email(
    subject: str, body: str, to: Sequence[str], from_email: Optional[str] = None
) -> None:
    """Send an e-mail message."""
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    if not from_email:
        from_email = current_app.config["DEFAULT_FROM_EMAIL"]
    msg["From"] = from_email
    msg["To"] = ", ".join(to)

    host = current_app.config["EMAIL_HOST"]
    port = current_app.config["EMAIL_PORT"]
    user = current_app.config["EMAIL_HOST_USER"]
    password = current_app.config["EMAIL_HOST_PASSWORD"]
    use_tls = current_app.config["EMAIL_USE_TLS"]
    try:
        if use_tls:
            smtp = smtplib.SMTP_SSL(host=host, port=port, timeout=10)
        else:
            smtp = smtplib.SMTP(host=host, port=port, timeout=10)
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


def make_cache_key_thumbnails(*args, **kwargs):
    """Make a cache key for thumbnails."""
    # hash query args except jwt
    query_args = list((k, v) for (k, v) in request.args.items(multi=True) if k != "jwt")
    args_as_sorted_tuple = tuple(sorted(query_args))
    args_as_bytes = str(args_as_sorted_tuple).encode()
    arg_hash = hashlib.md5(args_as_bytes)
    arg_hash = str(arg_hash.hexdigest())

    # get media checksum
    handle = kwargs["handle"]
    db_handle = get_db_handle()
    try:
        obj = db_handle.get_media_from_handle(handle)
    except HandleError:
        abort(404)
    # checksum in the DB
    checksum = obj.checksum

    cache_key = checksum + request.path + arg_hash

    return cache_key
