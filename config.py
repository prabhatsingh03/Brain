import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
import pymysql

load_dotenv()


def ensure_database_exists():
    """Create the database if it doesn't exist"""
    db_user = os.environ.get('DB_USER', 'root')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_name = os.environ.get('DB_NAME', 'simon_brain')
    
    try:
        connection = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password
        )
        
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"Database '{db_name}' is ready (created or already exists)")
        
        connection.close()
        return True
    except Exception as e:
        print(f"Error ensuring database exists: {e}")
        return False


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-prod'

    # Database Configuration
    DB_USER = os.environ.get('DB_USER', 'root')
    # URL‑encode the password so special characters like @, :, / etc. are handled safely
    _raw_password = os.environ.get('DB_PASSWORD', 'password')
    DB_PASSWORD = quote_plus(_raw_password)
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_NAME = os.environ.get('DB_NAME', 'simon_brain')

    # Fallback to DATABASE_URL if provided, else construct from components
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

    # Gemini
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # App Settings (paths aligned with old_code: process_metadata, process_file_cache_detail)
    _BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    PROCESS_METADATA_DIR = os.environ.get('PROCESS_METADATA_DIR') or os.path.join(_BASE_DIR, 'process_metadata')
    PROCESS_FILE_CACHE_DIR = os.path.join(_BASE_DIR, 'process_file_cache_detail')
    PROJECT_DOCS_DIR = os.environ.get('PROJECT_DOCS_DIR') or os.path.join(_BASE_DIR, 'Project_document_data')
    
    # Project document storage (local vs S3)
    USE_S3_FOR_PROJECT_DOCS = os.environ.get('USE_S3_FOR_PROJECT_DOCS', 'false').lower() in ('true', '1', 'yes', 'y')
    S3_PROJECT_DOCS_BUCKET = os.environ.get('S3_PROJECT_DOCS_BUCKET')
    S3_PROJECT_DOCS_PREFIX = os.environ.get('S3_PROJECT_DOCS_PREFIX', '')
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.environ.get('AWS_REGION')
    
    # Security Settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', "memory://")
    RATELIMIT_STRATEGY = "fixed-window"
    
    # Only secure cookies if in production (using HTTPS)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

