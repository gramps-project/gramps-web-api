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


"""Texts for e-mails."""

from gettext import gettext as _


def email_reset_pw(base_url: str, token: str):
    """Reset password e-mail text."""
    intro = _(
        "You are receiving this e-mail because you (or someone else) "
        "have requested the reset of the password for your account."
    )

    action = _(
        "Please click on the following link, or paste this into your browser "
        "to complete the process:"
    )

    end = _(
        "If you did not request this, please ignore this e-mail "
        "and your password will remain unchanged."
    )
    return f"""{intro}

{action}

{base_url}/api/users/-/password/reset/?jwt={token}

{end}
"""


def email_confirm_email(base_url: str, token: str):
    """Confirm e-mail address e-mail text."""
    intro = (
        _(
            "You are receiving this e-mail because you (or someone else) "
            "have registered a new account at %s."
        )
        % base_url
    )
    action = _(
        "Please click on the following link, or paste this into your browser "
        "to complete the process:"
    )

    return f"""{intro}

{action}

{base_url}/api/users/-/email/confirm/?jwt={token}
"""


def email_new_user(base_url: str, username: str, fullname: str, email: str):
    """E-mail notifying owners of a new registered user."""
    intro = _("A new user registered at %s:") % base_url
    label_username = _("User name")
    label_fullname = _("Full name")
    label_email = _("E-mail")
    user_details = f"""{label_username}: {username}
{label_fullname}: {fullname}
{label_email}: {email}
"""
    return f"""{intro}

{user_details}
"""
