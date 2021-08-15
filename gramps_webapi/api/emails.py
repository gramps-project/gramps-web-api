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

