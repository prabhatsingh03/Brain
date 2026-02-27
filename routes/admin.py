from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, jsonify
from flask_login import login_required, current_user
from models.project import Project, ProjectMetadata, ProjectDependency
from models.user import User
from models.audit import AuditLog
from extensions import db, csrf
from flask_wtf.csrf import CSRFError
import os
import werkzeug.utils
import io
import tempfile

from services.document_storage import get_document_storage
from services.gemini_service import GeminiService

admin_bp = Blueprint('admin', __name__)


def initialize_project_filesystem(process_name: str) -> None:
    """
    Mirror the folder and file initialisation performed by the original
    Streamlit project_creator script so that all legacy paths continue
    to work (process_metadata, process_file_cache_detail, etc.).
    """
    try:
        base_root = os.path.abspath(os.path.join(current_app.root_path, '..'))

        # Core folders (aligned with old_code: project_document_data lowercase)
        folders = {
            "process_metadata": os.path.join(base_root, "process_metadata", process_name),
            "process_file_cache_detail": os.path.join(base_root, "process_file_cache_detail", process_name),
            "past_conversation": os.path.join(base_root, "past_conversation", process_name),
        }

        # Only create local project_document_data folder when not using S3 for project docs
        if not current_app.config.get("USE_S3_FOR_PROJECT_DOCS"):
            folders["project_document_data"] = os.path.join(base_root, "project_document_data", process_name)

        for path in folders.values():
            os.makedirs(path, exist_ok=True)
    except Exception as e:
        current_app.logger.error(f"Failed to initialise filesystem for process {process_name}: {e}")

@admin_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('CSRF token missing or invalid. Please try again.', 'danger')
    return redirect(url_for('admin.index'))

@admin_bp.before_request
def admin_only():
    # Enforce authentication and admin role
    if not current_user.is_authenticated or current_user.role != 'admin':
        # Log failed admin access attempts
        try:
            user_email = current_user.email if current_user.is_authenticated else 'Anonymous'
            log = AuditLog(
                user_id=user_email,
                action='ADMIN_ACCESS_ATTEMPT',
                details=f"Failed admin access - User role: {getattr(current_user, 'role', 'None')}"
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Audit Log Failed: {e}")
        
        return "Access Denied", 403
    
    # Log successful admin access
    try:
        log = AuditLog(
            user_id=current_user.email,
            action='ADMIN_ACCESS_ATTEMPT',
            details=f"Successful admin access to {request.endpoint}"
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Audit Log Failed: {e}")

@admin_bp.route('/')
def index():
    projects = Project.query.all()
    metadata = ProjectMetadata.query.all()
    users = User.query.all()
    return render_template(
        'admin/admin_dashboard.html',
        projects=projects,
        metadata=metadata,
        users=users,
        ProjectDependency=ProjectDependency,
    )

@admin_bp.route('/project/add', methods=['POST'])
def add_project():
    name = request.form.get('name')
    description = request.form.get('description', '')
    if name:
        try:
            upper_name = name.upper()

            # Prevent duplicate projects
            existing = Project.query.filter_by(name=upper_name).first()
            if existing:
                flash(f'Project {upper_name} already exists.', 'danger')
                return redirect(url_for('admin.index'))

            p = Project(name=upper_name, description=description)
            db.session.add(p)
            db.session.commit()

            # Mirror legacy filesystem initialisation (folders + CSV/JSON)
            initialize_project_filesystem(upper_name)

            flash('Project added.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
    return redirect(url_for('admin.index'))


@admin_bp.route('/project/<int:id>/edit')
def edit_project(id):
    """
    Render a simple edit form for updating a project's
    name (kept uppercase) and description.
    """
    project = Project.query.get_or_404(id)
    return render_template('admin/project_edit.html', project=project)


@admin_bp.route('/project/<int:id>/update', methods=['POST'])
def update_project(id):
    """
    Handle updates to a project's name and description.
    """
    project = Project.query.get_or_404(id)
    new_name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not new_name:
        flash('Project name is required.', 'danger')
        return redirect(url_for('admin.edit_project', id=project.id))

    upper_name = new_name.upper()

    # Prevent renaming to an existing project's name
    existing = Project.query.filter(Project.id != project.id, Project.name == upper_name).first()
    if existing:
        flash(f'Another project with name {upper_name} already exists.', 'danger')
        return redirect(url_for('admin.edit_project', id=project.id))

    try:
        old_name = project.name
        project.name = upper_name
        project.description = description
        db.session.commit()
        flash('Project updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating project: {e}', 'danger')

    return redirect(url_for('admin.index'))


@admin_bp.route('/project/<int:id>/delete', methods=['POST'])
def delete_project(id):
    """
    Delete a project from the admin console, along with its metadata and
    dependency mappings. Any underlying files on disk referenced by
    ProjectMetadata.file_path are also removed if they exist.
    """
    proj = Project.query.get_or_404(id)

    try:
        storage = get_document_storage()

        # Delete all metadata rows (and underlying files or S3 objects) for this project
        metas = ProjectMetadata.query.filter_by(project_id=proj.id).all()
        for meta in metas:
            if meta.file_path:
                storage.delete(meta.file_path)
            db.session.delete(meta)

        # Remove dependency mappings where this project is the source
        ProjectDependency.query.filter_by(project_name=proj.name).delete()

        # Finally delete the project itself
        db.session.delete(proj)
        db.session.commit()
        flash(f'Project {proj.name} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting project: {e}', 'danger')

    return redirect(url_for('admin.index'))

def _is_pdf(filename: str) -> bool:
    """Allow only PDFs, matching old_code metadata_admin_panel."""
    return bool(filename) and filename.lower().endswith('.pdf')


@admin_bp.route('/generate-description', methods=['POST'])
def generate_description():
    """
    Generate a short AI description for an uploaded PDF.
    Returns JSON with a `description` field based strictly on the document content.
    """
    file = request.files.get('file')
    content_length = request.content_length or 0

    if not file or not file.filename:
        return jsonify({'error': 'Please choose a PDF file before generating a description.'}), 400

    if not _is_pdf(file.filename):
        return jsonify({'error': 'Only PDF files are allowed for description generation.'}), 400

    max_bytes = 50 * 1024 * 1024
    if content_length > max_bytes:
        return jsonify({'error': 'File is too large. Maximum allowed size is 50 MB.'}), 400

    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'Gemini API Key not configured.'}), 500

    fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(file.filename)[1])
    try:
        os.close(fd)
        file.save(temp_path)

        service = GeminiService(api_key=api_key)
        description = service.generate_document_description(temp_path, max_words=50)

        if not description:
            return jsonify({'error': 'Failed to generate description from the document.'}), 500

        return jsonify({'description': description})
    except Exception as e:
        current_app.logger.error(f"Error generating document description: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred while generating the description.'}), 500
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as cleanup_error:
            current_app.logger.warning(f"Failed to remove temporary file {temp_path}: {cleanup_error}")


@admin_bp.route('/upload', methods=['POST'])
def upload_metadata():
    project_id = request.form.get('project_id')
    type_of_data = request.form.get('type_of_data')
    file = request.files.get('file')
    content_length = request.content_length or 0

    if not file or not file.filename:
        flash('Please choose a PDF file before submitting.', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))
    if not _is_pdf(file.filename):
        flash('Only PDF files are allowed.', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))
    # Explicit server-side size check (matches global 50 MB limit)
    max_bytes = 50 * 1024 * 1024
    if content_length > max_bytes:
        flash('File is too large. Maximum allowed size is 50 MB.', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))
    if not project_id:
        flash('Project is required.', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))

    filename = werkzeug.utils.secure_filename(file.filename)
    proj = Project.query.get(project_id)
    if not proj:
        flash('Invalid project.', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))

    storage = get_document_storage()
    storage_id = storage.build_storage_id(proj.name, filename)

    # Prevent accidental overwrite of an existing file
    if storage.exists(storage_id):
        flash('A file with the same name already exists for this project. Please rename and try again.', 'danger')
        return redirect(url_for('admin.index'))

    # Save via storage abstraction (local or S3)
    final_storage_id = storage.save_pdf(proj.name, filename, file)

    # Add to DB
    meta = ProjectMetadata(
        project_id=project_id,
        file_name=filename,
        # In local mode this is an absolute path; in S3 mode this is an S3 object key
        file_path=final_storage_id,
        type_of_data=type_of_data
    )
    db.session.add(meta)
    db.session.commit()

    flash('File uploaded and indexed.', 'success')
    return redirect(url_for('admin.index', _anchor='metadata'))

@admin_bp.route('/metadata/delete/<int:id>', methods=['POST'])
def delete_metadata(id):
    meta = ProjectMetadata.query.get_or_404(id)
    try:
        project = meta.project

        # Delete file from storage (local or S3)
        storage = get_document_storage()
        storage.delete(meta.file_path)
        
        # Delete from DB
        db.session.delete(meta)
        db.session.commit()

        flash('File deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting file: {e}', 'danger')
    
    return redirect(url_for('admin.index', _anchor='metadata'))

@admin_bp.route('/metadata/download/<int:id>')
def download_metadata(id):
    meta = ProjectMetadata.query.get_or_404(id)
    try:
        storage = get_document_storage()

        # Local filesystem: stream directly from disk
        if not storage.use_s3:
            return send_file(meta.file_path, as_attachment=True, download_name=meta.file_name)

        # S3 mode: stream bytes from S3
        data = storage.read_bytes(meta.file_path)
        if data is None:
            flash('File not found in storage.', 'danger')
            return redirect(url_for('admin.index', _anchor='metadata'))

        return send_file(
            io.BytesIO(data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=meta.file_name
        )
    except Exception as e:
        flash(f'Error downloading file: {e}', 'danger')
        return redirect(url_for('admin.index', _anchor='metadata'))


@admin_bp.route('/metadata/edit/<int:id>')
def edit_metadata(id):
    """
    Render a focused metadata edit view for a single record,
    matching the behaviour of the Streamlit 'Update Metadata' tab.
    """
    meta = ProjectMetadata.query.get_or_404(id)
    return render_template('admin/metadata_edit.html', meta=meta)


@admin_bp.route('/metadata/update/<int:id>', methods=['POST'])
def update_metadata(id):
    """
    Update metadata fields and optionally replace the underlying file.
    """
    meta = ProjectMetadata.query.get_or_404(id)
    project = meta.project

    type_of_data = request.form.get('type_of_data', meta.type_of_data)
    file = request.files.get('file')

    try:
        # Handle optional file replacement
        if file and file.filename:
            filename = werkzeug.utils.secure_filename(file.filename)

            storage = get_document_storage()
            new_storage_id = storage.build_storage_id(project.name, filename)

            # Block overwriting a different existing file
            if storage.exists(new_storage_id) and os.path.abspath(str(new_storage_id)) != os.path.abspath(str(meta.file_path)):
                flash('A file with this name already exists for this project. Please rename and try again.', 'danger')
                return redirect(url_for('admin.edit_metadata', id=meta.id))

            # Only PDF allowed (same as old_code)
            if not _is_pdf(filename):
                flash('Only PDF files are allowed.', 'danger')
                return redirect(url_for('admin.edit_metadata', id=meta.id))

            # Remove old file if it exists and path is different
            if meta.file_path and os.path.abspath(str(meta.file_path)) != os.path.abspath(str(new_storage_id)):
                try:
                    storage.delete(meta.file_path)
                except Exception as e:
                    current_app.logger.error(f"Failed to remove old metadata file {meta.file_path}: {e}")

            # Save new file via storage abstraction
            final_storage_id = storage.save_pdf(project.name, filename, file)
            meta.file_name = filename
            meta.file_path = final_storage_id

        # Update metadata fields
        meta.type_of_data = type_of_data

        db.session.commit()
        flash('Metadata updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating metadata: {e}', 'danger')

    return redirect(url_for('admin.index', _anchor='metadata'))

# User Management Routes
@admin_bp.route('/user/add', methods=['POST'])
def add_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    
    if not email or not password:
        flash('Email and password are required.', 'danger')
        return redirect(url_for('admin.index', _anchor='users'))
    
    # Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash(f'User with email {email} already exists.', 'danger')
        return redirect(url_for('admin.index', _anchor='users'))
    
    try:
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User {email} created successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating user: {e}', 'danger')
    
    return redirect(url_for('admin.index', _anchor='users'))

@admin_bp.route('/user/<int:id>/update-role', methods=['POST'])
def update_user_role(id):
    user = User.query.get_or_404(id)
    new_role = request.form.get('role')
    
    if new_role not in ['user', 'admin']:
        flash('Invalid role specified.', 'danger')
        return redirect(url_for('admin.index', _anchor='users'))
    
    try:
        user.role = new_role
        db.session.commit()
        flash(f'User {user.email} role updated to {new_role}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating role: {e}', 'danger')
    
    return redirect(url_for('admin.index', _anchor='users'))

@admin_bp.route('/user/<int:id>/delete', methods=['POST'])
def delete_user(id):
    # Prevent self-deletion
    if current_user.id == id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.index', _anchor='users'))
    
    user = User.query.get_or_404(id)
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.email} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {e}', 'danger')
    
    return redirect(url_for('admin.index', _anchor='users'))


@admin_bp.route('/dependencies/update', methods=['POST'])
def update_dependencies():
    """
    Update dependency list for an existing project.
    """
    project_name = request.form.get('project_name')
    dependencies = request.form.getlist('dependencies')  # multiple select

    if not project_name:
        flash('Project name is required to update dependencies.', 'danger')
        return redirect(url_for('admin.index', _anchor='dependencies'))

    try:
        # Remove existing dependencies for this project
        from models.project import ProjectDependency  # local import to avoid circulars at module import time
        ProjectDependency.query.filter_by(project_name=project_name).delete()

        # Insert new ones
        for dep in dependencies:
            if dep and dep != project_name:
                db.session.add(ProjectDependency(project_name=project_name, dependency_name=dep))

        db.session.commit()
        flash(f'Dependencies updated for {project_name}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating dependencies: {e}', 'danger')

    return redirect(url_for('admin.index', _anchor='dependencies'))


@admin_bp.route('/dependencies/create', methods=['POST'])
def create_dependencies():
    """
    Create an initial dependency mapping for a project that does not yet have one.
    """
    project_name = request.form.get('new_project_name')
    dependencies = request.form.getlist('new_dependencies')

    if not project_name:
        flash('Project name is required to create dependencies.', 'danger')
        return redirect(url_for('admin.index', _anchor='dependencies'))

    try:
        from models.project import ProjectDependency  # local import to avoid circulars at module import time

        # Only add if there is not already a mapping row
        existing = ProjectDependency.query.filter_by(project_name=project_name).first()
        if existing:
            flash(f'Dependencies already exist for {project_name}. Use Update instead.', 'danger')
            return redirect(url_for('admin.index', _anchor='dependencies'))

        for dep in dependencies:
            if dep and dep != project_name:
                db.session.add(ProjectDependency(project_name=project_name, dependency_name=dep))

        db.session.commit()
        flash(f'Dependencies created for {project_name}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating dependencies: {e}', 'danger')

    return redirect(url_for('admin.index', _anchor='dependencies'))


