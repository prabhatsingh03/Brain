"""
Migration script to add share_token column to chat_session table.
Enables view-only shared chat links.
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flask import Flask
from config import Config
from extensions import db
from sqlalchemy import text


def migrate():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        try:
            result = db.session.execute(text("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'chat_session'
                AND COLUMN_NAME = 'share_token'
            """)).fetchone()

            if not result:
                db.session.execute(text("""
                    ALTER TABLE chat_session
                    ADD COLUMN share_token VARCHAR(64) UNIQUE NULL
                """))
                db.session.commit()
                print("[OK] Added 'share_token' to chat_session")
            else:
                print("[OK] Column 'share_token' already exists in chat_session")
        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    migrate()
