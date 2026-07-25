import os
import subprocess
import time
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from groq import Groq

# .env faylini yuklash
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'notfic_secret_key_123'
socketio = SocketIO(app, cors_allowed_origins="*")

# Groq AI mijozini ishga tushirish
ai_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_ai_response(prompt):
    try:
        completion = ai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Sening isming Notfic AI. Sen Notfic platformasining aqlli yordamchisisan. Do'stona, qisqa, tushunarli va aqlli javob ber."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=1024
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"🤖 [Notfic AI Xatolik]: AI bilan bog'lanishda muammo bo'ldi. (Xato: {e})"

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('message')
def handle_message(data):
    username = data.get('username', 'Anonim')
    msg = data.get('message', '').strip()

    if not msg:
        return

    # 1. Foydalanuvchi xabarini yuborish
    emit('response_message', {'username': username, 'message': msg}, broadcast=True)

    # 2. AI javobi
    if username != 'Notfic AI ⚡':
        ai_reply = get_ai_response(msg)
        emit('response_message', {'username': 'Notfic AI ⚡', 'message': ai_reply}, broadcast=True)

if __name__ == '__main__':
    # LocalTunnel orqali parolsiz va ro'yxatdan o'tmasdan internetga chiqarish
    try:
        subprocess.Popen("lt --port 5000", shell=True)
        print("\n==========================================")
        print("🚀 NOTFIC SERVERI ISHGA TUSHDI!")
        print("Internet havolasini olish uchun buyruq satrini kuzating.")
        print("==========================================\n")
    except Exception as e:
        print("Tunnelni ochishda xatolik:", e)

    socketio.run(app, debug=True, port=5000)