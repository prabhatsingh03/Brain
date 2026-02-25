from flask import Blueprint, render_template, request, jsonify, current_app, session, send_file, redirect, url_for, Response, stream_with_context
from flask_login import login_required, current_user
from models.project import Project, ProjectMetadata, ProjectDependency
from models.conversation import Conversation, ChatSession
from models.audit import AuditLog
from extensions import db, limiter
from services.qna_service import QnAService
from utils.security import sanitize_input, validate_file_path, validate_mode, validate_selected_files
import os
import io
import json
import secrets
import tempfile
import uuid
import threading
import time
import fitz # PyMuPDF
import bleach
from datetime import datetime
from collections import OrderedDict
import hashlib

from services.document_storage import get_document_storage

class LRUCache:
    def __init__(self, capacity=100):
        self.cache = OrderedDict()
        self.capacity = capacity
    def get(self, key):
        if key not in self.cache: return None
        self.cache.move_to_end(key)
        return self.cache[key]
    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

QNA_CACHE = LRUCache(capacity=200)

def get_qna_cache_key(project_name, question, primary_mode, advance_mode, selected_files, chat_history, related_projects, visual_intel):
    """Generates a unique cache key based on all inputs that affect the response."""
    key_data = {
        'p': project_name,
        'q': question,
        'm': primary_mode,
        'am': advance_mode,
        'f': list(selected_files) if selected_files else [],
        'h': [(str(q), str(a)) for q, a in chat_history] if chat_history else [],
        'rp': list(related_projects) if related_projects else [],
        'vi': visual_intel
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode('utf-8')).hexdigest()

main_bp = Blueprint('main', __name__)

# In-memory store for comparison uploads: upload_id -> {path, user_id, file_id?}
# Backend returns immediately; Gemini upload continues in background (previous flow)
COMPARISON_UPLOADS = {}


def _upload_comparison_to_gemini(upload_id: str, temp_path: str, app):
    """Background: upload temp file to Gemini and store file_id. Runs after response is sent."""
    with app.app_context():
        try:
            api_key = app.config.get('GEMINI_API_KEY')
            if api_key and temp_path and os.path.exists(temp_path):
                service = QnAService(api_key=api_key)
                file_id = service.upload_user_file_for_comparison(temp_path)
                if upload_id in COMPARISON_UPLOADS and COMPARISON_UPLOADS[upload_id].get('path') == temp_path:
                    COMPARISON_UPLOADS[upload_id]['file_id'] = file_id
                    COMPARISON_UPLOADS[upload_id]['path'] = None
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        except Exception as e:
            debug_logger.exception("Comparison background upload failed: %s", e)

import logging
import traceback

# Setup distinct file logger for debugging
debug_logger = logging.getLogger('debug_logger')
debug_logger.setLevel(logging.INFO)
if not debug_logger.handlers:
    fh = logging.FileHandler('sia_debug.log')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    debug_logger.addHandler(fh)
debug_logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('debug_errors.log')
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
debug_logger.addHandler(handler)

@main_bp.app_context_processor
def inject_recent_chats():
    recent_chats = []
    pinned_chats = []
    if current_user.is_authenticated:
        # Fetch Pinned Chats
        pinned_chats = Conversation.query.filter_by(user_id=current_user.id, is_pinned=True)\
            .order_by(Conversation.timestamp.desc()).all()
            
        # Fetch Last 20 Recent Chats (Unpinned)
        recent_chats = Conversation.query.filter_by(user_id=current_user.id, is_pinned=False)\
            .order_by(Conversation.timestamp.desc())\
            .limit(20).all()
            
    return dict(user_recent_chats=recent_chats, pinned_chats=pinned_chats)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.all()
    return render_template('dashboard.html', projects=projects, user=current_user)

@main_bp.route('/api/project/<project_name>/files')
@login_required
def project_files(project_name):
    project = Project.query.filter_by(name=project_name).first_or_404()
    metadata = ProjectMetadata.query.filter_by(project_id=project.id).all()
    
    files = []
    for m in metadata:
        files.append({
            'file_name': m.file_name,
            'type': m.type_of_data,
            'path': m.file_path
        })
    
    return jsonify({'files': files})


@main_bp.route('/project/<project_name>')
@login_required
def project_view(project_name):
    # Verify project exists
    project = Project.query.filter_by(name=project_name).first()
    if not project:
        return "Project not found", 404
        
    return render_template('search.html', project=project, user=current_user)

@main_bp.route('/visualization/dap-3d')
@login_required
def dap_3d_view():
    return render_template('dap_3d_view.html')

@main_bp.route('/api/visual')
@login_required
@limiter.exempt
def serve_visual():
    try:
        # Prefer the new stable visual identifier (?id=...) but continue to
        # support the legacy ?path=... parameter for backward compatibility.
        file_id = request.args.get('id')
        file_path = request.args.get('path') or file_id
        page_num = int(request.args.get('page', 0))

        if not file_path:
            return "File not found", 404

        # Authorisation: only allow serving documents that exist in ProjectMetadata
        meta = ProjectMetadata.query.filter_by(file_path=file_path).first()
        if not meta:
            current_app.logger.warning(f"Visual access denied: no ProjectMetadata record for file_path='{file_path}'")
            return ("Unauthorized file access", 403)

        storage = get_document_storage()

        # Audit Log for File Access
        try:
            log = AuditLog(
                user_id=current_user.email,
                action='VIEW_FILE',
                details=f"Accessed {meta.file_name} (Page {page_num})"
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Audit Log Failed: {e}")

        # Check if it's a PDF or Image. For S3 we may have only a key, so
        # derive the extension from the stored path or filename.
        ext = os.path.splitext(file_path)[1].lower() or os.path.splitext(meta.file_name)[1].lower()

        if ext == '.pdf':
            # Always operate on a local temporary path (works for both local and S3)
            local_path = storage.ensure_local_path(file_path, project_name=meta.project.name if meta.project else None)
            if not local_path or not os.path.exists(local_path):
                return "File not found", 404

            doc = fitz.open(local_path)
            if page_num < 0 or page_num >= len(doc):
                 return "Page out of range", 404
                 
            page = doc[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            return send_file(io.BytesIO(img_data), mimetype='image/png')

        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            # For images, we just serve the file itself if page_num is 0
            if page_num != 0:
                return "Only one page available for images", 404

            if storage.use_s3:
                data = storage.read_bytes(file_path)
                if data is None:
                    return "File not found", 404
                # Best-effort content type based on extension
                mime = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                }.get(ext, 'application/octet-stream')
                return send_file(io.BytesIO(data), mimetype=mime)
            else:
                abs_file_path = os.path.abspath(file_path)
                if not os.path.exists(abs_file_path):
                    return "File not found", 404
                return send_file(abs_file_path)
        
        else:
            # For other types (txt, etc), we don't have a visual representation.
            # We could return a placeholder or 404.
            return "No visual available for this file type", 404
            
    except Exception as e:
        current_app.logger.error(f"Visual Error: {e}")
        return f"Error serving visual: {str(e)}", 500

@main_bp.route('/api/chat/sessions/<project_name>')
@login_required
@limiter.exempt
def get_sessions(project_name):
    project = Project.query.filter_by(name=project_name).first_or_404()
    sessions = ChatSession.query.filter_by(user_id=current_user.id, project_id=project.id)\
        .order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc()).all()
    
    return jsonify([{
        'id': s.id,
        'title': s.title,
        'updated_at': s.updated_at.isoformat(),
        'is_pinned': s.is_pinned
    } for s in sessions])

@main_bp.route('/api/chat/session/<int:session_id>')
@login_required
def get_session_messages(session_id):
    session_obj = ChatSession.query.get_or_404(session_id)
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    messages = Conversation.query.filter_by(session_id=session_id)\
        .order_by(Conversation.timestamp.asc()).all()
    
    return jsonify({
        'session_title': session_obj.title,
        'messages': [{
            'id': m.id,
            'question': m.question,
            'answer': m.answer,
            'timestamp': m.timestamp.isoformat(),
            'is_pinned': m.is_pinned,
            'relevant_files': json.loads(m.relevant_files) if isinstance(m.relevant_files, str) else (m.relevant_files or []),
            'visuals': json.loads(m.visuals) if isinstance(m.visuals, str) else (m.visuals or [])
        } for m in messages]
    })

@main_bp.route('/api/chat/session/<int:session_id>/title', methods=['POST'])
@login_required
def update_session_title(session_id):
    session_obj = ChatSession.query.get_or_404(session_id)
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    new_title = data.get('title')
    if not new_title:
        return jsonify({'error': 'No title provided'}), 400
    
    session_obj.title = sanitize_input(new_title, max_length=100)
    db.session.commit()
    return jsonify({'success': True, 'title': session_obj.title})

@main_bp.route('/api/chat/session/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    session_obj = ChatSession.query.get_or_404(session_id)
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    db.session.delete(session_obj)
    db.session.commit()
    return jsonify({'success': True})


@main_bp.route('/api/chat/session/<int:session_id>/share', methods=['POST'])
@login_required
def create_share_link(session_id):
    session_obj = ChatSession.query.get_or_404(session_id)
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    session_obj.share_token = secrets.token_urlsafe(32)
    db.session.commit()
    share_url = request.host_url.rstrip('/') + url_for('main.shared_chat_view', token=session_obj.share_token)
    return jsonify({'share_url': share_url})


@main_bp.route('/api/chat/shared/<token>')
@limiter.limit("30 per minute")
def get_shared_session(token):
    session_obj = ChatSession.query.filter_by(share_token=token).first()
    if not session_obj:
        return jsonify({'error': 'Not found'}), 404
    messages = Conversation.query.filter_by(session_id=session_obj.id)\
        .order_by(Conversation.timestamp.asc()).all()
    return jsonify({
        'session_title': session_obj.title,
        'messages': [{
            'id': m.id,
            'question': m.question,
            'answer': m.answer,
            'timestamp': m.timestamp.isoformat(),
            'is_pinned': m.is_pinned,
            'relevant_files': json.loads(m.relevant_files) if isinstance(m.relevant_files, str) else (m.relevant_files or []),
            'visuals': json.loads(m.visuals) if isinstance(m.visuals, str) else (m.visuals or [])
        } for m in messages]
    })


@main_bp.route('/share/<token>')
@limiter.limit("30 per minute")
def shared_chat_view(token):
    session_obj = ChatSession.query.filter_by(share_token=token).first()
    if not session_obj:
        return render_template('shared_chat.html', token=None, invalid=True)
    return render_template('shared_chat.html', token=token, invalid=False)


@main_bp.route('/api/chat/<project_name>/upload-comparison', methods=['POST'])
@login_required
def upload_comparison(project_name):
    """Accept one file; return upload_id immediately. Previous flow (upload to Gemini) continues in background."""
    Project.query.filter_by(name=project_name).first_or_404()
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400
    allowed = ('.pdf', '.doc', '.docx', '.txt')
    if not file.filename.lower().endswith(allowed):
        return jsonify({'error': 'Allowed types: PDF, DOC, DOCX, TXT'}), 400
    fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(file.filename)[1])
    try:
        os.close(fd)
        file.save(temp_path)
        upload_id = str(uuid.uuid4())
        COMPARISON_UPLOADS[upload_id] = {'path': temp_path, 'user_id': current_user.id, 'file_id': None}
        # Continue previous flow in background: upload to Gemini
        thread = threading.Thread(
            target=_upload_comparison_to_gemini,
            args=(upload_id, temp_path, current_app._get_current_object()),
            daemon=True
        )
        thread.start()
        return jsonify({'upload_id': upload_id})
    except Exception as e:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/chat/<project_name>', methods=['POST'])
@login_required
def chat_api(project_name):
    data = request.json
    question = data.get('question')
    mode = data.get('mode', 'basic')
    advance_mode = data.get('advance_mode', 'none')
    selected_files = data.get('selected_files', [])
    session_id = data.get('session_id')
    visual_intel = data.get('visual_intel', True)
    
    # Input sanitization and validation
    try:
        # Sanitize question (remove HTML/script tags)
        question = sanitize_input(question, max_length=5000) if question else None
        
        # Validate mode against whitelist (align with Streamlit answer modes)
        allowed_modes = [
            'basic',
            'research',
            'analytical',
            'expert',
            'cross_project',  # only used when advance_mode == 'cross_project'
            'comparison',     # only used when advance_mode == 'comparison'
        ]
        if not validate_mode(mode, allowed_modes):
            return jsonify({'error': 'Invalid mode parameter'}), 400
        
        # Validate and sanitize selected files
        if selected_files:
            selected_files = validate_selected_files(selected_files)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        api_key = current_app.config.get('GEMINI_API_KEY')
        if not api_key:
             return jsonify({'error': 'Gemini API Key not configured'}), 500

        proj = Project.query.filter_by(name=project_name).first_or_404()
        
        # Handle Session
        if session_id:
            chat_session = ChatSession.query.get(session_id)
            if not chat_session or chat_session.user_id != current_user.id:
                return jsonify({'error': 'Invalid session'}), 403
        else:
            chat_session = ChatSession(user_id=current_user.id, project_id=proj.id)
            db.session.add(chat_session)
            db.session.flush() # Get ID without committing yet

        try:
            service = QnAService(api_key=api_key)
            
            # Fetch history for this session and convert to (question, answer) pairs
            history_msgs = Conversation.query.filter_by(session_id=chat_session.id)\
                .order_by(Conversation.timestamp.asc()).all()
            
            chat_history = [(m.question, m.answer) for m in history_msgs]

            # Determine related projects if cross‑project mode is enabled
            related_projects: list[str] = []
            if advance_mode == 'cross_project':
                deps = ProjectDependency.query.filter_by(project_name=proj.name).all()
                related_projects = [d.dependency_name for d in deps]
            
            cache_key = get_qna_cache_key(project_name, question, mode, advance_mode, selected_files, chat_history, related_projects, visual_intel)
            cached_result = QNA_CACHE.get(cache_key)

            if cached_result:
                debug_logger.info(f"QnA Cache HIT for chat_api: {cache_key}")
                result = cached_result
            else:
                debug_logger.info(f"QnA Cache MISS for chat_api: {cache_key}")
                # Comparison flow (explicit advanced mode)
                if advance_mode == 'comparison':
                    # Resolve upload:uuid to Gemini file_id (upload to Gemini when user sends question)
                    resolved_file_ids = []
                    for fid in (selected_files or []):
                        if fid.startswith('upload:'):
                            upload_id = fid[7:]
                            entry = COMPARISON_UPLOADS.get(upload_id)
                            if not entry or entry.get('user_id') != current_user.id:
                                continue
                            if entry.get('file_id'):
                                resolved_file_ids.append(entry['file_id'])
                                continue
                            # Background may still be uploading; wait briefly for file_id
                            for _ in range(30):
                                if entry.get('file_id'):
                                    resolved_file_ids.append(entry['file_id'])
                                    break
                                time.sleep(0.5)
                            else:
                                temp_path = entry.get('path')
                                if temp_path and os.path.exists(temp_path):
                                    gemini_file_id = service.upload_user_file_for_comparison(temp_path)
                                    if gemini_file_id:
                                        entry['file_id'] = gemini_file_id
                                        resolved_file_ids.append(gemini_file_id)
                                        try:
                                            os.remove(temp_path)
                                        except Exception:
                                            pass
                                        entry['path'] = None
                        else:
                            resolved_file_ids.append(fid)
                    result = service.generate_comparison_answer(
                        question=question,
                        project_name=project_name,
                        file_ids=resolved_file_ids,
                        extract_visuals=visual_intel
                    )
                # Cross‑project flow
                elif advance_mode == 'cross_project' and related_projects:
                    result = service.generate_cross_project_answer(
                        question=question,
                        parent_project=project_name,
                        related_projects=related_projects,
                        chat_history=chat_history,
                        style_mode=mode,  # preserve basic/research/analytical/expert style
                        extract_visuals=visual_intel
                    )
                else:
                    # Default single‑project flow
                    result = service.generate_single_project_answer(
                        question=question,
                        project_name=project_name,
                        chat_history=chat_history,
                        answer_mode=mode,
                        extract_visuals=visual_intel
                    )
                    
                # Save to cache
                if 'answer' in result:
                    QNA_CACHE.put(cache_key, result)
            
            answer = result.get('answer', 'No answer generated.')
            files = result.get('relevant_files', [])
            visuals = result.get('visuals', [])
            
            debug_logger.info(f"chat_api: Saving visuals={visuals}")
            # Save message to DB
            conv = Conversation(
                session_id=chat_session.id,
                project_id=proj.id,
                user_id=current_user.id,
                question=question,
                answer=answer,
            relevant_files=json.dumps(files),
            visuals=json.dumps(visuals)
            )
            db.session.add(conv)
            chat_session.updated_at = datetime.utcnow()
            
            # Auto-generate title if it's the first message (Gemini or full question fallback; DB max 255)
            if not history_msgs:
                try:
                    generated_title = service.generate_chat_title(question)
                    if generated_title:
                        chat_session.title = generated_title[:255]
                    else:
                        chat_session.title = question[:255]
                except Exception as title_err:
                    current_app.logger.error(f"Title Generation Error: {title_err}")
                    chat_session.title = question[:255]

            # Audit Log for Query
            log = AuditLog(
                user_id=current_user.email,
                action='QUERY',
                details=f"Project: {project_name} | Session: {chat_session.id} | Mode: {mode} | Q: {question[:100]}..."
            )
            db.session.add(log)
            
            db.session.commit()

            return jsonify({
                'answer': answer,
                'files': files,
                'visuals': visuals,
                'session_id': chat_session.id,
                'session_title': chat_session.title
            })
        except Exception as e:
            db.session.rollback()
            raise e
    except Exception as e:
        debug_logger.error(f"Chat Error: {e}")
        debug_logger.error(traceback.format_exc())
        current_app.logger.error(f"Chat Error: {e}")
        return jsonify({'error': str(e)}), 500


def _chat_stream_events(project_name, question, primary_mode, advance_mode, selected_files, session_id, service, chat_session, history_msgs, chat_history, proj, related_projects, visual_intel=True):
    """Generator that yields SSE event strings (data: {...}\\n\\n). Saves to DB on 'done' and adds session_id/session_title."""
    try:
        cache_key = get_qna_cache_key(project_name, question, primary_mode, advance_mode, selected_files, chat_history, related_projects, visual_intel)
        cached_result = QNA_CACHE.get(cache_key)
        
        if cached_result:
            debug_logger.info(f"QnA Cache HIT for chat_stream_api: {cache_key}")
            answer = cached_result.get('answer', '')
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
            conv = Conversation(
                session_id=chat_session.id, 
                project_id=proj.id, 
                user_id=current_user.id, 
                question=question, 
                answer=answer, 
                relevant_files=json.dumps(cached_result.get('relevant_files', [])), 
                visuals=json.dumps(cached_result.get('visuals', []))
            )
            db.session.add(conv)
            chat_session.updated_at = datetime.utcnow()
            if not history_msgs:
                try:
                    gt = service.generate_chat_title(question)
                    chat_session.title = (gt[:255] if gt else question[:255])
                except Exception:
                    chat_session.title = question[:255]
            db.session.add(AuditLog(user_id=current_user.email, action='QUERY', details=f"Project: {project_name} | Session: {chat_session.id} | Mode: {primary_mode} | Q: {question[:100]}..."))
            db.session.commit()
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'relevant_files': cached_result.get('relevant_files', []), 'visuals': cached_result.get('visuals', []), 'session_id': chat_session.id, 'session_title': chat_session.title})}\n\n"
            return
            
        debug_logger.info(f"QnA Cache MISS for chat_stream_api: {cache_key}")

        if advance_mode == 'comparison':
            resolved_file_ids = []
            for fid in (selected_files or []):
                if fid.startswith('upload:'):
                    upload_id = fid[7:]
                    entry = COMPARISON_UPLOADS.get(upload_id)
                    if not entry or entry.get('user_id') != current_user.id:
                        continue
                    if entry.get('file_id'):
                        resolved_file_ids.append(entry['file_id'])
                        continue
                    for _ in range(30):
                        if entry.get('file_id'):
                            resolved_file_ids.append(entry['file_id'])
                            break
                        time.sleep(0.5)
                    else:
                        temp_path = entry.get('path')
                        if temp_path and os.path.exists(temp_path):
                            gemini_file_id = service.upload_user_file_for_comparison(temp_path)
                            if gemini_file_id:
                                entry['file_id'] = gemini_file_id
                                resolved_file_ids.append(gemini_file_id)
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                                entry['path'] = None
                else:
                    resolved_file_ids.append(fid)
            result = service.generate_comparison_answer(
                question=question,
                project_name=project_name,
                file_ids=resolved_file_ids
            )
            if 'answer' in result:
                QNA_CACHE.put(cache_key, result)
            answer = result.get('answer', '')
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
            # Save to DB before sending done (so session_title can be set)
            conv = Conversation(
                session_id=chat_session.id, 
                project_id=proj.id, 
                user_id=current_user.id, 
                question=question, 
                answer=answer, 
                relevant_files=json.dumps(result.get('relevant_files', [])), 
                visuals=json.dumps(result.get('visuals', []))
            )
            db.session.add(conv)
            chat_session.updated_at = datetime.utcnow()
            if not history_msgs:
                try:
                    gt = service.generate_chat_title(question)
                    chat_session.title = (gt[:255] if gt else question[:255])
                except Exception:
                    chat_session.title = question[:255]
            db.session.add(AuditLog(user_id=current_user.email, action='QUERY', details=f"Project: {project_name} | Session: {chat_session.id} | Mode: {primary_mode} | Q: {question[:100]}..."))
            db.session.commit()
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'relevant_files': result.get('relevant_files', []), 'visuals': result.get('visuals', []), 'session_id': chat_session.id, 'session_title': chat_session.title})}\n\n"
        elif advance_mode == 'cross_project' and related_projects:
            result = service.generate_cross_project_answer(
                question=question,
                parent_project=project_name,
                related_projects=related_projects,
                chat_history=chat_history,
                style_mode=primary_mode,
            )
            if 'answer' in result:
                QNA_CACHE.put(cache_key, result)
            answer = result.get('answer', '')
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
            conv = Conversation(
                session_id=chat_session.id, 
                project_id=proj.id, 
                user_id=current_user.id, 
                question=question, 
                answer=answer, 
                relevant_files=json.dumps(result.get('relevant_files', [])), 
                visuals=json.dumps(result.get('visuals', []))
            )
            db.session.add(conv)
            chat_session.updated_at = datetime.utcnow()
            if not history_msgs:
                try:
                    gt = service.generate_chat_title(question)
                    chat_session.title = (gt[:255] if gt else question[:255])
                except Exception:
                    chat_session.title = question[:255]
            db.session.add(AuditLog(user_id=current_user.email, action='QUERY', details=f"Project: {project_name} | Session: {chat_session.id} | Mode: {primary_mode} | Q: {question[:100]}..."))
            db.session.commit()
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'relevant_files': result.get('relevant_files', []), 'visuals': result.get('visuals', []), 'session_id': chat_session.id, 'session_title': chat_session.title})}\n\n"
        else:
            done_ev = None
            for ev in service.generate_single_project_answer_stream(
                question=question,
                project_name=project_name,
                chat_history=chat_history,
                answer_mode=primary_mode,
                extract_visuals=visual_intel
            ):
                if ev.get('type') == 'chunk':
                    yield f"data: {json.dumps(ev)}\n\n"
                else:
                    done_ev = ev
                    break
            if done_ev is None:
                return
            if 'answer' in done_ev:
                QNA_CACHE.put(cache_key, done_ev)
            debug_logger.info(f"stream: Saving done_ev={done_ev}")
            answer = done_ev.get('answer', '')
            debug_logger.info(f"DEBUG: creating Conversation with visuals={done_ev.get('visuals')}")
            conv = Conversation(
                session_id=chat_session.id, 
                project_id=proj.id, 
                user_id=current_user.id, 
                question=question, 
                answer=answer, 
                relevant_files=json.dumps(done_ev.get('relevant_files', [])), 
                visuals=json.dumps(done_ev.get('visuals', []))
            )
            db.session.add(conv)
            chat_session.updated_at = datetime.utcnow()
            if not history_msgs:
                try:
                    gt = service.generate_chat_title(question)
                    chat_session.title = (gt[:255] if gt else question[:255])
                except Exception:
                    chat_session.title = question[:255]
            db.session.add(AuditLog(user_id=current_user.email, action='QUERY', details=f"Project: {project_name} | Session: {chat_session.id} | Mode: {primary_mode} | Q: {question[:100]}..."))
            db.session.commit()
            done_ev['session_id'] = chat_session.id
            done_ev['session_title'] = chat_session.title
            yield f"data: {json.dumps(done_ev)}\n\n"
    except Exception as e:
        debug_logger.error(f"Chat stream error: {e}")
        debug_logger.error(traceback.format_exc())
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@main_bp.route('/api/chat/<project_name>/stream', methods=['POST'])
@login_required
def chat_stream_api(project_name):
    """Streaming chat: yields SSE events (chunk then done with session_id/session_title)."""
    data = request.json
    question = data.get('question')
    primary_mode = data.get('mode', 'basic')
    advance_mode = data.get('advance_mode', 'none')
    selected_files = data.get('selected_files', [])
    session_id = data.get('session_id')
    visual_intel = data.get('visual_intel', True)

    try:
        question = sanitize_input(question, max_length=5000) if question else None
        allowed_modes = ['basic', 'research', 'analytical', 'expert', 'cross_project', 'comparison']
        if not validate_mode(primary_mode, allowed_modes):
            return jsonify({'error': 'Invalid mode parameter'}), 400
        if selected_files:
            selected_files = validate_selected_files(selected_files)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'Gemini API Key not configured'}), 500

    proj = Project.query.filter_by(name=project_name).first_or_404()
    if session_id:
        chat_session = ChatSession.query.get(session_id)
        if not chat_session or chat_session.user_id != current_user.id:
            return jsonify({'error': 'Invalid session'}), 403
    else:
        chat_session = ChatSession(user_id=current_user.id, project_id=proj.id)
        db.session.add(chat_session)
        db.session.flush()

    history_msgs = Conversation.query.filter_by(session_id=chat_session.id).order_by(Conversation.timestamp.asc()).all()
    chat_history = [(m.question, m.answer) for m in history_msgs]
    related_projects = []
    if advance_mode == 'cross_project':
        deps = ProjectDependency.query.filter_by(project_name=proj.name).all()
        related_projects = [d.dependency_name for d in deps]

    service = QnAService(api_key=api_key)

    return Response(
        stream_with_context(_chat_stream_events(
            project_name, question, primary_mode, advance_mode, selected_files, session_id,
            service, chat_session, history_msgs, chat_history, proj, related_projects, visual_intel
        )),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@main_bp.route('/api/chat/session/<int:session_id>/pin', methods=['POST'])
@login_required
def toggle_session_pin(session_id):
    session_obj = ChatSession.query.get_or_404(session_id)
    if session_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    session_obj.is_pinned = not session_obj.is_pinned
    db.session.commit()
    return jsonify({'success': True, 'is_pinned': session_obj.is_pinned})

@main_bp.route('/api/user/theme', methods=['GET', 'POST'])
@login_required
@limiter.exempt
def user_theme():
    if request.method == 'POST':
        data = request.get_json()
        theme = data.get('theme')
        # Validate input
        if theme in ['light', 'dark']:
            current_user.theme_preference = theme
            db.session.commit()
            return jsonify({'success': True, 'theme': theme})
        return jsonify({'error': 'Invalid theme value. Must be "light" or "dark".'}), 400
    
    return jsonify({'theme': current_user.theme_preference or 'dark'})
    

