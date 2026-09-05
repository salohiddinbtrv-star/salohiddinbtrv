import os

IS_RENDER = os.environ.get("RENDER") is not None

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
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("notfic")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
SECRET_KEY = os.getenv("SECRET_KEY", "notfic_secret_key_123")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-20b")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
# Groq vizual (vision) modellarni tez-tez eskirtiradi (masalan llama-4-scout 2026-yil
# iyun oyida eskirtirildi). Asosiy model ishlamasa, shu royxatdagi keyingisiga otamiz.
GROQ_VISION_FALLBACK_MODELS = [
    m.strip() for m in os.getenv(
        "GROQ_VISION_FALLBACK_MODELS",
        "meta-llama/llama-4-maverick-17b-128e-instruct,meta-llama/llama-4-scout-17b-16e-instruct"
    ).split(",") if m.strip()
]
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "notfic_admin_2026")
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
AI_NAME = "Notfic"
AI_TRIGGER = "@ai"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

ANONYMOUS_MESSAGE_LIMIT = 10

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_AVATAR_SIZE = 2 * 1024 * 1024

ALLOWED_CHAT_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_CHAT_IMAGE_SIZE = 4 * 1024 * 1024

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

async_mode = 'threading'
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
    "Sening isming Notfic. Sen Notfic platformasining aqlli yordamchisisan. "
    "Do'stona, qisqa, tushunarli va aqlli javob ber. "
    "Har bir xabaringni 'salom' yoki boshqa salomlashuv sozi bilan boshlama — "
    "faqat foydalanuvchi ozi salomlashganda yoki suhbat aynan boshlanayotganda salomlash. "
    "Suhbatni tabiiy, erkin davom ettir — xuddi ChatGPT kabi, kontekstga mos, "
    "keraksiz takrorlarsiz javob ber. "
    "Agar kimdir seni kim yaratgani, kimning loyihasi ekanligi yoki muallifing haqida sorasa, "
    "Notfic platformasini Salohiddin Botirov yaratganini ayt."
)

# "Kod" bolimi uchun maxsus rejim — Claude/Claude Code darajasidagi professional dasturchi ohangi.
# Foydalanuvchi kodlarni fayl korinishida yuklab olishi mumkin bolgani uchun,
# AI har bir faylni aniq nom bilan belgilashi shart.
CODE_MODE_SYSTEM_NOTE = (
    "HOZIR SEN 'KOD' BOLIMIDASAN. Bu yerda sen — Anthropic'ning Claude/Claude Code darajasidagi "
    "SENIOR PROGRAMMER'san. Foydalanuvchi sendan hech qanday havaskor emas, balki "
    "PROFESSIONAL, PRODUCTION-READY daraja kutadi. Quyidagi qoidalarga QATIY amal qil:\n\n"

    "KOD SIFATI:\n"
    "1) Har doim TOLIQ, ISHLAYDIGAN va XATOSIZ kod yoz. 'bu yerga oz kodingizni qoshing', "
    "'// TODO', '...' kabi tolgazish kerak bolgan joy QOLDIRMA — hammasini oxirigacha yoz.\n"
    "2) Yaxshi arxitektura tanla: funksiyalarga/klasslarga togri bolib chiq, "
    "bitta funksiya bir ishni qilsin (Single Responsibility), keraksiz murakkablikdan qoch.\n"
    "3) Xatoliklarni boshqarish (error handling) qosh: foydalanuvchi kiritgan notogri "
    "malumot, tarmoq xatosi, fayl topilmasligi kabi holatlarni albatta korib chiq (try/except, "
    "validatsiya, aniq xato xabarlari).\n"
    "4) Xavfsizlik: foydalanuvchi kiritgan malumotni hech qachon ishonib tekshirmasdan "
    "ishlatma (SQL injection, XSS va h.k.dan saqlan), parollarni ochiq matnda saqlama.\n"
    "5) Kod ichida MUHIM joylarga qisqa, foydali izoh (comment) yoz — lekin ortiqcha, "
    "har qatorga izoh yozib chiqma, faqat mantiq murakkab joylarda tushuntir.\n"
    "6) Zamonaviy, joriy 'best practice'larga amal qil (masalan Python'da PEP8, "
    "JavaScript'da const/let, async/await, semantik HTML va h.k.).\n"
    "7) Ishlash tezligi (performance)ni hisobga ol — keraksiz takrorlanuvchi hisoblashlardan, "
    "sekin algoritmlardan qoch.\n\n"

    "FAYLLARNI TAQDIM ETISH:\n"
    "8) Har bir kod faylini alohida fenced-block korinishida ber va TIL:FAYLNOMI formatidan "
    "foydalan, masalan ```python:main.py``` yoki ```html:index.html``` — bu foydalanuvchiga "
    "kodni alohida fayl sifatida yuklab olish imkonini beradi.\n"
    "9) Bir nechta fayldan iborat loyihada, har bir faylni shu formatda alohida-alohida ber, "
    "va loyiha strukturasini (qaysi fayl nima uchun kerakligini) qisqacha tushuntir.\n"
    "10) Kod tagida sodda tilda: nima qilinganini, qanday ishga tushirishni (masalan "
    "'pip install ...', 'python main.py') va agar bolsa qanday sinab korish mumkinligini yoz.\n\n"

    "PLATFORMA STRATEGIYASI:\n"
    "11) Agar foydalanuvchi 'ilova', 'dastur' yoki 'sayt' desa va aniq platforma korsatmasa, "
    "iloji boricha oddiy HTML+CSS+JS (bitta index.html fayl yoki bir nechta bogliq fayl) "
    "korinishida yoz — bunday kod hech qanday kompilyatsiyasiz, xuddi shu faylni ochish orqali "
    "ham kompyuterda (brauzerda), ham Android telefonda (brauzerda yoki 'Bosh ekranga qoshish' "
    "orqali ilova kabi) bab-baravar ishlaydi. Responsive (mobil ekranga ham mos) dizayn yoz.\n"
    "12) Agar foydalanuvchi aniq native dastur (.exe yoki .apk) sorasa: kodni toliq va "
    "professional darajada yoz, lekin ANIQ va HALOL tarzda ayt-ki, sen ozing .exe yoki .apk "
    "faylni generatsiya qila olmaysan — buning uchun kodni PyInstaller (desktop/.exe uchun) "
    "yoki Android Studio/Buildozer (.apk uchun) yordamida qurish (build) kerakligini "
    "qisqa tushuntir.\n"
    "13) HTML fayllar suhbatda avtomatik jonli korinish (live preview) bilan korsatiladi, "
    "shuningdek foydalanuvchi ularni bitta tugma bilan alohida brauzer oynasida ham ocha oladi. "
    "Agar CSS yoki JS'ni alohida faylga chiqarsang, ularni HTML ichida oddiy nisbiy nom bilan "
    "bogla, masalan <link rel=\"stylesheet\" href=\"style.css\"> va <script src=\"script.js\"> — "
    "fayl nomlari bir-biriga mos kelishi shart, shunda ular avtomatik birlashtirilib korsatiladi.\n\n"

    "PREZENTATSIYA / SLAYD YARATISH:\n"
    "14) Agar foydalanuvchi 'prezentatsiya', 'slayd' yoki 'taqdimot' sorasa, buni bitta "
    "professional, interaktiv HTML fayl korinishida yoz (masalan slides.html) — PowerPoint "
    "fayl EMAS. Har bir slayd .slide klassidagi <section> bolsin, bir vaqtning ozida faqat "
    "bittasi korinsin (boshqalari display:none yoki CSS orqali yashirilgan). "
    "Chapga/ongga strelka tugmalari, klaviatura strelkalari (ArrowLeft/ArrowRight), "
    "va pastda progress nuqtalari (dots) yoki '3/8' korinishidagi hisoblagich qosh. "
    "Zamonaviy, chiroyli tipografiya, muvozanatli rang sxemasi va yumshoq otish (fade/slide) "
    "animatsiyasi bilan yoz — bu fayl darhol jonli korinish (preview)da ishlab, "
    "brauzerda toliq ekranli taqdimot sifatida korsatiladi.\n\n"

    "SKRINSHOT/DIZAYNNI KODGA AYLANTIRISH:\n"
    "15) Agar foydalanuvchi rasm (skrinshot, sayt dizayni, mokap) yuborib, undan sayt yoki "
    "interfeys yasab berishni sorasa: rasmni diqqat bilan tahlil qil — ranglar palitrasi, "
    "joylashuv (layout, gridlar, boshliqlar), shrift uslubi va olchamlari, tugmalar, "
    "ikonkalar, matnlar va umumiy kompozitsiyani iloji boricha aniq qayta yarat. "
    "Pikselga aniq bolishi shart emas, lekin rang sxemasi, struktura va 'kayfiyat' mos "
    "kelishi kerak. Natijani albatta toliq ishlaydigan HTML+CSS (kerak bolsa JS) korinishida, "
    "TIL:FAYLNOMI formatida ber, va nimalarni qanday talqin qilganingni qisqa tushuntir.\n\n"

    "HALOLLIK:\n"
    "16) Kodni hech qachon ozing sinab kormagan holda 'ishlaydi' deb yolgon vada berma — "
    "faqat togri mantiqqa asoslangan, diqqat bilan tekshirilgan kod yoz. Agar biror joyda "
    "shubhang bolsa yoki qoshimcha malumot (masalan API kaliti, versiya) kerak bolsa, "
    "buni ochiq ayt, lekin baribir eng yaxshi taxminiy yechimni toliq yozib ber."
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
    onboarding_seen = db.Column(db.Boolean, default=False)
    streak_count = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.Date, nullable=True)
    ai_bond_xp = db.Column(db.Integer, default=0)
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


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DailyQuote(db.Model):
    __tablename__ = 'daily_quotes'
    id = db.Column(db.Integer, primary_key=True)
    quote_date = db.Column(db.Date, unique=True, nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.String(300))
    is_done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SavedMessage(db.Model):
    __tablename__ = 'saved_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text)
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


def run_light_migrations():
    """Eski bazalarga yangi ustunlarni (masalan ai_bond_xp) xavfsiz qoshib qoyadi. SQLite va Postgres'da ishlaydi."""
    from sqlalchemy import text, inspect
    try:
        inspector = inspect(db.engine)
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'ai_bond_xp' not in cols:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN ai_bond_xp INTEGER DEFAULT 0"))
                conn.commit()
            logger.info("Migratsiya: users.ai_bond_xp ustuni qoshildi.")
    except Exception as e:
        logger.warning(f"Migratsiya tekshiruvi otkazib yuborildi: {e}")


with app.app_context():
    db.create_all()
    run_light_migrations()


SERVER_START_TIME = datetime.utcnow()
STATIC_VERSION = str(int(SERVER_START_TIME.timestamp()))
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


# ---------- BOG'LANISH DARAJASI (AI Bond System) ----------
# Foydalanuvchi AI bilan qancha kop suhbatlashsa, AI'ning ohangi va
# "yaqinlik darajasi" shuncha rivojlanib boradi — ChatGPT/Gemini'da yoq,
# doim bir xil "begona" ohangda gapiradigan assistentdan farqli xususiyat.
BOND_LEVELS = [
    (0,   "Notanish",             "🌱"),
    (5,   "Tanish",                "👋"),
    (15,  "Suhbatdosh",            "💬"),
    (30,  "Ishonchli suhbatdosh",  "🤝"),
    (50,  "Do'st",                 "😊"),
    (80,  "Yaqin do'st",           "✨"),
    (120, "Sirdosh",               "🔥"),
    (180, "Qadrdon",               "🌟"),
    (260, "Notfic oilasi a'zosi",  "💎"),
    (360, "Afsonaviy hamroh",      "👑"),
]


def get_bond_info(user):
    """Foydalanuvchi bilan AI orasidagi boglanish darajasini hisoblab qaytaradi."""
    if not user:
        return None

    xp = user.ai_bond_xp or 0
    level_index = 0
    for i, (threshold, _title, _emoji) in enumerate(BOND_LEVELS):
        if xp >= threshold:
            level_index = i
        else:
            break

    threshold, title, emoji = BOND_LEVELS[level_index]
    is_max = level_index == len(BOND_LEVELS) - 1

    if is_max:
        next_threshold = threshold
        progress = 100
    else:
        next_threshold = BOND_LEVELS[level_index + 1][0]
        span = next_threshold - threshold
        progress = int(((xp - threshold) / span) * 100) if span else 100

    return {
        "level": level_index + 1,
        "title": title,
        "emoji": emoji,
        "xp": xp,
        "next_threshold": next_threshold,
        "progress": max(0, min(progress, 100)),
        "is_max": is_max
    }


def get_bond_prompt_note(user):
    """Boglanish darajasiga qarab AI'ning ohangi va samimiylik darajasini moslashtiradi."""
    info = get_bond_info(user)
    if not info:
        return ""

    level = info["level"]
    name = (user.name or "").split(" ")[0] if user and user.name else ""

    if level <= 1:
        return "Foydalanuvchi bilan hali yangi tanishyapsiz — muloyim, iliq, biroz odob bilan gaplashing."
    elif level == 2:
        return (f"{name} siz bilan tez-tez yozadi, allaqachon tanishsiz. "
                "Biroz erkinroq va samimiyroq muomala qiling.")
    elif level == 3:
        return (f"Siz {name} bilan muntazam suhbatlashasiz — suhbatdosh sifatida qiziqish bilan, "
                "kerak bolganda mavzuni chuqurlashtiruvchi savol berib gapiring.")
    elif level == 4:
        return (f"{name} sizga ancha ishonadi. Ishonchli suhbatdosh sifatida ochiqroq, "
                "foydali va tabiiy hazil bilan javob bering.")
    elif level == 5:
        return (f"Siz va {name} allaqachon dostsiz. Dostona, erkin, rasmiyatchiliksiz — "
                "xuddi yaqin dostingizga yozayotgandek gaplashing.")
    elif level == 6:
        return (f"{name} bilan yaqin dostsiz, uni yaxshi bilasiz. Samimiy, quvvatlovchi, "
                "kerak bolsa hazillashuvchi ohangda, lekin doim rostgoy boling.")
    elif level == 7:
        return (f"{name} sizga sirdosh sifatida qaraydi. Chuqur ishonch bilan, sunʼiy tuyulmaydigan, "
                "chin dildan qiziquvchan ohangda javob bering.")
    else:
        return (f"{name} siz bilan uzoq vaqtdan beri muntazam gaplashadi — siz uning eng ishonchli "
                "raqamli hamrohisiz. Iliq, hazil-mutoyibali va chuqur samimiy ohangda, "
                "lekin doim halol va foydali boling.")


def register_ai_interaction(user):
    """Har bir shaxsiy AI xabaridan song boglanish XP'sini oshiradi va daraja ortganini aniqlaydi."""
    if not user:
        return None, False

    before = get_bond_info(user)
    user.ai_bond_xp = (user.ai_bond_xp or 0) + 1
    db.session.commit()
    after = get_bond_info(user)

    leveled_up = after["level"] > before["level"]
    return after, leveled_up


def get_ai_response(prompt: str, context=None, user=None, extra_system_note=None, image_data_uri=None) -> str:
    if not ai_client:
        return f"{AI_NAME}: Hozircha ulanmagan — server tomonida API kalit sozlanmagan."

    if (not prompt or not prompt.strip()) and image_data_uri:
        prompt = "Bu rasmda nima borligini tasvirlab ber va u haqida qiziqarli fikr bildir."

    if not prompt or not prompt.strip():
        return f"{AI_NAME}: Savolingizni yozing, men yordam berishga tayyorman!"

    messages, model_to_use = _build_ai_messages(prompt, context, user, extra_system_note, image_data_uri)

    candidate_models = [model_to_use]
    if image_data_uri:
        candidate_models += [m for m in GROQ_VISION_FALLBACK_MODELS if m != model_to_use]

    last_error = None
    for candidate in candidate_models:
        try:
            completion = ai_client.chat.completions.create(
                model=candidate,
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
            return completion.choices[0].message.content
        except Exception as e:
            last_error = e
            logger.warning(f"AI model '{candidate}' ishlamadi, keyingisi sinaladi: {e}")

    logger.error(f"Groq AI xatosi (barcha modellar sinaldi): {last_error}")
    if image_data_uri:
        return f"{AI_NAME}: Rasmni tahlil qila olmadim, birozdan song qayta urinib koring."
    return f"{AI_NAME}: Hozir javob bera olmadim, birozdan song qayta urinib koring."


def _build_ai_messages(prompt, context, user, extra_system_note, image_data_uri):
    """get_ai_response va stream_ai_response uchun umumiy xabar/model tayyorlash mantigi."""
    style_notes = get_user_ai_style_notes(user)
    bond_note = get_bond_prompt_note(user)
    system_content = SYSTEM_PROMPT
    if bond_note:
        system_content += " " + bond_note
    if style_notes:
        system_content += " " + style_notes
    if extra_system_note:
        system_content += " " + extra_system_note
    if image_data_uri:
        system_content += (
            " Foydalanuvchi sizga rasm yubordi. Rasmni diqqat bilan tahlil qilib, "
            "aniq va foydali javob bering."
        )

    messages = [{"role": "system", "content": system_content}]

    if context:
        for item in context[-14:]:
            role = "assistant" if item.get("isAI") else "user"
            text = (item.get("message") or "").strip()
            if text:
                messages.append({"role": role, "content": text})

    if image_data_uri:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt.strip()},
                {"type": "image_url", "image_url": {"url": image_data_uri}}
            ]
        })
        model_to_use = GROQ_VISION_MODEL
    else:
        messages.append({"role": "user", "content": prompt.strip()})
        model_to_use = AI_MODEL

    return messages, model_to_use


def stream_ai_response(prompt: str, context=None, user=None, extra_system_note=None,
                        image_data_uri=None, on_chunk=None, max_tokens=1024, reasoning_effort=None,
                        temperature=0.7) -> str:
    """AI javobini boâ€˜lak-boâ€˜lak (stream) generatsiya qiladi, har bir boâ€˜lakni on_chunk'ga yuboradi.
    ChatGPT/Gemini'dagidek 'jonli yozilayotgan' effekt uchun."""
    if not ai_client:
        text = f"{AI_NAME}: Hozircha ulanmagan — server tomonida API kalit sozlanmagan."
        if on_chunk:
            on_chunk(text)
        return text

    if (not prompt or not prompt.strip()) and image_data_uri:
        prompt = "Bu rasmda nima borligini tasvirlab ber va u haqida qiziqarli fikr bildir."

    if not prompt or not prompt.strip():
        text = f"{AI_NAME}: Savolingizni yozing, men yordam berishga tayyorman!"
        if on_chunk:
            on_chunk(text)
        return text

    messages, model_to_use = _build_ai_messages(prompt, context, user, extra_system_note, image_data_uri)

    extra_kwargs = {}
    if reasoning_effort and not image_data_uri and "gpt-oss" in model_to_use.lower():
        extra_kwargs["reasoning_effort"] = reasoning_effort

    # Rasm bor bolsa, asosiy vizual model ishlamay qolgan holatlar uchun (masalan Groq
    # modelni eskirtirib qoysa) zaxira modellarni ham sinab koramiz.
    candidate_models = [model_to_use]
    if image_data_uri:
        candidate_models += [m for m in GROQ_VISION_FALLBACK_MODELS if m != model_to_use]

    full_text = ""
    started_streaming = False
    last_error = None

    for candidate in candidate_models:
        try:
            stream = ai_client.chat.completions.create(
                model=candidate,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **extra_kwargs
            )
            for chunk in stream:
                delta = ""
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    started_streaming = True
                    full_text += delta
                    if on_chunk:
                        on_chunk(delta)

            if full_text.strip():
                return full_text
            if started_streaming:
                break
            last_error = "boâ€˜sh javob qaytdi"

        except Exception as e:
            last_error = e
            logger.warning(f"AI model '{candidate}' ishlamadi, keyingisi sinaladi: {e}")
            if started_streaming:
                break

    logger.error(f"Groq AI oqim xatosi (barcha modellar sinaldi): {last_error}")
    fallback = (f"{AI_NAME}: Rasmni tahlil qila olmadim, birozdan song qayta urinib koring."
                if image_data_uri else
                f"{AI_NAME}: Hozir javob bera olmadim, birozdan song qayta urinib koring.")
    if on_chunk:
        on_chunk(fallback)
    return fallback


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


def update_user_streak(user):
    """Foydalanuvchi kunlik faollik ketma-ketligini (streak) yangilaydi."""
    today = datetime.utcnow().date()

    if user.last_active_date == today:
        return

    if user.last_active_date == today - timedelta(days=1):
        user.streak_count = (user.streak_count or 0) + 1
    else:
        user.streak_count = 1

    user.last_active_date = today
    db.session.commit()


def get_or_create_daily_quote():
    """Har kunga bitta AI tomonidan yaratilgan qisqa fikr — butun sayt uchun bir marta generatsiya qilinadi."""
    today = datetime.utcnow().date()
    existing = DailyQuote.query.filter_by(quote_date=today).first()
    if existing:
        return existing.text

    text = get_ai_response(
        "Bugungi kun uchun ozbek tilida, 20 sozdan oshmagan, ilhomlantiruvchi yoki foydali qisqa fikr yoz. "
        "Faqat fikrning ozini yoz, kirish yoki izohsiz."
    )

    quote = DailyQuote(quote_date=today, text=text.strip())
    db.session.add(quote)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = DailyQuote.query.filter_by(quote_date=today).first()
        if existing:
            return existing.text

    return text.strip()


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


@app.after_request
def add_no_cache_headers(response):
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.route('/')
def index():
    user = current_user()
    if user:
        update_user_streak(user)
    display_avatar = get_display_avatar(user) if user else None
    is_admin = is_admin_user(user)
    show_onboarding = bool(user and not user.onboarding_seen)
    return render_template('index.html', user=user, display_avatar=display_avatar,
                            anon_limit=ANONYMOUS_MESSAGE_LIMIT, is_admin=is_admin,
                            show_onboarding=show_onboarding, v=STATIC_VERSION,
                            tts_enabled=bool(ELEVENLABS_API_KEY))


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


@app.route('/sw.js')
def service_worker():
    response = app.send_static_file('sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    return response


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
            "is_mine": (not m.is_ai) and m.sender_id == user.id,
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


@app.route('/api/onboarding/seen', methods=['POST'])
@login_required_api
def api_onboarding_seen():
    user = current_user()
    user.onboarding_seen = True
    db.session.commit()
    return jsonify({"success": True})


@app.route('/api/announcements')
def api_announcements():
    items = Announcement.query.order_by(Announcement.created_at.desc()).limit(50).all()
    return jsonify([{
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "time": a.created_at.strftime("%Y-%m-%d %H:%M")
    } for a in items])


@app.route('/api/daily-quote')
def api_daily_quote():
    text = get_or_create_daily_quote()
    return jsonify({"text": text, "date": datetime.utcnow().strftime("%Y-%m-%d")})


@app.route('/api/tasks', methods=['GET'])
@login_required_api
def api_list_tasks():
    user = current_user()
    tasks = Task.query.filter_by(user_id=user.id).order_by(Task.created_at.asc()).all()
    return jsonify([{
        "id": t.id, "text": t.text, "is_done": t.is_done
    } for t in tasks])


@app.route('/api/tasks', methods=['POST'])
@login_required_api
def api_create_task():
    user = current_user()
    data = request.get_json() or {}
    text = (data.get('text') or '').strip()[:300]
    if not text:
        return jsonify({"error": "empty_text"}), 400

    task = Task(user_id=user.id, text=text)
    db.session.add(task)
    db.session.commit()
    return jsonify({"success": True, "id": task.id, "text": task.text, "is_done": False})


@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required_api
def api_toggle_task(task_id):
    user = current_user()
    task = db.session.get(Task, task_id)
    if not task or task.user_id != user.id:
        return jsonify({"error": "not_found"}), 404
    task.is_done = not task.is_done
    db.session.commit()
    return jsonify({"success": True, "is_done": task.is_done})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required_api
def api_delete_task(task_id):
    user = current_user()
    task = db.session.get(Task, task_id)
    if not task or task.user_id != user.id:
        return jsonify({"error": "not_found"}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({"success": True})


@app.route('/api/saved-messages', methods=['GET'])
@login_required_api
def api_list_saved_messages():
    user = current_user()
    items = SavedMessage.query.filter_by(user_id=user.id).order_by(SavedMessage.created_at.desc()).all()
    return jsonify([{
        "id": s.id, "content": s.content, "time": s.created_at.strftime("%Y-%m-%d %H:%M")
    } for s in items])


@app.route('/api/saved-messages', methods=['POST'])
@login_required_api
def api_create_saved_message():
    user = current_user()
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()[:4000]
    if not content:
        return jsonify({"error": "empty_content"}), 400

    saved = SavedMessage(user_id=user.id, content=content)
    db.session.add(saved)
    db.session.commit()
    return jsonify({"success": True, "id": saved.id})


@app.route('/api/saved-messages/<int:saved_id>', methods=['DELETE'])
@login_required_api
def api_delete_saved_message(saved_id):
    user = current_user()
    saved = db.session.get(SavedMessage, saved_id)
    if not saved or saved.user_id != user.id:
        return jsonify({"error": "not_found"}), 404
    db.session.delete(saved)
    db.session.commit()
    return jsonify({"success": True})


@app.route('/api/my-activity')
@login_required_api
def api_my_activity():
    user = current_user()

    dm_count = DirectMessage.query.filter_by(sender_id=user.id).count()
    group_msg_count = GroupMessage.query.filter_by(sender_id=user.id, is_ai=False).count()
    friends_count = FriendRequest.query.filter(
        db.or_(FriendRequest.sender_id == user.id, FriendRequest.receiver_id == user.id),
        FriendRequest.status == 'accepted'
    ).count()
    groups_count = GroupMember.query.filter_by(user_id=user.id).count()

    return jsonify({
        "streak_count": user.streak_count or 0,
        "joined_date": user.created_at.strftime("%Y-%m-%d") if user.created_at else '',
        "friend_messages_sent": dm_count,
        "group_messages_sent": group_msg_count,
        "friends_count": friends_count,
        "groups_count": groups_count
    })


@app.route('/api/ai/bond')
def api_ai_bond():
    user = current_user()
    info = get_bond_info(user)
    if not info:
        return jsonify({"logged_in": False})
    return jsonify(dict(info, logged_in=True))


@app.route('/api/quick-prompts')
def api_quick_prompts():
    return jsonify([
        {"label": "😂 Hazil ayt", "prompt": "Menga qiziqarli va kulgili hazil ayt."},
        {"label": "💡 Fikr ber", "prompt": "Bugungi kun uchun foydali maslahat ber."},
        {"label": "📚 Tushuntir", "prompt": "Menga murakkab mavzuni sodda tilda tushuntirib ber."},
        {"label": "💻 Kod yordami", "prompt": "Menga dasturlashda yordam kerak."},
        {"label": "✍️ Matn yoz", "prompt": "Menga qisqa va tasirli matn yozib ber."},
        {"label": "🎯 Motivatsiya", "prompt": "Menga bugun uchun motivatsion soz ayt."}
    ])


@app.route('/api/tts', methods=['POST'])
def api_tts():
    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "tts_not_configured"}), 503

    data = request.get_json() or {}
    text = (data.get('text') or '').strip()[:1000]
    voice_id = data.get('voice_id') or ELEVENLABS_VOICE_ID
    mood = data.get('mood') or 'neutral'

    if not text:
        return jsonify({"error": "empty_text"}), 400

    mood_settings = {
        "happy": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.7},
        "annoyed": {"stability": 0.7, "similarity_boost": 0.7, "style": 0.2},
        "neutral": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.4}
    }
    settings = mood_settings.get(mood, mood_settings["neutral"])

    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": settings
            },
            timeout=20
        )

        if resp.status_code == 200:
            return app.response_class(resp.content, mimetype='audio/mpeg')

        logger.error(f"ElevenLabs TTS xatosi: {resp.status_code} {resp.text[:200]}")
        return jsonify({"error": "tts_failed"}), 502

    except Exception as e:
        logger.error(f"ElevenLabs TTS xatosi: {e}")
        return jsonify({"error": "tts_failed"}), 502


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
        history=list(public_history)[::-1],
        v=STATIC_VERSION
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
    title = (data.get('title') or '').strip()[:150]

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

    announcement = Announcement(title=title or None, message=text)
    db.session.add(announcement)
    db.session.commit()

    socketio.emit('public_response_message', entry)
    socketio.emit('announcement_created', {
        "id": announcement.id,
        "title": announcement.title,
        "message": announcement.message,
        "time": announcement.created_at.strftime("%Y-%m-%d %H:%M")
    })

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
    image_data_uri = data.get('image')
    is_code_mode = data.get('chatType') == 'code'

    if image_data_uri:
        if not isinstance(image_data_uri, str) or not image_data_uri.startswith('data:image/'):
            image_data_uri = None
        else:
            mime = image_data_uri.split(';')[0].replace('data:', '')
            if mime not in ALLOWED_CHAT_IMAGE_TYPES:
                image_data_uri = None
            elif len(image_data_uri) > MAX_CHAT_IMAGE_SIZE * 1.4:
                emit('ai_response_message', {
                    'username': AI_NAME, 'message': f"{AI_NAME}: Rasm hajmi juda katta (4MB dan oshmasin).",
                    'isAI': True
                })
                return

    if not msg and not image_data_uri:
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
    logger.info(f"[AI-shaxsiy] {username}: {msg}{' [+rasm]' if image_data_uri else ''}")

    emit('ai_response_message', {
        'username': username, 'message': msg, 'isAI': False, 'clientId': client_id,
        'image': image_data_uri
    })

    emit('ai_typing', {'typing': True})
    user = current_user()

    stream_id = 'strm_' + str(next(public_msg_counter)) + '_' + str(int(datetime.utcnow().timestamp() * 1000))
    emit('ai_stream_start', {'streamId': stream_id})
    emit('ai_typing', {'typing': False})

    def on_chunk(delta):
        emit('ai_stream_chunk', {'streamId': stream_id, 'chunk': delta})
        socketio.sleep(0)

    ai_reply = stream_ai_response(
        msg, context, user=user, image_data_uri=image_data_uri, on_chunk=on_chunk,
        extra_system_note=(CODE_MODE_SYSTEM_NOTE if is_code_mode else None),
        max_tokens=(8192 if is_code_mode else 1024),
        reasoning_effort=('high' if is_code_mode else None)
    )
    emit('ai_stream_done', {'streamId': stream_id, 'message': ai_reply, 'prompt': msg})

    if user:
        bond_info, leveled_up = register_ai_interaction(user)
        emit('bond_update', dict(bond_info, leveled_up=leveled_up))


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