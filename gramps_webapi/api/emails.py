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


def email_reset_pw(base_url: str, user_name: str, token: str):
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

    url = f"""{base_url}/api/users/-/password/reset/?jwt={token}"""
    body = f"""{intro}

{action}

{url}

{end}
"""

    body_html = email_body_reset_pw(user_name=user_name, url=url)
    return (body, body_html)


def email_confirm_email(base_url: str, user_name: str, token: str):
    """Confirm e-mail address e-mail text."""
    intro = (
        _(
            "You are receiving this message because this e-mail address "
            "was used to register a new account at %s."
        )
        % base_url
    )
    action = _(
        "Please click on the following link, or paste this into your browser "
        "to confirm your email address. You will be able to log on once a "
        "tree owner reviews and approves your account."
    )

    url = f"""{base_url}/api/users/-/email/confirm/?jwt={token};"""

    body = f"""{intro}

{action}

{url}
"""
    body_html = email_body_confirm_email(user_name=user_name, url=url)
    return (body, body_html)


def email_new_user(base_url: str, username: str, fullname: str, email: str):
    """E-mail notifying owners of a new registered user."""
    intro = _("A new user registered at %s.") % base_url
    next_step = _(
        "Please review this user registration and assign a role to " "enable access:"
    )
    label_username = _("User name")
    label_fullname = _("Full name")
    label_email = _("E-mail")
    user_details = f"""{label_username}: {username}
{label_fullname}: {fullname}
{label_email}: {email}
"""
    return f"""{intro}

{next_step}

{user_details}
"""


def url_as_button(url: str, button_label: str) -> str:
    return f"""
        <a href="{url}" style="background-color: #6D4C41; color: white;
            padding: 10px 20px; text-decoration: none; border-radius: 4px;
            font-family: sans-serif;">
            {button_label}
        </a>
    """


def url_as_link(url: str, button_label: str) -> str:
    return f"""
        <a href="{url}" style="background-color: #6D4C41; color: white;
            padding: 10px 20px; text-decoration: none; border-radius: 4px;
            font-family: sans-serif;">
            {button_label}
        </a>
    """


def email_html_styles() -> str:
    return """
body {
    font-family: Arial, sans-serif;
    background-color: #f4f4f4;
    margin: 0;
    padding: 0;
}
.container {
    max-width: 600px;
    margin: 20px 10px;
    background: #ffffff;
    padding: 20px;
    border-radius: 10px;
    box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
}
.header {
    text-align: left;
    font-size: 24px;
    color: #333;
}
.content {
    text-align: left;
    font-size: 16px;
    color: #555;
}
.button {
    display: inline-block;
    background-color: #6D4C41;
    color: #ffffff;
    padding: 10px 20px;
    font-size: 16px;
    text-decoration: none;
    border-radius: 4px;
}
.greeting {
    font-size: 20px;
}
"""


def email_body_reset_pw(user_name: str, url: str) -> str:
    return """
    <!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
    <style>
        %(styles)s
    </style>
</head>
<body>
    <div class="container">
        <div class="header">Reset Your Password</div>
        <div class="content">
            <p class="greeting">Hi %(user_name)s,</p>
            <p>You are receiving this e-mail because you (or someone else) have requested the reset of the password for your account.</p>
            <p>Click the button below to set a new password:</p>
            <a href="%(url)s" class="button">Reset Password</a>
            <p>If you did not request a password reset, please ignore this email and your password will remain unchanged.</p>
        </div>
    </div>
</body>
</html>
    """ % {
        "user_name": user_name,
        "url": url,
        "styles": email_html_styles(),
    }


def email_body_confirm_email(user_name: str, url: str) -> str:
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Confirm Your Email Address</title>
    <style>
        %(styles)s
    </style>
</head>
<body>
    <div class="container">
        <div class="header">Welcome to Gramps Web</div>
        <div class="content">
            <p class="greeting">Hi %(user_name)s,</p>
            <p>Thank you for registering! Please confirm your email address by clicking the button below:</p>
            <a href="%(url)s" class="button">Confirm Email</a>
            <p>You will be able to log on once a tree owner reviews and approves your account.</p>
        </div>
    </div>
</body>
</html>
    """ % {
        "user_name": user_name,
        "url": url,
        "styles": email_html_styles(),
    }
