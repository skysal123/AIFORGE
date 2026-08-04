"""Public-facing routes for AIForge Technologies."""
from flask import current_app, flash, redirect, render_template, url_for
from flask_wtf import FlaskForm
from wtforms import EmailField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from ...extensions import db
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
