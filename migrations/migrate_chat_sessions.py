"""
Migration script to add session_id column to conversation table and create chat_session table.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flask import Flask
from config import Config
from extensions import db
from sqlalchemy import text
from models.conversation import ChatSession, Conversation

def migrate():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        try:
            # 1. Ensure chat_session table exists
            print("Creating chat_session table if it doesn't exist...")
            db.create_all()
            
            # 2. Check if column already exists in conversation
            result = db.session.execute(text("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'conversation' 
                AND COLUMN_NAME = 'session_id'
            """)).fetchone()
            
            if result:
                print("✓ Column 'session_id' already exists in 'conversation'. No migration needed.")
            else:
                print("Adding 'session_id' column to 'conversation' table...")
                db.session.execute(text("""
                    ALTER TABLE conversation 
                    ADD COLUMN session_id INT,
                    ADD CONSTRAINT fk_session FOREIGN KEY (session_id) REFERENCES chat_session(id) ON DELETE CASCADE
                """))
                db.session.commit()
                print("✓ Successfully added 'session_id' column!")
                
        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()
