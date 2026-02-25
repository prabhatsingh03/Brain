from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import os
import tempfile
from jinja2 import FileSystemBytecodeCache
from flask_compress import Compress
from config import Config, ensure_database_exists
from extensions import db, login_manager, csrf, limiter
from routes.auth import auth_bp
from routes.main import main_bp
from routes.admin import admin_bp
from models.user import User

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure database exists before initializing SQLAlchemy
    ensure_database_exists()

    # Initialize Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    csrf.init_app(app)
    limiter.init_app(app)
    Compress(app)

    # Configure Caching
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year for static files
    app.jinja_env.bytecode_cache = FileSystemBytecodeCache(directory=tempfile.gettempdir())

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Create Database Tables
    with app.app_context():
        db.create_all()

    # Add Security Headers
    # Serve Favicon
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static', 'images'),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.route('/.well-known/appspecific/com.chrome.devtools.json')
    def chrome_devtools():
        return jsonify({}), 200

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify(error="ratelimit exceeded", message=str(e.description)), 429

    @app.route('/test-marked')
    def test_marked():
        return send_from_directory(os.path.join(app.root_path, 'static'), 'reproduce_marked.html')

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    return app

if __name__ == '__main__':
    app = create_app()
    from waitress import serve
    print("Starting Waitress server on http://0.0.0.0:5000 (Multi-threaded)")
    serve(app, host='0.0.0.0', port=5000, threads=6)
