#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021      David Straub
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

from gettext import gettext as _

from flask import abort, current_app

from .emails import email_confirm_email, email_new_user, email_reset_pw
from .util import send_email


def send_email_reset_password(email: str, token: str):
    """Send an email for password reset."""
    base_url = current_app.config["BASE_URL"].rstrip("/")
    body = email_reset_pw(base_url=base_url, token=token)
    subject = _("Reset your Gramps password")
    send_email(subject=subject, body=body, to=[email])


def send_email_confirm_email(email: str, token: str):
    """Send an email to confirm an e-mail address."""
    base_url = current_app.config["BASE_URL"].rstrip("/")
    body = email_confirm_email(base_url=base_url, token=token)
    subject = _("Confirm your e-mail address")
    send_email(subject=subject, body=body, to=[email])


def send_email_new_user(username: str, fullname: str, email: str):
    """Send an email to owners to notify of a new registered user."""
    base_url = current_app.config["BASE_URL"].rstrip("/")
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
