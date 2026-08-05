import eventlet
eventlet.monkey_patch()

import os
import logging
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("notfic")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "notfic_secret_key_123")
AI_MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return {"status": "ok", "ai_connected": ai_client is not None}, 200


@socketio.on('connect')
def handle_connect():
    logger.info("Yangi foydalanuvchi ulandi.")


@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Foydalanuvchi uzildi.")


@socketio.on('ai_message')
def handle_ai_message(data):
    username = (data.get('username') or 'Anonim').strip()[:50]
    msg = (data.get('message') or '').strip()[:2000]
    client_id = data.get('clientId')

    if not msg:
        return

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

    logger.info(f"[Ochiq] {username}: {msg}")

    emit('public_response_message', {'username': username, 'message': msg, 'clientId': client_id}, broadcast=True)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Notfic server {port}-portda ishga tushmoqda...")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)