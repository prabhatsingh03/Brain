"""
Stores comparison-mode uploads so any Gunicorn worker can resolve upload_id -> gemini_file_id.
Replaces in-memory COMPARISON_UPLOADS for production multi-worker setups.
"""
from datetime import datetime
from extensions import db


class ComparisonUpload(db.Model):
    __tablename__ = "comparison_upload"

    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    gemini_file_id = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ComparisonUpload {self.upload_id} user_id={self.user_id} gemini_file_id={self.gemini_file_id}>"
