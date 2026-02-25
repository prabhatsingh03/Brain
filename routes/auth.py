from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models.user import User
from extensions import db, limiter, csrf
from flask_limiter import RateLimitExceeded
from flask_wtf.csrf import CSRFError

auth_bp = Blueprint('auth', __name__)

@auth_bp.errorhandler(RateLimitExceeded)
def handle_rate_limit_exceeded(e):
    return jsonify({
        'success': False,
        'message': 'Too many requests. Please try again later.',
        'retry_after': e.description
    }), 429

@auth_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({
        'success': False,
        'message': 'CSRF token missing or invalid. Please refresh and try again.'
    }), 403

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'success': True, 'redirect_url': url_for('main.dashboard')})
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        # Get credentials from JSON or Form
        if request.is_json:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            email = request.form.get('email')
            password = request.form.get('password')
            
        if not email or not email.endswith('@adventz.com'):
            error_msg = 'Access restricted to @adventz.com emails only.'
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg})
            flash(error_msg, 'danger')
            return redirect(url_for('main.index'))
                
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember') == 'on')
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'redirect_url': url_for('main.dashboard')})
            return redirect(url_for('main.dashboard'))
        else:
            error_msg = 'Invalid email or password.'
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg})
            flash(error_msg, 'danger')
            return redirect(url_for('main.index'))
            
    # GET request redirects to landing page (where modal exists)
    return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("3 per hour")
@limiter.limit("10 per day")
def register():
    email = None
    password = None
    confirm_password = None
    username = None

    if request.is_json:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        username = data.get('username')
    else:
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        username = request.form.get('username')

    if not email or not email.endswith('@adventz.com'):
        error_msg = 'Registration restricted to @adventz.com emails only.'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg})
        flash(error_msg, 'danger')
        return redirect(url_for('main.index'))
        
    if password != confirm_password:
        error_msg = 'Passwords do not match.'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg})
        flash(error_msg, 'danger')
        return redirect(url_for('main.index'))

    # Check if user already exists
    user = User.query.filter_by(email=email).first()
    if user:
        error_msg = 'User already exists.'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg})
        flash(error_msg, 'danger')
        return redirect(url_for('main.index'))
        
    new_user = User(email=email)
    new_user.set_password(password)
    # If username is needed in model, add it here. Currently User model doesn't have it.
    db.session.add(new_user)
    db.session.commit()
    
    success_msg = 'Registration successful. Please log in.'
    if request.is_json:
        return jsonify({'success': True, 'message': success_msg})
    flash(success_msg, 'success')
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
