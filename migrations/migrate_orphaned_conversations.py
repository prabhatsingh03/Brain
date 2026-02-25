"""
Migration script to associate existing orphaned conversations with new ChatSessions.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flask import Flask
from config import Config
from extensions import db
from models.conversation import ChatSession, Conversation
from models.project import Project

def migrate():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        try:
            # 1. Find all conversations with NULL session_id
            orphaned = Conversation.query.filter(Conversation.session_id == None).all()
            if not orphaned:
                print("✓ No orphaned conversations found.")
                return

            print(f"Found {len(orphaned)} orphaned conversations. Grouping them...")
            
            # Group by user_id and project_id
            groups = {}
            for conv in orphaned:
                key = (conv.user_id, conv.project_id)
                if key not in groups:
                    groups[key] = []
                groups[key].append(conv)
            
            for (u_id, p_id), convs in groups.items():
                # Sort by timestamp to get the first question for the title
                convs.sort(key=lambda x: x.timestamp)
                first_q = convs[0].question
                title = first_q[:30] + "..." if len(first_q) > 30 else first_q
                
                # Create a new session
                session = ChatSession(
                    user_id=u_id,
                    project_id=p_id,
                    title=f"Migrated Chat: {title}"
                )
                db.session.add(session)
                db.session.commit() # Get session ID
                
                print(f"Created session '{session.title}' for User {u_id} and Project {p_id}")
                
                # Link conversations to this session
                for conv in convs:
                    conv.session_id = session.id
                
            db.session.commit()
            print("✓ Successfully migrated all orphaned conversations!")
                
        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()
