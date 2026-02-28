"""
Create comparison_upload table for DB-backed comparison mode uploads.
Enables comparison mode to work across Gunicorn workers (no in-memory store).
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db


def migrate():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("[OK] comparison_upload table ensured (create_all).")


if __name__ == "__main__":
    migrate()
