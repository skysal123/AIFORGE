"""Application factory for AIForge Technologies."""
from datetime import datetime

from flask import Flask

from .config import get_config
from .extensions import db, mail, csrf


def create_app(config_object=None):
    """Build and return a configured Flask app instance."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_object or get_config())

    # Initialise extensions
    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    # Make the current year available to every template
    @app.context_processor
    def inject_globals():
        return {"now_year": datetime.utcnow().year}

    # Register blueprints
    from .blueprints.main import main_bp
    app.register_blueprint(main_bp)

    # Auto-create tables in dev (swap for migrations before production)
    with app.app_context():
        from . import models  # noqa: F401  (registers models on db)
        db.create_all()

    return app
