"""Mail helper.

Sends an enquiry notification to the configured CONTACT_EMAIL. If the
mail server isn't fully configured (missing MAIL_USERNAME / MAIL_PASSWORD /
CONTACT_EMAIL), this logs a clear WARNING and returns ``False`` so the
caller can decide whether to surface an error. The form still succeeds
in dev with no SMTP — the enquiry is saved to the DB either way.
"""
import logging
from threading import Thread

from flask import current_app
from flask_mail import Message

from ..extensions import mail

log = logging.getLogger(__name__)


def _send_async(app, msg):
    """Send ``msg`` in a background thread so the request returns fast.

    The exception is logged with ``log.exception`` so it shows up in
    Render's persistent log stream, instead of disappearing into a
    ``print()`` that only survives until the worker dies.
    """
    with app.app_context():
        try:
            mail.send(msg)
            log.info("Enquiry email sent to %s", msg.recipients)
        except Exception:
            log.exception("Failed to send enquiry email to %s", msg.recipients)


def send_enquiry_notification(enquiry):
    """Email the configured recipient about a new enquiry.

    Returns ``True`` if a send was dispatched, ``False`` if SMTP isn't
    fully configured (the enquiry is still saved to the DB regardless).
    """
    recipient = current_app.config.get("CONTACT_EMAIL")
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")

    missing = [name for name, val in (
        ("CONTACT_EMAIL", recipient),
        ("MAIL_USERNAME", username),
        ("MAIL_PASSWORD", password),
    ) if not val]
    if missing:
        log.warning(
            "SMTP not fully configured — missing %s. "
            "Enquiry from %s <%s> saved to DB but NOT emailed.",
            ", ".join(missing), enquiry.name, enquiry.email,
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
        sender=current_app.config.get("MAIL_DEFAULT_SENDER") or username,
        recipients=[recipient],
        body=body,
    )

    Thread(
        target=_send_async,
        args=(current_app._get_current_object(), msg),
        daemon=True,
    ).start()
    return True
