import os

IS_RENDER = os.environ.get("RENDER") is not None

if IS_RENDER:
    import eventlet
    eventlet.monkey_patch()

import base64
import logging
from datetime import datetime
from functools import wraps
from collections import deque

from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("notfic")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "notfic_secret_key_123")
AI_MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "notfic_admin_2026")
AI_NAME = "Notfic AI ⚡"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

ANONYMOUS_MESSAGE_LIMIT = 10

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///notfic.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY topilmadi!")
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.warning("Google OAuth sozlanmagan!")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

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


# ---------- MODEL ----------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(150))
    avatar = db.Column(db.String(500))
    custom_avatar = db.Column(db.Text, nullable=True)
    bio = db.Column(db.String(300), default='')
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
public_history = deque(maxlen=50)

anonymous_message_counts = {}


def get_ai_response(prompt: str) -> str:
    if not ai_client:
        return f"🤖 [{AI_NAME}]: Hozircha AI ulanmagan — server tomonida API kalit sozlanmagan."

    if not prompt or not prompt.strip():
        return f"🤖 [{AI_NAME}]: Savolingizni yozing, men yordam berishga tayyorman!"

    try:
        completion = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt.strip()}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"Groq AI xatosi: {e}")
        return f"🤖 [{AI_NAME}]: Hozir javob bera olmadim, birozdan so'ng qayta urinib ko'ring."


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


def get_display_avatar(user):
    if not user:
        return None
    if user.custom_avatar:
        return user.custom_avatar
    return user.avatar


# ---------- ODDIY ROUTE'LAR ----------
@app.route('/')
def index():
    user = current_user()
    display_avatar = get_display_avatar(user) if user else None
    return render_template('index.html', user=user, display_avatar=display_avatar, anon_limit=ANONYMOUS_MESSAGE_LIMIT)


@app.route('/health')
def health():
    return {"status": "ok", "ai_connected": ai_client is not None}, 200


# ---------- GOOGLE LOGIN ----------
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
    session['user_id'] = user.id

    logger.info(f"Foydalanuvchi kirdi: {name} ({email})")
    return redirect(url_for('index'))


@app.route('/auth/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))


# ---------- PROFIL API ----------
@app.route('/api/profile', methods=['GET'])
def api_get_profile():
    user = current_user()
    if not user:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
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


# ---------- ADMIN ROUTE'LARI ----------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Parol notogri"
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


# ---------- SOCKET.IO ----------
@socketio.on('connect')
def handle_connect():
    connected_sids.add(request.sid)
    stats["total_connections"] += 1
    logger.info(f"Yangi foydalanuvchi ulandi. Hozir onlayn: {len(connected_sids)}")


@socketio.on('disconnect')
def handle_disconnect():
    connected_sids.discard(request.sid)
    anonymous_message_counts.pop(request.sid, None)
    logger.info(f"Foydalanuvchi uzildi. Hozir onlayn: {len(connected_sids)}")


def is_logged_in_session():
    return current_user() is not None


@socketio.on('ai_message')
def handle_ai_message(data):
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

    stats["total_ai_messages"] += 1
    logger.info(f"[AI-shaxsiy] {username}: {msg}")

    emit('ai_response_message', {'username': username, 'message': msg, 'isAI': False, 'clientId': client_id})

    emit('ai_typing', {'typing': True})
    ai_reply = get_ai_response(msg)
    emit('ai_typing', {'typing': False})
    emit('ai_response_message', {'username': AI_NAME, 'message': ai_reply, 'isAI': True})


@socketio.on('public_message')
def handle_public_message(data):
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

    stats["total_public_messages"] += 1
    public_history.append({
        "username": username,
        "message": msg,
        "time": datetime.utcnow().strftime("%H:%M:%S")
    })

    logger.info(f"[Ochiq] {username}: {msg}")

    emit('public_response_message', {'username': username, 'message': msg, 'clientId': client_id}, broadcast=True)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Notfic server {port}-portda ishga tushmoqda...")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)