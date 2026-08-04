"""Main marketing site blueprint."""
from flask import Blueprint

main_bp = Blueprint("main", __name__)

# Import routes at module level so @main_bp.route decorators fire on import.
# (Avoids a circular import where routes.py tried to import main_bp.)
from . import routes  # noqa: E402,F401
