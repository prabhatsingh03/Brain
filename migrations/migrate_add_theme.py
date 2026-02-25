"""
Migration script to add theme_preference column to user table
Run this script to update the database schema.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flask import Flask
from config import Config
from extensions import db
from sqlalchemy import text

def migrate():
    # Create minimal Flask app for database context
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'user' 
                AND COLUMN_NAME = 'theme_preference'
            """)).fetchone()
            
            if result:
                print("✓ Column 'theme_preference' already exists. No migration needed.")
            else:
                print("Adding 'theme_preference' column to 'user' table...")
                db.session.execute(text("""
                    ALTER TABLE user 
                    ADD COLUMN theme_preference VARCHAR(10) DEFAULT 'dark'
                """))
                db.session.commit()
                print("✓ Successfully added 'theme_preference' column!")
                
        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()
