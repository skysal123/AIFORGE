"""Public-facing routes for AIForge Technologies."""
from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from wtforms import EmailField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from ...extensions import db, mail
from ...models import Enquiry
from ...utils.mail import send_enquiry_notification
from . import main_bp


# --------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------- #

INTEREST_CHOICES = [
    ("", "— Select what you're interested in —"),
    ("ai-solutions", "Custom AI Solutions"),
    ("web-development", "Web / Software Development"),
    ("ai-integration", "AI Integration for an Existing Site"),
    ("training", "Corporate / College Training"),
    ("student-mentorship", "Student Mentorship / Final-Year Project"),
    ("ai-assistant", "AI Assistant (AaaS)"),
    ("other", "Something Else"),
]


class EnquiryForm(FlaskForm):
    name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={"placeholder": "Your name", "autocomplete": "name"},
    )
    email = EmailField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"placeholder": "you@company.com", "autocomplete": "email"},
    )
    phone = StringField(
        "Phone (optional)",
        validators=[Optional(), Length(max=40)],
        render_kw={"placeholder": "+91 98xxxxxxxx", "autocomplete": "tel"},
    )
    interest = SelectField(
        "What can we help with?",
        choices=INTEREST_CHOICES,
        validators=[Optional()],
    )
    message = TextAreaField(
        "Tell us about your project",
        validators=[DataRequired(), Length(min=10, max=2000)],
        render_kw={"placeholder": "A few lines on what you're trying to build…", "rows": 5},
    )


# --------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------- #

@main_bp.route("/")
def landing():
    return render_template(
        "landing.html",
        brand=current_app.config["BRAND_NAME"],
        tagline=current_app.config["BRAND_TAGLINE"],
    )


@main_bp.route("/services")
def services():
    return render_template(
        "services.html",
        brand=current_app.config["BRAND_NAME"],
    )


@main_bp.route("/about")
def about():
    return render_template(
        "about.html",
        brand=current_app.config["BRAND_NAME"],
    )


@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = EnquiryForm()
    if form.validate_on_submit():
        enquiry = Enquiry(
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            phone=(form.phone.data or "").strip() or None,
            interest=(form.interest.data or "").strip() or None,
            message=form.message.data.strip(),
        )
        db.session.add(enquiry)
        db.session.commit()
        send_enquiry_notification(enquiry)
        flash("Thanks — we'll get back to you within one business day.", "success")
        return redirect(url_for("main.thank_you"))

    return render_template(
        "contact.html",
        brand=current_app.config["BRAND_NAME"],
        form=form,
    )


@main_bp.route("/thank-you")
def thank_you():
    return render_template(
        "thank_you.html",
        brand=current_app.config["BRAND_NAME"],
    )


# --------------------------------------------------------------------- #
# Debug helpers — temporary, for diagnosing SendGrid wiring on Render.    #
# Remove or gate behind ADMIN_TOKEN before going to a real production.   #
# --------------------------------------------------------------------- #

@main_bp.route("/debug/mail-config")
def debug_mail_config():
    """Return the mail-related env vars Flask-Mail is actually using.

    Doesn't include the password — that one stays masked.
    """
    cfg = current_app.config
    return jsonify(
        {
            "MAIL_SERVER":            cfg.get("MAIL_SERVER"),
            "MAIL_PORT":              cfg.get("MAIL_PORT"),
            "MAIL_USE_TLS":           cfg.get("MAIL_USE_TLS"),
            "MAIL_USE_SSL":           cfg.get("MAIL_USE_SSL"),
            "MAIL_USERNAME":          cfg.get("MAIL_USERNAME"),
            "MAIL_PASSWORD_set":      bool(cfg.get("MAIL_PASSWORD")),
            "MAIL_PASSWORD_length":   len(cfg.get("MAIL_PASSWORD") or ""),
            "MAIL_DEFAULT_SENDER":    cfg.get("MAIL_DEFAULT_SENDER"),
            "CONTACT_EMAIL":          cfg.get("CONTACT_EMAIL"),
            "flask_mail_default_sender": getattr(mail, "default_sender", None),
            "AIFORGE_ENV":            cfg.get("AIFORGE_ENV"),
        }
    )


@main_bp.route("/debug/send-test-email", methods=["POST"])
def debug_send_test_email():
    """Send a real test email synchronously and return the exception (if any).

    Hit this with curl from your terminal:

        curl -X POST https://aiforge-zaxl.onrender.com/debug/send-test-email

    Whatever this prints is what Flask-Mail is actually doing.
    """
    from flask_mail import Message

    cfg = current_app.config
    recipient = cfg.get("CONTACT_EMAIL")
    sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME")
    if not recipient or not sender:
        return jsonify(
            ok=False,
            error="Missing CONTACT_EMAIL / MAIL_USERNAME / MAIL_DEFAULT_SENDER",
            config={
                "recipient_set": bool(recipient),
                "sender": sender,
            },
        ), 400

    msg = Message(
        subject="[AIForge] Render mail debug test",
        sender=sender,
        recipients=[recipient],
        body=(
            "If you're reading this in your inbox, mail is wired up.\n\n"
            f"FROM: {sender}\nTO: {recipient}\nSERVER: {cfg.get('MAIL_SERVER')}\n"
            f"PORT: {cfg.get('MAIL_PORT')}\nTLS: {cfg.get('MAIL_USE_TLS')}\n"
            f"SSL: {cfg.get('MAIL_USE_SSL')}\n"
        ),
    )

    try:
        mail.send(msg)
        return jsonify(ok=True, sent_to=recipient, from_=sender)
    except Exception as exc:
        return jsonify(
            ok=False,
            error_class=type(exc).__name__,
            error_message=str(exc),
            config={
                "MAIL_SERVER": cfg.get("MAIL_SERVER"),
                "MAIL_PORT":   cfg.get("MAIL_PORT"),
                "MAIL_USE_TLS": cfg.get("MAIL_USE_TLS"),
                "MAIL_USE_SSL": cfg.get("MAIL_USE_SSL"),
            },
        ), 500
