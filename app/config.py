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

    # ---- Flask-Mail ----
    # All mail credentials MUST come from environment variables — never bake
    # secrets into source. Defaults intentionally left empty so that a
    # misconfigured deploy is loud instead of silently "working" against the
    # wrong mailbox. See README / Render env settings for the required vars.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER",
        os.environ.get("MAIL_USERNAME"),  # fall back to MAIL_USERNAME
    )
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL")

    # ---- Brand ----
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

