"""
Consolidated migration to verify and add all chat-related schema fields.
Ensures backward compatibility for databases created at different stages.
"""
import sys, os
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
            # Ensure chat_session table exists
            db.create_all()
            
            # Check and add chat_session columns
            columns_to_check = [
                ('title', "VARCHAR(255) DEFAULT 'New Chat'"),
                ('updated_at', "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                ('is_pinned', "BOOLEAN DEFAULT FALSE")
            ]
            
            for col_name, col_def in columns_to_check:
                result = db.session.execute(text(f"""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'chat_session' 
                    AND COLUMN_NAME = '{col_name}'
                """)).fetchone()
                
                if not result:
                    db.session.execute(text(f"ALTER TABLE chat_session ADD COLUMN {col_name} {col_def}"))
                    db.session.commit()
                    print(f"[OK] Added '{col_name}' to chat_session")
                else:
                    print(f"[OK] Column '{col_name}' already exists in chat_session")
                    
                    # Comment 2: Ensure updated_at has ON UPDATE behavior
                    if col_name == 'updated_at':
                        extra = db.session.execute(text(f"""
                            SELECT EXTRA FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE()
                            AND TABLE_NAME = 'chat_session' 
                            AND COLUMN_NAME = 'updated_at'
                        """)).scalar()
                        
                        if extra is None:
                            extra = ''
                        
                        if 'on update' not in extra.lower():
                            db.session.execute(text(f"ALTER TABLE chat_session MODIFY COLUMN {col_name} {col_def}"))
                            db.session.commit()
                            print(f"[OK] Fix: Added ON UPDATE CURRENT_TIMESTAMP to '{col_name}'")
            
            # Check conversation.session_id
            result = db.session.execute(text("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'conversation' 
                AND COLUMN_NAME = 'session_id'
            """)).fetchone()
            
            if not result:
                db.session.execute(text("""
                    ALTER TABLE conversation 
                    ADD COLUMN session_id INT,
                    ADD CONSTRAINT fk_session FOREIGN KEY (session_id) 
                    REFERENCES chat_session(id) ON DELETE CASCADE
                """))
                db.session.commit()
                print("[OK] Added 'session_id' to conversation")
            else:
                print("[OK] Column 'session_id' already exists in conversation")

                # Comment 1: Ensure FK exists and has ON DELETE CASCADE
                fk_result = db.session.execute(text("""
                    SELECT CONSTRAINT_NAME, DELETE_RULE 
                    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
                    WHERE CONSTRAINT_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'conversation'
                    AND REFERENCED_TABLE_NAME = 'chat_session'
                """)).fetchone()

                if not fk_result:
                    try:
                        db.session.execute(text("""
                            ALTER TABLE conversation ADD CONSTRAINT fk_session 
                            FOREIGN KEY (session_id) REFERENCES chat_session(id) 
                            ON DELETE CASCADE
                        """))
                        db.session.commit()
                        print("[OK] Fix: Added missing FK constraint to 'session_id'")
                    except Exception as e:
                        print(f"[WARN] Could not add FK constraint: {e}")
                else:
                    constraint_name, delete_rule = fk_result
                    if delete_rule != 'CASCADE':
                        try:
                            # Drop existing constraint
                            db.session.execute(text(f"ALTER TABLE conversation DROP FOREIGN KEY {constraint_name}"))
                            
                            # Re-add with CASCADE
                            db.session.execute(text(f"""
                                ALTER TABLE conversation ADD CONSTRAINT {constraint_name}
                                FOREIGN KEY (session_id) REFERENCES chat_session(id)
                                ON DELETE CASCADE
                            """))
                            db.session.commit()
                            print(f"[OK] Fix: Updated FK '{constraint_name}' to ON DELETE CASCADE")
                        except Exception as e:
                            print(f"[WARN] Could not update FK constraint: {e}")
                    else:
                        print(f"[OK] FK '{constraint_name}' already has ON DELETE CASCADE")
                
        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()
