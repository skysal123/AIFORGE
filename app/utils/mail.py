"""Mail helper.

Sends an enquiry notification to the configured CONTACT_EMAIL. If the
mail server isn't configured (dev without SMTP creds), this silently
no-ops and logs the enquiry instead — the form still succeeds.
"""
import logging
from threading import Thread

from flask import current_app
from flask_mail import Message

from ..extensions import mail

log = logging.getLogger(__name__)


def _send_async(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:  # pragma: no cover
            log.exception("Failed to send enquiry email")


def send_enquiry_notification(enquiry):
    """Email the configured recipient about a new enquiry.

    Falls back to a log line if MAIL_USERNAME is not set.
    """
    recipient = current_app.config.get("CONTACT_EMAIL")
    username = current_app.config.get("MAIL_USERNAME")

    if not username or not recipient:
        log.info(
            "Enquiry captured (no SMTP configured): %s <%s> interest=%s",
            enquiry.name, enquiry.email, enquiry.interest,
        )
        return False

    subject = f"[AIForge] New enquiry from {enquiry.name}"
    body = (
        f"Name:    {enquiry.name}\n"
        f"Email:   {enquiry.email}\n"
        f"Phone:   {enquiry.phone or '-'}\n"
        f"Interest:{enquiry.interest or '-'}\n"
        f"\nMessage:\n{enquiry.message}\n"
    )

    msg = Message(
        subject=subject,
        sender=current_app.config.get("MAIL_USERNAME"),
        recipients=[recipient],
        body=body,
    )

    Thread(target=_send_async, args=(current_app._get_current_object(), msg)).start()
    return True
