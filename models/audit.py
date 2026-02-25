from datetime import datetime
from extensions import db

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=True) # Email or User ID
    action = db.Column(db.String(50), nullable=False) # e.g. "QUERY", "VIEW_FILE", "DOWNLOAD"
    details = db.Column(db.Text, nullable=True) # Question asked or Filename accessed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_id} at {self.timestamp}>'
