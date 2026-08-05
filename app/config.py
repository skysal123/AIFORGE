"""Configuration for AIForge Technologies.

Loaded by ``create_app`` via the ``AIFORGE_ENV`` environment variable.
Defaults to ``DevelopmentConfig`` when no env is set.
"""
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class BaseConfig:
    """Defaults shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'aiforge.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail — leave unset in dev so contact form can no-op gracefully.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME","aiforgetechno@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD","grwd daua dqrx sibk")
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "aiforgetechno@gmail.com")

    # Brand
    BRAND_NAME = "AIForge Technologies"
    BRAND_TAGLINE = "From ideas to intelligent products."


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.environ.get("AIFORGE_ENV", "development").lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
