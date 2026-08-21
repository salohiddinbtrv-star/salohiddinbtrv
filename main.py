import os

IS_RENDER = os.environ.get("RENDER") is not None

if IS_RENDER:
    import eventlet
    eventlet.monkey_patch()

import base64
import logging
import itertools
from datetime import datetime, timedelta
from functools import wraps
from collections import deque

from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("notfic")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "notfic_secret_key_123")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-20b")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "notfic_admin_2026")
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
AI_NAME = "Notfic AI ⚡"
AI_TRIGGER = "@ai"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

ANONYMOUS_MESSAGE_LIMIT = 10

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_AVATAR_SIZE = 2 * 1024 * 1024

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///notfic.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY topilmadi!")
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.warning("Google OAuth sozlanmagan!")
if not ADMIN_EMAIL:
    logger.warning("ADMIN_EMAIL sozlanmagan!")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db = SQLAlchemy(app)

async_mode = 'eventlet' if IS_RENDER else 'threading'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

ai_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

SYSTEM_PROMPT = (
    "Sening isming Notfic AI. Sen Notfic platformasining aqlli yordamchisisan. "
    "Do'stona, qisqa, tushunarli va aqlli javob ber."
)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(150))
    avatar = db.Column(db.String(500))
    custom_avatar = db.Column(db.Text, nullable=True)
    bio = db.Column(db.String(300), default='')
    is_banned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FriendRequest(db.Model):
    __tablename__ = 'friend_requests'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DirectMessage(db.Model):
    __tablename__ = 'direct_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text)
    reaction = db.Column(db.String(8), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GroupMember(db.Model):
    __tablename__ = 'group_members'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class GroupMessage(db.Model):
    __tablename__ = 'group_messages'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_ai = db.Column(db.Boolean, default=False)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(150))
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AIFeedback(db.Model):
    __tablename__ = 'ai_feedback'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    prompt = db.Column(db.Text)
    response = db.Column(db.Text)
    rating = db.Column(db.Integer)  # 1 = yoqdi, -1 = yoqmadi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserAIPreference(db.Model):
    __tablename__ = 'user_ai_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    likes_count = db.Column(db.Integer, default=0)
    dislikes_count = db.Column(db.Integer, default=0)
    avg_liked_length = db.Column(db.Float, default=0.0)
    avg_disliked_length = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_log'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100))
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


SERVER_START_TIME = datetime.utcnow()
connected_sids = set()
stats = {
    "total_public_messages": 0,
    "total_ai_messages": 0,
    "total_connections": 0,
}
public_history = deque(maxlen=200)
public_msg_counter = itertools.count(1)

anonymous_message_counts = {}
online_user_counts = {}

admin_login_attempts = {}
ADMIN_LOGIN_MAX_ATTEMPTS = 5
ADMIN_LOGIN_LOCKOUT_MINUTES = 15


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def log_admin_action(action, detail=""):
    entry = AdminAuditLog(action=action, detail=detail)
    db.session.add(entry)
    db.session.commit()


def dangerous_action(action_name):
    """Xavfli amallar uchun: admin paroli qayta so'raladi va amal audit jurnaliga yoziladi."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            data = request.get_json() or {}
            confirm_password = data.get('confirm_password', '')
            if confirm_password != ADMIN_PASSWORD:
                logger.warning(f"Xavfli amalga notogri parol bilan urinish: {action_name} (IP: {get_client_ip()})")
                return jsonify({"error": "confirm_password_required"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def get_user_ai_style_notes(user):
    """Foydalanuvchining reyting tarixi asosida AI uslubini moslashtirish uchun qisqa yordamchi matn hosil qiladi."""
    if not user:
        return ""

    pref = UserAIPreference.query.filter_by(user_id=user.id).first()
    if not pref or (pref.likes_count + pref.dislikes_count) < 3:
        return ""

    notes = []
    if pref.avg_liked_length and pref.avg_disliked_length:
        if pref.avg_liked_length < pref.avg_disliked_length * 0.7:
            notes.append("Bu foydalanuvchi qisqa va lo'nda javoblarni afzal koradi.")
        elif pref.avg_liked_length > pref.avg_disliked_length * 1.3:
            notes.append("Bu foydalanuvchi batafsil va toliq javoblarni afzal koradi.")

    if not notes:
        return ""

    return "Foydalanuvchi haqida: " + " ".join(notes)


def get_ai_response(prompt: str, context=None, user=None, extra_system_note=None) -> str:
    if not ai_client:
        return f"🤖 [{AI_NAME}]: Hozircha AI ulanmagan — server tomonida API kalit sozlanmagan."

    if not prompt or not prompt.strip():
        return f"🤖 [{AI_NAME}]: Savolingizni yozing, men yordam berishga tayyorman!"

    style_notes = get_user_ai_style_notes(user)
    system_content = SYSTEM_PROMPT
    if style_notes:
        system_content += " " + style_notes
    if extra_system_note:
        system_content += " " + extra_system_note

    messages = [{"role": "system", "content": system_content}]

    if context:
        for item in context[-14:]:
            role = "assistant" if item.get("isAI") else "user"
            text = (item.get("message") or "").strip()
            if text:
                messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": prompt.strip()})

    try:
        completion = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )
        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"Groq AI xatosi: {e}")
        return f"🤖 [{AI_NAME}]: Hozir javob bera olmadim, birozdan so'ng qayta urinib ko'ring."


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def get_display_avatar(user):
    if not user:
        return None
    if user.custom_avatar:
        return user.custom_avatar
    return user.avatar


def is_admin_user(user):
    if not user or not ADMIN_EMAIL:
        return False
    return (user.email or '').strip().lower() == ADMIN_EMAIL


def session_is_admin():
    if session.get('is_admin'):
        return True
    return is_admin_user(current_user())


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session_is_admin():
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def login_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "login_required"}), 401
        return f(*args, **kwargs)
    return decorated


def are_friends(user_id_a, user_id_b):
    return FriendRequest.query.filter(
        db.or_(
            db.and_(FriendRequest.sender_id == user_id_a, FriendRequest.receiver_id == user_id_b),
            db.and_(FriendRequest.sender_id == user_id_b, FriendRequest.receiver_id == user_id_a)
        ),
        FriendRequest.status == 'accepted'
    ).first() is not None


def get_friendship_row(user_id_a, user_id_b):
    return FriendRequest.query.filter(
        db.or_(
            db.and_(FriendRequest.sender_id == user_id_a, FriendRequest.receiver_id == user_id_b),
            db.and_(FriendRequest.sender_id == user_id_b, FriendRequest.receiver_id == user_id_a)
        ),
        FriendRequest.status == 'accepted'
    ).first()


def is_group_member(group_id, user_id):
    return GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first() is not None


def get_group_ids_for_user(user_id):
    return [m.group_id for m in GroupMember.query.filter_by(user_id=user_id).all()]


@app.route('/')
def index():
    user = current_user()
    display_avatar = get_display_avatar(user) if user else None
    is_admin = is_admin_user(user)
    return render_template('index.html', user=user, display_avatar=display_avatar,
                            anon_limit=ANONYMOUS_MESSAGE_LIMIT, is_admin=is_admin)


@app.route('/health')
def health():
    uptime_seconds = int((datetime.utcnow() - SERVER_START_TIME).total_seconds())
    return {
        "status": "ok",
        "ai_connected": ai_client is not None,
        "uptime_seconds": uptime_seconds
    }, 200


@app.route('/robots.txt')
def robots_txt():
    content = "User-agent: *\nAllow: /\nSitemap: " + request.url_root.rstrip('/') + "/sitemap.xml\n"
    return app.response_class(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    base = request.url_root.rstrip('/')
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{base}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        '</urlset>\n'
    )
    return app.response_class(content, mimetype='application/xml')


@app.route('/auth/google/login')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')

    if not user_info:
        return redirect(url_for('index'))

    google_id = user_info.get('sub')
    name = user_info.get('name', 'Foydalanuvchi')
    email = user_info.get('email', '')
    avatar = user_info.get('picture', '')

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User(google_id=google_id, name=name, email=email, avatar=avatar)
        db.session.add(user)
    else:
        user.name = name
        user.email = email
        user.avatar = avatar

    db.session.commit()

    if user.is_banned:
        return redirect(url_for('banned_page'))

    session['user_id'] = user.id
    session.permanent = True

    logger.info(f"Foydalanuvchi kirdi: {name} ({email})")
    return redirect(url_for('index'))


@app.route('/banned')
def banned_page():
    return "Sizning hisobingiz bloklangan. Savollar bo'lsa, administratorga murojaat qiling.", 403


@app.route('/auth/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))


@app.route('/api/profile', methods=['GET'])
def api_get_profile():
    user = current_user()
    if not user:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar": get_display_avatar(user),
        "bio": user.bio or ''
    })


@app.route('/api/profile', methods=['POST'])
def api_update_profile():
    user = current_user()
    if not user:
        return jsonify({"error": "login_required"}), 401

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()[:100]
    bio = (data.get('bio') or '').strip()[:300]

    if name:
        user.name = name
    user.bio = bio

    db.session.commit()

    return jsonify({"success": True, "name": user.name, "bio": user.bio})


@app.route('/api/profile/avatar', methods=['POST'])
def api_upload_avatar():
    user = current_user()
    if not user:
        return jsonify({"error": "login_required"}), 401

    if 'avatar' not in request.files:
        return jsonify({"error": "no_file"}), 400

    file = request.files['avatar']

    if file.mimetype not in ALLOWED_IMAGE_TYPES:
        return jsonify({"error": "invalid_type", "message": "Faqat JPG, PNG yoki WEBP formatlariga ruxsat berilgan"}), 400

    file_data = file.read()

    if len(file_data) > MAX_AVATAR_SIZE:
        return jsonify({"error": "too_large", "message": "Rasm hajmi 2MB dan katta bolmasligi kerak"}), 400

    encoded = base64.b64encode(file_data).decode('utf-8')
    data_uri = f"data:{file.mimetype};base64,{encoded}"

    user.custom_avatar = data_uri
    db.session.commit()

    logger.info(f"Foydalanuvchi avatarini yangiladi: {user.name}")

    return jsonify({"success": True, "avatar": data_uri})


@app.route('/api/profile/avatar', methods=['DELETE'])
def api_remove_avatar():
    user = current_user()
    if not user:
        return jsonify({"error": "login_required"}), 401

    user.custom_avatar = None
    db.session.commit()

    return jsonify({"success": True, "avatar": user.avatar})


@app.route('/api/friends/search')
@login_required_api
def api_friends_search():
    user = current_user()
    q = (request.args.get('q') or '').strip()

    if len(q) < 2:
        return jsonify([])

    results = User.query.filter(
        User.name.ilike(f'%{q}%'),
        User.id != user.id,
        User.is_banned == False
    ).limit(20).all()

    output = []
    for u in results:
        status = 'none'
        if are_friends(user.id, u.id):
            status = 'friends'
        else:
            sent = FriendRequest.query.filter_by(sender_id=user.id, receiver_id=u.id, status='pending').first()
            received = FriendRequest.query.filter_by(sender_id=u.id, receiver_id=user.id, status='pending').first()
            if sent:
                status = 'pending_sent'
            elif received:
                status = 'pending_received'

        output.append({
            "id": u.id,
            "name": u.name,
            "avatar": get_display_avatar(u),
            "status": status
        })

    return jsonify(output)


@app.route('/api/friends/request', methods=['POST'])
@login_required_api
def api_friend_request():
    user = current_user()
    data = request.get_json() or {}
    to_id = data.get('user_id')

    if not to_id or int(to_id) == user.id:
        return jsonify({"error": "invalid_target"}), 400

    target = db.session.get(User, to_id)
    if not target:
        return jsonify({"error": "not_found"}), 404

    if are_friends(user.id, to_id):
        return jsonify({"error": "already_friends"}), 400

    existing = FriendRequest.query.filter_by(sender_id=user.id, receiver_id=to_id, status='pending').first()
    if existing:
        return jsonify({"error": "already_sent"}), 400

    reverse = FriendRequest.query.filter_by(sender_id=to_id, receiver_id=user.id, status='pending').first()
    if reverse:
        return jsonify({"error": "they_already_sent"}), 400

    req = FriendRequest(sender_id=user.id, receiver_id=to_id, status='pending')
    db.session.add(req)
    db.session.commit()

    logger.info(f"Dostlik taklifi: {user.name} -> {target.name}")

    socketio.emit('friend_request_received', {
        "request_id": req.id,
        "user_id": user.id,
        "name": user.name,
        "avatar": get_display_avatar(user)
    }, room=str(to_id))

    return jsonify({"success": True})


@app.route('/api/friends/requests')
@login_required_api
def api_friend_requests():
    user = current_user()
    requests_in = FriendRequest.query.filter_by(receiver_id=user.id, status='pending').all()

    output = []
    for r in requests_in:
        sender = db.session.get(User, r.sender_id)
        if not sender:
            continue
        output.append({
            "request_id": r.id,
            "user_id": sender.id,
            "name": sender.name,
            "avatar": get_display_avatar(sender)
        })

    return jsonify(output)


@app.route('/api/friends/requests/<int:req_id>/respond', methods=['POST'])
@login_required_api
def api_friend_respond(req_id):
    user = current_user()
    data = request.get_json() or {}
    action = data.get('action')

    req = db.session.get(FriendRequest, req_id)
    if not req or req.receiver_id != user.id:
        return jsonify({"error": "not_found"}), 404

    if action == 'accept':
        req.status = 'accepted'
        socketio.emit('friend_request_accepted', {
            "user_id": user.id,
            "name": user.name,
            "avatar": get_display_avatar(user)
        }, room=str(req.sender_id))
    elif action == 'reject':
        req.status = 'rejected'
    else:
        return jsonify({"error": "invalid_action"}), 400

    db.session.commit()
    return jsonify({"success": True, "status": req.status})


@app.route('/api/friends')
@login_required_api
def api_friends_list():
    user = current_user()
    accepted = FriendRequest.query.filter(
        db.or_(FriendRequest.sender_id == user.id, FriendRequest.receiver_id == user.id),
        FriendRequest.status == 'accepted'
    ).all()

    output = []
    for r in accepted:
        other_id = r.receiver_id if r.sender_id == user.id else r.sender_id
        other = db.session.get(User, other_id)
        if not other:
            continue
        output.append({
            "id": other.id,
            "name": other.name,
            "avatar": get_display_avatar(other),
            "is_online": other.id in online_user_counts
        })

    return jsonify(output)


@app.route('/api/friends/<int:friend_id>', methods=['DELETE'])
@login_required_api
def api_remove_friend(friend_id):
    user = current_user()
    req = get_friendship_row(user.id, friend_id)

    if not req:
        return jsonify({"error": "not_friends"}), 404

    db.session.delete(req)
    db.session.commit()

    logger.info(f"Dostlikdan chiqarish: {user.name} -x- user#{friend_id}")

    socketio.emit('friend_removed', {"user_id": user.id}, room=str(friend_id))

    return jsonify({"success": True})


@app.route('/api/friends/<int:friend_id>/messages')
@login_required_api
def api_friend_messages(friend_id):
    user = current_user()

    if not are_friends(user.id, friend_id):
        return jsonify({"error": "not_friends"}), 403

    friend = db.session.get(User, friend_id)

    msgs = DirectMessage.query.filter(
        db.or_(
            db.and_(DirectMessage.sender_id == user.id, DirectMessage.receiver_id == friend_id),
            db.and_(DirectMessage.sender_id == friend_id, DirectMessage.receiver_id == user.id)
        )
    ).order_by(DirectMessage.created_at.asc()).limit(200).all()

    return jsonify([{
        "id": m.id,
        "sender_id": m.sender_id,
        "message": m.message,
        "is_mine": m.sender_id == user.id,
        "avatar": get_display_avatar(user) if m.sender_id == user.id else get_display_avatar(friend),
        "reaction": m.reaction,
        "time": m.created_at.strftime("%H:%M")
    } for m in msgs])


@app.route('/api/ai/feedback', methods=['POST'])
def api_ai_feedback():
    user = current_user()
    data = request.get_json() or {}
    prompt = (data.get('prompt') or '').strip()[:2000]
    response_text = (data.get('response') or '').strip()[:4000]
    rating = data.get('rating')

    if rating not in (1, -1):
        return jsonify({"error": "invalid_rating"}), 400

    fb = AIFeedback(user_id=user.id if user else None, prompt=prompt, response=response_text, rating=rating)
    db.session.add(fb)

    if user:
        pref = UserAIPreference.query.filter_by(user_id=user.id).first()
        if not pref:
            pref = UserAIPreference(user_id=user.id)
            db.session.add(pref)

        length = len(response_text)
        if rating == 1:
            pref.avg_liked_length = ((pref.avg_liked_length * pref.likes_count) + length) / (pref.likes_count + 1)
            pref.likes_count += 1
        else:
            pref.avg_disliked_length = ((pref.avg_disliked_length * pref.dislikes_count) + length) / (pref.dislikes_count + 1)
            pref.dislikes_count += 1

        pref.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"success": True})


@app.route('/api/groups', methods=['POST'])
@login_required_api
def api_create_group():
    user = current_user()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()[:100] or "Nomsiz guruh"
    member_ids = data.get('member_ids') or []

    valid_member_ids = set()
    for mid in member_ids:
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            continue
        if are_friends(user.id, mid):
            valid_member_ids.add(mid)

    if len(valid_member_ids) < 1:
        return jsonify({"error": "need_at_least_one_member"}), 400

    group = Group(name=name, creator_id=user.id)
    db.session.add(group)
    db.session.flush()

    db.session.add(GroupMember(group_id=group.id, user_id=user.id))
    for mid in valid_member_ids:
        db.session.add(GroupMember(group_id=group.id, user_id=mid))

    db.session.commit()

    logger.info(f"Guruh yaratildi: '{name}' ({user.name} tomonidan)")

    for mid in valid_member_ids:
        join_room('group_' + str(group.id))
        socketio.emit('group_created', {"group_id": group.id, "name": group.name}, room=str(mid))

    return jsonify({"success": True, "group_id": group.id, "name": group.name})


@app.route('/api/groups')
@login_required_api
def api_list_groups():
    user = current_user()
    memberships = GroupMember.query.filter_by(user_id=user.id).all()

    output = []
    for m in memberships:
        group = db.session.get(Group, m.group_id)
        if not group:
            continue
        member_count = GroupMember.query.filter_by(group_id=group.id).count()
        output.append({"id": group.id, "name": group.name, "member_count": member_count})

    return jsonify(output)


@app.route('/api/groups/<int:group_id>/messages')
@login_required_api
def api_group_messages(group_id):
    user = current_user()
    if not is_group_member(group_id, user.id):
        return jsonify({"error": "not_member"}), 403

    msgs = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.asc()).limit(200).all()

    output = []
    for m in msgs:
        sender = db.session.get(User, m.sender_id) if m.sender_id else None
        output.append({
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": AI_NAME if m.is_ai else (sender.name if sender else "?"),
            "sender_avatar": None if m.is_ai else (get_display_avatar(sender) if sender else None),
            "message": m.message,
            "is_ai": m.is_ai,
            "time": m.created_at.strftime("%H:%M")
        })

    return jsonify(output)


@app.route('/api/support', methods=['POST'])
def api_submit_support():
    user = current_user()
    data = request.get_json() or {}
    message = (data.get('message') or '').strip()[:2000]
    name = (data.get('name') or (user.name if user else '')).strip()[:100]
    email = (data.get('email') or (user.email if user else '')).strip()[:150]

    if not message:
        return jsonify({"error": "empty_message"}), 400

    ticket = SupportTicket(
        user_id=user.id if user else None,
        name=name or 'Anonim',
        email=email,
        message=message
    )
    db.session.add(ticket)
    db.session.commit()

    logger.info(f"Yangi murojaat: {name or 'Anonim'} ({email})")

    return jsonify({"success": True})


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    ip = get_client_ip()
    record = admin_login_attempts.get(ip)

    if record and record.get('locked_until') and datetime.utcnow() < record['locked_until']:
        remaining = int((record['locked_until'] - datetime.utcnow()).total_seconds() / 60) + 1
        return render_template('admin_login.html', error=f"Juda kop notogri urinish. {remaining} daqiqadan song qayta urinib koring.")

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session.permanent = True
            admin_login_attempts.pop(ip, None)
            log_admin_action("admin_login", f"IP: {ip}")
            return redirect(url_for('admin_dashboard'))
        else:
            record = admin_login_attempts.setdefault(ip, {"count": 0, "locked_until": None})
            record['count'] += 1
            if record['count'] >= ADMIN_LOGIN_MAX_ATTEMPTS:
                record['locked_until'] = datetime.utcnow() + timedelta(minutes=ADMIN_LOGIN_LOCKOUT_MINUTES)
                logger.warning(f"Admin login bloklandi (IP: {ip}) — juda kop notogri urinish.")
                error = f"Juda kop notogri urinish. {ADMIN_LOGIN_LOCKOUT_MINUTES} daqiqaga bloklandingiz."
            else:
                error = f"Parol notogri. Yana {ADMIN_LOGIN_MAX_ATTEMPTS - record['count']} ta urinish qoldi."
    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    uptime_seconds = int((datetime.utcnow() - SERVER_START_TIME).total_seconds())
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    total_users = User.query.count()

    return render_template(
        'admin.html',
        online_count=len(connected_sids),
        total_public=stats["total_public_messages"],
        total_ai=stats["total_ai_messages"],
        total_connections=stats["total_connections"],
        total_users=total_users,
        uptime=f"{hours} soat {minutes} daqiqa",
        ai_connected=ai_client is not None,
        history=list(public_history)[::-1]
    )


@app.route('/admin/api/stats')
@admin_required
def admin_api_stats():
    uptime_seconds = int((datetime.utcnow() - SERVER_START_TIME).total_seconds())
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    total_users = User.query.count()

    return jsonify({
        "online_count": len(connected_sids),
        "total_public": stats["total_public_messages"],
        "total_ai": stats["total_ai_messages"],
        "total_connections": stats["total_connections"],
        "total_users": total_users,
        "uptime": f"{hours} soat {minutes} daqiqa",
        "history": list(public_history)[::-1]
    })


@app.route('/admin/api/ai-stats')
@admin_required
def admin_ai_stats():
    total_likes = AIFeedback.query.filter_by(rating=1).count()
    total_dislikes = AIFeedback.query.filter_by(rating=-1).count()
    total = total_likes + total_dislikes
    satisfaction = round((total_likes / total) * 100, 1) if total else None
    personalized_users = UserAIPreference.query.filter(
        (UserAIPreference.likes_count + UserAIPreference.dislikes_count) >= 3
    ).count()

    return jsonify({
        "total_likes": total_likes,
        "total_dislikes": total_dislikes,
        "satisfaction_percent": satisfaction,
        "personalized_users": personalized_users
    })


@app.route('/admin/api/friends-overview')
@admin_required
def admin_friends_overview():
    total_friendships = FriendRequest.query.filter_by(status='accepted').count()
    pending_requests = FriendRequest.query.filter_by(status='pending').count()

    return jsonify({
        "total_friendships": total_friendships,
        "pending_requests": pending_requests
    })


@app.route('/admin/api/broadcast', methods=['POST'])
@admin_required
def admin_broadcast():
    data = request.get_json() or {}
    text = (data.get('message') or '').strip()[:500]

    if not text:
        return jsonify({"error": "empty_message"}), 400

    stats["total_public_messages"] += 1
    msg_id = next(public_msg_counter)
    entry = {
        "id": msg_id,
        "username": "📢 Notfic E'lon",
        "message": text,
        "avatar": None,
        "time": datetime.utcnow().strftime("%H:%M:%S")
    }
    public_history.append(entry)

    socketio.emit('public_response_message', entry)

    logger.info(f"Admin elon yubordi: {text}")
    log_admin_action("broadcast", text[:200])

    return jsonify({"success": True})


@app.route('/admin/api/users')
@admin_required
def admin_api_users():
    search = (request.args.get('q') or '').strip().lower()
    users = User.query.order_by(User.created_at.desc()).all()
    if search:
        users = [u for u in users if search in (u.name or '').lower() or search in (u.email or '').lower()]

    return jsonify([{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "avatar": get_display_avatar(u),
        "is_banned": u.is_banned,
        "is_admin": is_admin_user(u),
        "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else ''
    } for u in users])


@app.route('/admin/api/users/<int:user_id>/ban', methods=['POST'])
@admin_required
def admin_toggle_ban(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    if is_admin_user(user):
        return jsonify({"error": "cannot_ban_admin"}), 400

    user.is_banned = not user.is_banned
    db.session.commit()

    logger.info(f"Admin foydalanuvchini {'bloklandi' if user.is_banned else 'blokdan chiqarildi'}: {user.email}")
    log_admin_action("toggle_ban", f"user#{user_id} ({user.email}) -> {'banned' if user.is_banned else 'unbanned'}")

    if user.is_banned:
        socketio.emit('force_logout', {"reason": "banned"}, room=str(user_id))

    return jsonify({"success": True, "is_banned": user.is_banned})


@app.route('/admin/api/messages/<int:msg_id>', methods=['DELETE'])
@admin_required
def admin_delete_message(msg_id):
    global public_history
    found = False
    new_history = deque(maxlen=200)
    for m in public_history:
        if m.get('id') == msg_id:
            found = True
            continue
        new_history.append(m)
    public_history = new_history

    if found:
        socketio.emit('message_deleted', {'id': msg_id})
        log_admin_action("delete_public_message", f"msg#{msg_id}")

    return jsonify({"success": found})


@app.route('/admin/api/users/<int:user_id>/messages')
@admin_required
def admin_view_user_messages(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    msgs = DirectMessage.query.filter(
        db.or_(DirectMessage.sender_id == user_id, DirectMessage.receiver_id == user_id)
    ).order_by(DirectMessage.created_at.desc()).limit(100).all()

    log_admin_action("view_user_messages", f"user#{user_id} ({user.email})")

    return jsonify([{
        "id": m.id,
        "sender_id": m.sender_id,
        "receiver_id": m.receiver_id,
        "message": m.message,
        "time": m.created_at.strftime("%Y-%m-%d %H:%M")
    } for m in msgs])


@app.route('/admin/api/users/<int:user_id>/delete', methods=['POST'])
@admin_required
@dangerous_action("delete_user")
def admin_delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    if is_admin_user(user):
        return jsonify({"error": "cannot_delete_admin"}), 400

    FriendRequest.query.filter(
        db.or_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == user_id)
    ).delete(synchronize_session=False)
    DirectMessage.query.filter(
        db.or_(DirectMessage.sender_id == user_id, DirectMessage.receiver_id == user_id)
    ).delete(synchronize_session=False)
    AIFeedback.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    UserAIPreference.query.filter_by(user_id=user_id).delete(synchronize_session=False)

    email = user.email
    db.session.delete(user)
    db.session.commit()

    logger.warning(f"Admin foydalanuvchini BUTUNLAY OCHIRDI: user#{user_id} ({email})")
    log_admin_action("delete_user", f"user#{user_id} ({email})")

    socketio.emit('force_logout', {"reason": "account_deleted"}, room=str(user_id))

    return jsonify({"success": True})


@app.route('/admin/api/export/users', methods=['POST'])
@admin_required
@dangerous_action("export_users")
def admin_export_users():
    users = User.query.all()
    data = [{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "is_banned": u.is_banned,
        "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else ''
    } for u in users]

    log_admin_action("export_users", f"{len(data)} ta foydalanuvchi")

    return jsonify(data)


@app.route('/admin/api/support')
@admin_required
def admin_list_support():
    status_filter = request.args.get('status', 'open')
    query = SupportTicket.query
    if status_filter in ('open', 'resolved'):
        query = query.filter_by(status=status_filter)
    tickets = query.order_by(SupportTicket.created_at.desc()).limit(100).all()

    return jsonify([{
        "id": t.id,
        "name": t.name,
        "email": t.email,
        "message": t.message,
        "status": t.status,
        "time": t.created_at.strftime("%Y-%m-%d %H:%M")
    } for t in tickets])


@app.route('/admin/api/support/<int:ticket_id>/resolve', methods=['POST'])
@admin_required
def admin_resolve_support(ticket_id):
    ticket = db.session.get(SupportTicket, ticket_id)
    if not ticket:
        return jsonify({"error": "not_found"}), 404

    ticket.status = 'resolved'
    db.session.commit()

    log_admin_action("resolve_support_ticket", f"ticket#{ticket_id} ({ticket.email})")

    return jsonify({"success": True})


@app.route('/admin/api/audit-log')
@admin_required
def admin_audit_log():
    entries = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(150).all()
    return jsonify([{
        "action": e.action,
        "detail": e.detail,
        "time": e.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for e in entries])


@socketio.on('connect')
def handle_connect():
    connected_sids.add(request.sid)
    stats["total_connections"] += 1

    user = current_user()
    if user:
        join_room(str(user.id))
        for gid in get_group_ids_for_user(user.id):
            join_room('group_' + str(gid))

        online_user_counts[user.id] = online_user_counts.get(user.id, 0) + 1
        if online_user_counts[user.id] == 1:
            socketio.emit('friend_online', {"user_id": user.id})

    logger.info(f"Yangi foydalanuvchi ulandi. Hozir onlayn: {len(connected_sids)}")


@socketio.on('disconnect')
def handle_disconnect():
    connected_sids.discard(request.sid)
    anonymous_message_counts.pop(request.sid, None)

    user = current_user()
    if user and user.id in online_user_counts:
        online_user_counts[user.id] -= 1
        if online_user_counts[user.id] <= 0:
            online_user_counts.pop(user.id, None)
            socketio.emit('friend_offline', {"user_id": user.id})

    logger.info(f"Foydalanuvchi uzildi. Hozir onlayn: {len(connected_sids)}")


def is_logged_in_session():
    return current_user() is not None


def is_banned_session():
    user = current_user()
    return user.is_banned if user else False


@socketio.on('ai_message')
def handle_ai_message(data):
    if is_banned_session():
        emit('banned_notice', {'message': 'Hisobingiz bloklangan.'})
        return

    username = (data.get('username') or 'Anonim').strip()[:50]
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')
    context = data.get('context') or []

    if not msg:
        return

    if not is_logged_in_session():
        count = anonymous_message_counts.get(request.sid, 0)
        if count >= ANONYMOUS_MESSAGE_LIMIT:
            emit('login_required', {
                'message': 'Bepul xabarlar tugadi. Davom etish uchun Google orqali kiring.'
            })
            return
        anonymous_message_counts[request.sid] = count + 1
        remaining = ANONYMOUS_MESSAGE_LIMIT - anonymous_message_counts[request.sid]
        emit('anon_limit_update', {'remaining': remaining})

    stats["total_ai_messages"] += 1
    logger.info(f"[AI-shaxsiy] {username}: {msg}")

    emit('ai_response_message', {'username': username, 'message': msg, 'isAI': False, 'clientId': client_id})

    emit('ai_typing', {'typing': True})
    user = current_user()
    ai_reply = get_ai_response(msg, context, user=user)
    emit('ai_typing', {'typing': False})
    emit('ai_response_message', {'username': AI_NAME, 'message': ai_reply, 'isAI': True, 'prompt': msg})


@socketio.on('public_message')
def handle_public_message(data):
    if is_banned_session():
        emit('banned_notice', {'message': 'Hisobingiz bloklangan.'})
        return

    user = current_user()
    username = (data.get('username') or 'Anonim').strip()[:50]
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')

    if not msg:
        return

    if not is_logged_in_session():
        count = anonymous_message_counts.get(request.sid, 0)
        if count >= ANONYMOUS_MESSAGE_LIMIT:
            emit('login_required', {
                'message': 'Bepul xabarlar tugadi. Davom etish uchun Google orqali kiring.'
            })
            return
        anonymous_message_counts[request.sid] = count + 1
        remaining = ANONYMOUS_MESSAGE_LIMIT - anonymous_message_counts[request.sid]
        emit('anon_limit_update', {'remaining': remaining})

    avatar = get_display_avatar(user) if user else None

    stats["total_public_messages"] += 1
    msg_id = next(public_msg_counter)
    public_history.append({
        "id": msg_id,
        "username": username,
        "message": msg,
        "avatar": avatar,
        "time": datetime.utcnow().strftime("%H:%M:%S")
    })

    logger.info(f"[Ochiq] {username}: {msg}")

    emit('public_response_message',
         {'id': msg_id, 'username': username, 'message': msg, 'avatar': avatar, 'clientId': client_id},
         broadcast=True)


@socketio.on('friend_message')
def handle_friend_message(data):
    user = current_user()
    if not user or user.is_banned:
        return

    to_id = data.get('to_user_id')
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')

    if not msg or not to_id:
        return

    if not are_friends(user.id, to_id):
        return

    row = DirectMessage(sender_id=user.id, receiver_id=to_id, message=msg)
    db.session.add(row)
    db.session.commit()

    logger.info(f"[Dost xabari] {user.name} -> user#{to_id}: {msg}")

    payload = {
        "id": row.id,
        "from_user_id": user.id,
        "to_user_id": int(to_id),
        "message": msg,
        "sender_name": user.name,
        "sender_avatar": get_display_avatar(user),
        "time": row.created_at.strftime("%H:%M"),
        "clientId": client_id
    }

    emit('friend_message', payload, room=str(to_id))
    emit('friend_message', payload, room=str(user.id))

    # Agar @AI deb chaqirilsa, AI shu dostlar suhbatiga uchinchi ishtirokchi sifatida qoshiladi
    if AI_TRIGGER in msg.lower():
        friend = db.session.get(User, to_id)
        note = (
            "Siz hozir ikki do'st (" + (user.name or 'Foydalanuvchi') + " va " +
            (friend.name if friend else 'dostlari') +
            ") orasidagi shaxsiy suhbatga uchinchi ishtirokchi sifatida qoshildingiz. "
            "Ular sizni @AI deb chaqirishdi. Do'stona, tabiiy ohangda, suhbat kontekstiga mos qisqa javob bering."
        )
        ai_reply = get_ai_response(msg, user=user, extra_system_note=note)

        ai_payload = {
            "id": None,
            "from_user_id": user.id,
            "to_user_id": int(to_id),
            "message": ai_reply,
            "sender_name": AI_NAME,
            "sender_avatar": None,
            "time": datetime.utcnow().strftime("%H:%M"),
            "isAI": True,
            "prompt": msg
        }
        emit('friend_message', ai_payload, room=str(to_id))
        emit('friend_message', ai_payload, room=str(user.id))


@socketio.on('react_public')
def handle_react_public(data):
    msg_id = data.get('msg_id')
    emoji = (data.get('emoji') or '').strip()[:8]
    if not msg_id or not emoji:
        return

    for m in public_history:
        if m.get('id') == msg_id:
            m['reaction'] = emoji
            break

    emit('public_reaction_update', {'id': msg_id, 'emoji': emoji}, broadcast=True)


@socketio.on('react_friend')
def handle_react_friend(data):
    user = current_user()
    if not user:
        return

    msg_id = data.get('msg_id')
    to_id = data.get('to_user_id')
    emoji = (data.get('emoji') or '').strip()[:8]

    if not msg_id or not to_id or not emoji:
        return

    if not are_friends(user.id, to_id):
        return

    row = db.session.get(DirectMessage, msg_id)
    if not row or row.sender_id not in (user.id, int(to_id)) or row.receiver_id not in (user.id, int(to_id)):
        return

    row.reaction = emoji
    db.session.commit()

    payload = {'id': msg_id, 'emoji': emoji}
    emit('friend_reaction_update', payload, room=str(to_id))
    emit('friend_reaction_update', payload, room=str(user.id))


@socketio.on('group_message')
def handle_group_message(data):
    user = current_user()
    if not user or user.is_banned:
        return

    group_id = data.get('group_id')
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')

    if not msg or not group_id or not is_group_member(group_id, user.id):
        return

    row = GroupMessage(group_id=group_id, sender_id=user.id, message=msg, is_ai=False)
    db.session.add(row)
    db.session.commit()

    payload = {
        "id": row.id,
        "group_id": group_id,
        "sender_id": user.id,
        "sender_name": user.name,
        "sender_avatar": get_display_avatar(user),
        "message": msg,
        "is_ai": False,
        "time": row.created_at.strftime("%H:%M"),
        "clientId": client_id
    }
    emit('group_message', payload, room='group_' + str(group_id))

    if AI_TRIGGER in msg.lower():
        group = db.session.get(Group, group_id)
        note = (
            "Siz hozir \"" + (group.name if group else "guruh") + "\" nomli dostlar guruh suhbatiga "
            "uchinchi ishtirokchi sifatida qoshildingiz. Sizni @AI deb chaqirishdi. "
            "Do'stona, qisqa javob bering, suhbat kontekstiga mos boling."
        )
        ai_reply = get_ai_response(msg, user=user, extra_system_note=note)

        ai_row = GroupMessage(group_id=group_id, sender_id=None, message=ai_reply, is_ai=True)
        db.session.add(ai_row)
        db.session.commit()

        ai_payload = {
            "id": ai_row.id,
            "group_id": group_id,
            "sender_id": None,
            "sender_name": AI_NAME,
            "sender_avatar": None,
            "message": ai_reply,
            "is_ai": True,
            "time": ai_row.created_at.strftime("%H:%M"),
            "prompt": msg
        }
        emit('group_message', ai_payload, room='group_' + str(group_id))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Notfic server {port}-portda ishga tushmoqda...")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)