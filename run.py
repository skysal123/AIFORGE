"""Entry point for local development.

    python run.py

Activates Flask's debug reloader. In production, use gunicorn:

    gunicorn "app:create_app()" --bind 0.0.0.0:8000
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
