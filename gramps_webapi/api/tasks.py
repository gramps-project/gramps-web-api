"""Execute tasks."""

from gettext import gettext as _

from flask import current_app

from .emails import email_confirm_email, email_reset_pw
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
