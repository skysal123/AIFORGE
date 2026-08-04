"""Database models."""
from datetime import datetime

from .extensions import db


class Enquiry(db.Model):
    """A lead captured from the contact form."""

    __tablename__ = "enquiries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    interest = db.Column(db.String(80), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):  # pragma: no cover
        return f"<Enquiry {self.id} {self.email}>"
