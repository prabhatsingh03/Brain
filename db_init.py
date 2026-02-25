import os
import pandas as pd
from flask import Flask
from config import Config, ensure_database_exists
from extensions import db, login_manager
from models.user import User
from models.project import Project, ProjectMetadata
from models.audit import AuditLog
from werkzeug.security import generate_password_hash

def create_app_context():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    ensure_database_exists()
    
    db.init_app(app)
    login_manager.init_app(app)
    return app

def seed_data():
    app = create_app_context()
    with app.app_context():
        # Create Tables
        print("Creating database tables...")
        db.create_all()

        # 1. Create Admin User (credentials from environment, with sensible defaults)
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@adventz.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')

        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            print(f"Creating admin user: {admin_email}")
            admin = User(email=admin_email, role='admin')
            admin.set_password(admin_password)
            db.session.add(admin)
        else:
            print(f"Admin user already exists: {admin_email}")

        # 2. Create Core Projects
        projects = ['DAP', 'SAP', 'PAP', 'AMMONIA']
        for p_name in projects:
            project = Project.query.filter_by(name=p_name).first()
            if not project:
                print(f"Creating project: {p_name}")
                project = Project(name=p_name, description=f"{p_name} Fertilizer Process")
                db.session.add(project)
                db.session.commit() # Commit to get ID
            
            # 3. Load Metadata for Project
            # Try to find metadata in expected locations
            possible_paths = [
                os.path.join(app.config['PROCESS_METADATA_DIR'], p_name, 'metadata.csv'),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'process_metadata', p_name, 'metadata.csv')),
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'process_metadata', p_name, 'metadata.csv')),
            ]
            
            csv_path = None
            for p in possible_paths:
                if os.path.exists(p):
                    csv_path = p
                    break
            
            if csv_path:
                print(f"Loading metadata from {csv_path}...")
                try:
                    df = pd.read_csv(csv_path)
                    df.columns = [c.strip().lower() for c in df.columns]
                    
                    count = 0
                    for _, row in df.iterrows():
                        f_path = row.get('file_path')
                        f_name = row.get('file_name')
                        if not f_path: continue
                        
                        exists = ProjectMetadata.query.filter_by(project_id=project.id, file_path=f_path).first()
                        if not exists:
                            meta = ProjectMetadata(
                                project_id=project.id,
                                type_of_data=row.get('type_of_data'),
                                file_name=f_name,
                                file_path=f_path
                                # Note: s_no from CSV is ignored; using id (auto-increment) instead
                            )
                            db.session.add(meta)
                            count += 1
                    print(f"Added {count} items for {p_name}")
                except Exception as e:
                    print(f"Error loading {csv_path}: {e}")
            else:
                # Metadata only: no directory scan (same as old_code; documents come from metadata CSV only)
                print(f"Metadata CSV not found for {p_name}. Skipping (metadata-only mode).")

        db.session.commit()
        print("Database initialization complete!")

if __name__ == '__main__':
    seed_data()
