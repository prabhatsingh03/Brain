from extensions import db
from datetime import datetime

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # DAP, SAP, etc.
    description = db.Column(db.String(200))
    # Relationships
    metadata_items = db.relationship('ProjectMetadata', backref='project', lazy=True)
    conversations = db.relationship('Conversation', backref='project', lazy=True)
    file_cache_items = db.relationship('FileUploadCache', backref='project', lazy=True, cascade='all, delete-orphan')

class ProjectMetadata(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    type_of_data = db.Column(db.String(500))  # was 100; increased to avoid MySQL 1406 "Data too long"
    
    def to_dict(self):
        return {
            'id': self.id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'type_of_data': self.type_of_data
        }

class ProjectDependency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(50), nullable=False) # Source project
    dependency_name = db.Column(db.String(50), nullable=False) # Target dependency

class FileUploadCache(db.Model):
    """
    Cache for Gemini file uploads to avoid re-uploading the same files.
    Maps local file paths to Gemini file IDs per project.
    """
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    local_path = db.Column(db.String(500), nullable=False)  # Resolved/normalized path used as cache key
    gemini_file_id = db.Column(db.String(255), nullable=False)  # Gemini file ID (e.g., "files/...")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Unique constraint: one cache entry per (project_id, local_path)
    __table_args__ = (db.UniqueConstraint('project_id', 'local_path', name='uq_project_local_path'),)
