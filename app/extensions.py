"""Flask extension singletons.

These are created here and bound to the app inside ``create_app`` so that
blueprints can ``from .extensions import db`` without circular imports.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
mail = Mail()
csrf = CSRFProtect()
