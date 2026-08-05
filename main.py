import eventlet
eventlet.monkey_patch()

import os
import logging
from datetime import datetime
from functools import wraps
from collections import deque

from flask import Flask, render_template, session, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit
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

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY topilmadi! .env faylini tekshiring.")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

ai_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = (
    "Sening isming Notfic AI. Sen Notfic platformasining aqlli yordamchisisan. "
    "Do'stona, qisqa, tushunarli va aqlli javob ber."
)

# ---------- XOTIRADA SAQLANADIGAN STATISTIKA ----------
SERVER_START_TIME = datetime.utcnow()
connected_sids = set()
stats = {
    "total_public_messages": 0,
    "total_ai_messages": 0,
    "total_connections": 0,
}
public_history = deque(maxlen=50)


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


# ---------- ADMIN HIMOYASI ----------
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ---------- ODDIY ROUTE'LAR ----------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return {"status": "ok", "ai_connected": ai_client is not None}, 200


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

    return render_template(
        'admin.html',
        online_count=len(connected_sids),
        total_public=stats["total_public_messages"],
        total_ai=stats["total_ai_messages"],
        total_connections=stats["total_connections"],
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

    return jsonify({
        "online_count": len(connected_sids),
        "total_public": stats["total_public_messages"],
        "total_ai": stats["total_ai_messages"],
        "total_connections": stats["total_connections"],
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
    logger.info(f"Foydalanuvchi uzildi. Hozir onlayn: {len(connected_sids)}")


@socketio.on('ai_message')
def handle_ai_message(data):
    username = (data.get('username') or 'Anonim').strip()[:50]
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')

    if not msg:
        return

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