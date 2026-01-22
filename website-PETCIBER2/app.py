from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
import sqlite3
import re
from flask import Response
from flask_socketio import SocketIO, join_room, leave_room, send, emit
from flask import render_template_string
from werkzeug.utils import secure_filename
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

DB_PATH = os.path.join(os.path.dirname(__file__), "petciber.db")

def inicializar_banco():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        # Tabela de tutores
        c.execute("""
        CREATE TABLE IF NOT EXISTS tutores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            telefone TEXT,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Tabela de pets
        c.execute("""
        CREATE TABLE IF NOT EXISTS pets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            raca TEXT,
            historico TEXT,
            foto TEXT,
            dono_email TEXT,
            tag_uid TEXT UNIQUE
        )
        """)

        # Tabela de vitais
        c.execute("""
        CREATE TABLE IF NOT EXISTS vitais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id INTEGER NOT NULL,
            bpm REAL NOT NULL,
            temp REAL NOT NULL,
            ts INTEGER NOT NULL,
            FOREIGN KEY(pet_id) REFERENCES pets(id)
        )
        """)

        # Tabela de eventos
        c.execute("""
        CREATE TABLE IF NOT EXISTS eventos_pet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_evento TEXT NOT NULL,
            data_evento TEXT NOT NULL,
            tipo TEXT NOT NULL,
            pet_id INTEGER NOT NULL,
            carteirinha_path TEXT,
            carteirinha_url TEXT,
            notificado INTEGER DEFAULT 0,
            FOREIGN KEY(pet_id) REFERENCES pets(id)
        )
        """)

        # Tabela de dispositivos
        c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_uid TEXT UNIQUE NOT NULL,
            pet_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(pet_id) REFERENCES pets(id)
        )
        """)

        conn.commit()
        print("✅ Banco inicializado com sucesso:", DB_PATH)

# Rodar antes de iniciar o Flask
inicializar_banco()

# Adicionando coluna foto caso não exista
with sqlite3.connect(DB_PATH) as conn:
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE pets ADD COLUMN foto TEXT")
        print("Coluna 'foto' adicionada à tabela pets.")
    except sqlite3.OperationalError:
        # coluna já existe
        print("Coluna 'foto' já existe.")
    conn.commit()

with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS tutores")
    conn.commit()



# --- Fim da inicialização do banco ---

# Agora sim, podemos importar Flask e outros módulos
from flask import Flask, render_template, request, redirect, url_for, session, flash
# resto do código...

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, date
import smtplib, ssl, json, requests, random, time, socket
from email.message import EmailMessage

# APScheduler (opcional)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _HAS_APSCHEDULER = True
except Exception:
    _HAS_APSCHEDULER = False

# Web Push (opcional)
try:
    from pywebpush import webpush, WebPushException
    _HAS_WEBPUSH = True
except Exception:
    _HAS_WEBPUSH = False

# ----------------------------------------------------------------------------
# App / Config
# ----------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_segura")

DB_PATH = os.environ.get("DB_PATH", "petciber.db")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB upload
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
DB_PATH = os.path.join(os.path.dirname(__file__), "petciber.db")
# Tempo real
socketio = SocketIO(app, cors_allowed_origins="*")

# Rate limit global + por rota
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"])

# API Key de ingestão (troque em produção)
API_KEY = os.environ.get("API_KEY", "PETCIBER123")

# SMTP (defina no ambiente)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER or "no-reply@petciber.local")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").rstrip("/")

# VAPID (Web Push)
VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS      = os.environ.get("VAPID_CLAIMS", "mailto:contato@petciber.com")

# ---------- Baltic Pets (catálogo + imagens + preços PF sugeridos) ----------
BALTIC_PRODUCTS = [
    # 250 g
    {"sku": "biotapet250",  "name": "BiotaPet 250 g",   "price": 97.71,  "img": "produtos/baltic_biotapet_250.jpg"},
    {"sku": "shinepet250",  "name": "ShinePet 250 g",   "price": 88.81,  "img": "produtos/baltic_shinepet_250.jpg"},
    {"sku": "defense250",   "name": "DefensePet 250 g", "price": 92.81,  "img": "produtos/baltic_defensepet_250.jpg"},
    {"sku": "sereni250",    "name": "SereniPet 250 g",  "price": 106.15, "img": "produtos/baltic_serenipet_250.jpg"},
    {"sku": "joint250",     "name": "JointPet 250 g",   "price": 120.80, "img": "produtos/baltic_jointpet_250.jpg"},

    # 75 g
    {"sku": "biotapet75",   "name": "BiotaPet 75 g",    "price": 47.92,  "img": "produtos/baltic_biotapet_75.jpg"},
    {"sku": "shinepet75",   "name": "ShinePet 75 g",    "price": 43.56,  "img": "produtos/baltic_shinepet_75.jpg"},
    {"sku": "defense75",    "name": "DefensePet 75 g",  "price": 45.52,  "img": "produtos/baltic_defensepet_75.jpg"},
    {"sku": "sereni75",     "name": "SereniPet 75 g",   "price": 52.05,  "img": "produtos/baltic_serenipet_75.jpg"},
    {"sku": "joint75",      "name": "JointPet 75 g",    "price": 59.24,  "img": "produtos/baltic_jointpet_75.jpg"},

    # 40 g
    {"sku": "artic40",      "name": "ArticPet 40 g",    "price": 88.48,  "img": "produtos/baltic_articpet_40.jpg"},
]
BALTIC_COUPON = {"code": "BALTIC10", "percent": 10}

# ----------------------------------------------------------------------------
# Static / Uploads (carteirinhas) + logo de fallback
# ----------------------------------------------------------------------------
STATIC_DIR = app.static_folder or "static"
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads", "carteirinhas")
os.makedirs(UPLOAD_DIR, exist_ok=True)

BRAND_DIR = os.path.join(STATIC_DIR, "brand")
os.makedirs(BRAND_DIR, exist_ok=True)
BRAND_LOGO = os.path.join(BRAND_DIR, "logo.png")
if not os.path.isfile(BRAND_LOGO):
    import base64
    _px = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAukB9WbV2gAAAABJRU5ErkJggg=="
    with open(BRAND_LOGO, "wb") as f:
        f.write(base64.b64decode(_px))

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
def _allowed(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT

# ----------------------------------------------------------------------------
# Helpers de DB
# ----------------------------------------------------------------------------
def _ensure_column(conn, table: str, coldef: str):
    """Adiciona uma coluna se não existir (idempotente)."""
    colname = coldef.split()[0].strip()
    c = conn.cursor()
    c.execute(f"PRAGMA table_info('{table}')")
    cols = [row[1] for row in c.fetchall()]
    if colname in cols:
        return
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            pass
        else:
            raise

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                raca TEXT NOT NULL,
                historico TEXT,
                dono_email TEXT NOT NULL,
                tag_uid TEXT UNIQUE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS vitais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pet_id INTEGER NOT NULL,
                bpm REAL NOT NULL,
                temp REAL NOT NULL,
                ts INTEGER NOT NULL,
                FOREIGN KEY(pet_id) REFERENCES pets(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS eventos_pet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_evento TEXT NOT NULL,
                data_evento TEXT NOT NULL,
                tipo TEXT NOT NULL,
                pet_id INTEGER NOT NULL,
                carteirinha_path TEXT,
                carteirinha_url  TEXT,
                notificado INTEGER DEFAULT 0,
                FOREIGN KEY (pet_id) REFERENCES pets(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS push_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_uid TEXT UNIQUE NOT NULL,
                pet_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(pet_id) REFERENCES pets(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price REAL NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT NOT NULL,
                coupon TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("PRAGMA table_info(pets)")
        colunas = [info[1] for info in c.fetchall()]
        if "foto" not in colunas:
            c.execute("ALTER TABLE pets ADD COLUMN foto TEXT")

init_db()

@app.route("/debug/seed")
def debug_seed():
    # cria usuário e 1 pet, sem duplicar
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO usuarios(email, senha) VALUES(?,?)",
                  ("demo@petciber.com", "123"))
        c.execute("SELECT 1 FROM pets WHERE dono_email=? LIMIT 1", ("demo@petciber.com",))
        if not c.fetchone():
            c.execute("INSERT INTO pets(nome, raca, historico, dono_email) VALUES(?,?,?,?)",
                      ("Mel", "Bulldog Francês", "Pet saudável, vacinas em dia.", "demo@petciber.com"))
        conn.commit()
    session["usuario"] = "demo@petciber.com"
    return redirect(url_for("dashboard"))

# ----------------------------------------------------------------------------
# Contexto global (ano)
# ----------------------------------------------------------------------------
@app.context_processor
def inject_year():
    return {"year": datetime.now().year}

# ----------------------------------------------------------------------------
# Domínio (IA de estado emocional / vitais)
# ----------------------------------------------------------------------------
def analisar_comportamento(bpm, temp_corporal, temp_ambiente, atividade):
    if bpm > 140 or atividade == "alta":
        if temp_corporal > 39:
            return "Estressado"
        return "Agitado"
    elif bpm < 80 and temp_corporal < 37:
        return "Sonolento"
    elif 80 <= bpm <= 110 and 37 <= temp_corporal <= 39:
        return "Calmo"
    else:
        return "Observação necessária"

def analisar_vitais_pet(bpm: float, temp: float):
    alertas, previsoes = [], []
    if bpm < 60:
        alertas.append("Bradicardia")
        previsoes.append("Possível fraqueza/hipotireoidismo/desidratação")
    elif bpm > 140:
        alertas.append("Taquicardia")
        previsoes.append("Pode indicar estresse/dor/IC/febre")
    if temp < 37:
        alertas.append("Hipotermia")
        previsoes.append("Exposição ao frio/choque/doença grave")
    elif 39.5 < temp <= 41:
        alertas.append("Febre")
        previsoes.append("Infecção/inflamação/doença sistêmica")
    elif temp > 41:
        alertas.append("Hipertermia grave")
        previsoes.append("Emergência veterinária imediata")
    if bpm > 140 and temp > 39.5:
        previsoes.append("Infecção grave ou dor aguda (combinação)")
    if bpm < 60 and temp < 37:
        previsoes.append("Risco de choque (combinação)")
    if not alertas:
        previsoes.append("Pet saudável ✅")
    return alertas, previsoes

# ----------------------------------------------------------------------------
# Util: sala SocketIO por pet
# ----------------------------------------------------------------------------
def pet_room(pet_id: int) -> str:
    return f"pet_{int(pet_id)}"

# ----------------------------------------------------------------------------
# E-mail
# ----------------------------------------------------------------------------
def send_email(to_email: str, subject: str, html_body: str) -> None:
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and MAIL_FROM):
        print("[EMAIL] SMTP não configurado. Pular envio para:", to_email)
        return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content("Seu cliente não suporta HTML.")
    msg.add_alternative(html_body, subtype="html")
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def _link_carteirinha(cpath: str | None, curl: str | None) -> str:
    if curl:
        return f'<p>Carteirinha: <a href="{curl}" target="_blank">abrir</a></p>'
    if cpath:
        if SITE_BASE_URL:
            return f'<p>Carteirinha: <a href="{SITE_BASE_URL}/static/{cpath}" target="_blank">abrir</a></p>'
        return f'<p>Carteirinha em /static/{cpath}</p>'
    return ""

# ----------------------------------------------------------------------------
# Web Push
# ----------------------------------------------------------------------------
def save_push_subscription(user_email: str, subscription: dict) -> None:
    if not subscription or not subscription.get("endpoint"):
        return
    endpoint = subscription["endpoint"]
    keys = subscription.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth   = keys.get("auth", "")
    if not (p256dh and auth):
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO push_subs (user_email, endpoint, p256dh, auth)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                user_email=excluded.user_email,
                p256dh=excluded.p256dh,
                auth=excluded.auth
        """, (user_email, endpoint, p256dh, auth))
        conn.commit()

def send_push_to_user(user_email: str, title: str, body: str, url_open: str = "/agenda"):
    if not (_HAS_WEBPUSH and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY):
        print("[PUSH] WebPush desativado (biblioteca/keys ausentes).")
        return
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": f"{SITE_BASE_URL or ''}/static/brand/logo.png",
        "badge": f"{SITE_BASE_URL or ''}/static/brand/logo.png",
        "url": f"{SITE_BASE_URL}{url_open}" if SITE_BASE_URL else url_open
    })
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, endpoint, p256dh, auth FROM push_subs WHERE user_email=?", (user_email,))
        rows = c.fetchall()
        for pid, endpoint, p256dh, auth in rows:
            sub = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_CLAIMS}
                )
            except WebPushException as e:
                print("[PUSH][erro]", e)
                if hasattr(e, "response") and e.response and e.response.status_code in (404, 410):
                    try:
                        c.execute("DELETE FROM push_subs WHERE id=?", (pid,))
                        conn.commit()
                    except:
                        pass

# ----------------------------------------------------------------------------
# Lembretes (e-mail + push) no dia do evento
# ----------------------------------------------------------------------------
def send_due_event_emails() -> dict:
    hoje = date.today().isoformat()
    enviados, erros = 0, 0
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT e.id, e.nome_evento, e.data_evento, e.tipo,
                   p.nome AS pet_nome, p.dono_email,
                   e.carteirinha_path, e.carteirinha_url
            FROM eventos_pet e
            JOIN pets p ON p.id = e.pet_id
            WHERE e.data_evento = ? AND (e.notificado IS NULL OR e.notificado = 0)
        """, (hoje,))
        rows = c.fetchall()
        for (eid, nome_evento, data_evento, tipo, pet_nome, dono_email, cpath, curl) in rows:
            try:
                assunto = f"Lembrete PETCIBER: {tipo.title()} de {pet_nome} hoje"
                corpo = f"""
                <div style="font-family:Arial,Helvetica,sans-serif">
                  <h2>Olá!</h2>
                  <p>Este é um lembrete da <b>Agenda Inteligente</b>:</p>
                  <ul>
                    <li><b>Evento:</b> {nome_evento}</li>
                    <li><b>Tipo:</b> {tipo.title()}</li>
                    <li><b>Pet:</b> {pet_nome}</li>
                    <li><b>Data:</b> {data_evento}</li>
                  </ul>
                  {_link_carteirinha(cpath, curl)}
                  <p>Boas-vindas e bons cuidados com seu pet! 🐾</p>
                </div>
                """
                send_email(dono_email, assunto, corpo)
                try:
                    titulo = f"Lembrete: {tipo.title()} de {pet_nome} é hoje"
                    resumo = f"{nome_evento} • {data_evento}"
                    send_push_to_user(dono_email, titulo, resumo, url_open="/agenda")
                except Exception as e:
                    print("[PUSH][evento] erro:", e)
                c.execute("UPDATE eventos_pet SET notificado = 1 WHERE id = ?", (eid,))
                enviados += 1
            except Exception as e:
                print("[EMAIL/PUSH][ERRO]", e)
                erros += 1
        conn.commit()
    return {"enviados": enviados, "erros": erros}

if _HAS_APSCHEDULER:
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(send_due_event_emails, "cron", hour=8, minute=0)
        scheduler.start()
        print("[Scheduler] Lembrete diário de eventos ativado (08:00).")
    except Exception as e:
        print("[Scheduler] Falha ao iniciar:", e)

# ----------------------------------------------------------------------------
# NLU gratuita (Wit.ai) – opcional
# ----------------------------------------------------------------------------
WIT_TOKEN = os.environ.get("WIT_TOKEN", "")
def wit_parse(texto: str):
    if not WIT_TOKEN or not texto:
        return None, {}
    try:
        r = requests.get(
            "https://api.wit.ai/message",
            params={"q": texto},
            headers={"Authorization": f"Bearer {WIT_TOKEN}"},
            timeout=10
        )
        j = r.json() or {}
        intent = None
        if j.get("intents"):
            intent = j["intents"][0].get("name")
        ents = {}
        for k, v in (j.get("entities") or {}).items():
            if not v:
                continue
            val = v[0].get("value")
            if val is None:
                val = v[0].get("body")
            ents[k.lower()] = (str(val).strip().lower() if isinstance(val, str) else val)
        return (intent.lower() if intent else None), ents
    except Exception:
        return None, {}

# ----------------------------------------------------------------------------
# Rotas principais
# ----------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("login"))

from werkzeug.security import generate_password_hash
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]
        confirmar = request.form["confirmar"]
        telefone = request.form.get("telefone", "").strip()

        if senha != confirmar:
            flash("❌ As senhas não coincidem.", "danger")
            return redirect(url_for("cadastro"))

        # Cria hash seguro da senha
        senha_hash = generate_password_hash(senha)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO usuarios (nome, email, senha, telefone)
                    VALUES (?, ?, ?, ?)
                """, (nome, email, senha_hash, telefone))
                conn.commit()
                flash("✅ Cadastro realizado com sucesso! Faça login.", "success")
                return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("⚠️ Este e-mail já está cadastrado.", "warning")
            return redirect(url_for("cadastro"))

    return render_template("cadastro.html")


# --- Rota de login ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT senha, nome FROM usuarios WHERE email = ?", (email,))
            row = cursor.fetchone()

            if row and check_password_hash(row[0], senha):
                session["usuario"] = email
                flash("✅ Login realizado com sucesso!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("⚠️ E-mail ou senha incorretos.", "danger")
                return redirect(url_for("login"))

    return render_template("login.html")

# ===============================
# 📦 Loja Baltic Pets (dados fixos)
# ===============================

BALTIC_PRODUCTS = [
    {"name": "BiotaPet 250 g", "price": 97.71, "img": "biotapet.jpeg", "sku": "biota250"},
    {"name": "ShinePet 250 g", "price": 88.81, "img": "shinepet.jpeg", "sku": "shine250"},
    {"name": "DefensePet 250 g", "price": 92.81, "img": "defensepet.jpeg", "sku": "defense250"},
    {"name": "SereniPet 250 g", "price": 106.15, "img": "serenipet.jpeg", "sku": "sereni250"},
    {"name": "ArticPet 40 g", "price": 88.48, "img": "articpet.jpeg", "sku": "artic40"}
]

BALTIC_COUPON = {"code": "BALTIC10", "percent": 10}

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))

    dono_email = session["usuario"]
    pets_com_dados = []

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # 🔹 Busca o nome do tutor pelo e-mail
        cursor.execute("SELECT nome_completo FROM usuarios WHERE email = ?", (dono_email,))
        resultado = cursor.fetchone()
        nome_tutor = resultado[0] if resultado and resultado[0] else "Tutor"

        # 🔹 Busca os pets do tutor
        cursor.execute("SELECT id, nome, raca, historico, foto FROM pets WHERE dono_email = ?", (dono_email,))
        pets = cursor.fetchall()

    # 🔹 Gera dados simulados e alertas
    for pet_id, nome, raca, historico, foto in pets:
        bpm = random.randint(60, 150)
        temp_corporal = round(random.uniform(36.0, 40.0), 1)
        temp_ambiente = round(random.uniform(22.0, 28.0), 1)
        atividade = random.choice(["baixa", "moderada", "alta"])
        estado_emocional = analisar_comportamento(bpm, temp_corporal, temp_ambiente, atividade)

        alertas = []
        if bpm < 70 or bpm > 140:
            alertas.append(f"Atenção: Batimentos anormais ({bpm} bpm)")
        if temp_corporal < 36.5 or temp_corporal > 39.5:
            alertas.append(f"Atenção: Temperatura fora do ideal ({temp_corporal}°C)")
        if estado_emocional in ["Estressado", "Observação necessária"]:
            alertas.append(f"Alerta: Estado emocional '{estado_emocional}'")

        pets_com_dados.append({
            "id": pet_id,
            "nome": nome,
            "raca": raca,
            "historico": historico,
            "foto": foto,
            "bpm": bpm,
            "temp_corporal": temp_corporal,
            "alertas": alertas,
            "estado_emocional": estado_emocional
        })

    # 🔹 Catálogo de produtos
    produtos = [
        {"nome": "ArticPet", "preco": 89.90, "imagem": "static/img/produtos/articpet.jpeg"},
        {"nome": "BioTaPet", "preco": 79.90, "imagem": "static/img/produtos/biotapet.jpeg"},
        {"nome": "DefensePet", "preco": 99.90, "imagem": "static/img/produtos/defensepet.jpeg"},
        {"nome": "JointPet", "preco": 84.90, "imagem": "static/img/produtos/jointpet.jpeg"},
        {"nome": "SereniPet", "preco": 69.90, "imagem": "static/img/produtos/serenipet.jpeg"},
        {"nome": "ShinePet", "preco": 74.90, "imagem": "static/img/produtos/shinepet.jpeg"},
    ]

    BALTIC_COUPON = {"code": "PETCIBER10", "percent": 10}

    return render_template(
        "dashboard.html",
        nome_tutor=nome_tutor,
        pets=pets_com_dados,
        cupom=BALTIC_COUPON,
        produtos=produtos
    )

@app.route("/add_to_cart/<sku>", methods=["POST"])
def add_to_cart(sku):
    if "cart" not in session:
        session["cart"] = []
    qty = int(request.form.get("qty", 1))
    session["cart"].append({"sku": sku, "qty": qty})
    session.modified = True
    flash("Produto adicionado ao carrinho!", "success")
    return redirect(url_for("dashboard"))

from flask import Flask, session, redirect, url_for, request, render_template, flash

# Adicionar produto ao carrinho
@app.route("/adicionar_carrinho", methods=["POST"])
def adicionar_carrinho():
    sku = request.form.get("sku")
    nome = request.form.get("nome")
    price = float(request.form.get("price"))
    qty = int(request.form.get("qty", 1))
    img = request.form.get("img")

    if "carrinho" not in session:
        session["carrinho"] = []

    # Se o produto já existe, apenas soma a quantidade
    for item in session["carrinho"]:
        if item["sku"] == sku:
            item["qty"] += qty
            break
    else:
        session["carrinho"].append({
            "sku": sku,
            "name": nome,
            "price": price,
            "qty": qty,
            "img": img
        })

    session.modified = True
    flash(f"{nome} adicionado ao carrinho!", "success")
    return redirect(url_for("dashboard"))

# ================= Ver carrinho =================
@app.route("/carrinho")
def ver_carrinho():
    carrinho = session.get("carrinho", [])
    total = sum(item["price"] * item["qty"] for item in carrinho)
    return render_template("carrinho.html", carrinho=carrinho, total=total)

# ================= Remover item =================
@app.route("/remover_carrinho/<sku>")
def remover_carrinho(sku):
    carrinho = session.get("carrinho", [])
    carrinho = [item for item in carrinho if item["sku"] != sku]
    session["carrinho"] = carrinho
    session.modified = True
    flash("Produto removido do carrinho.", "warning")
    return redirect(url_for("ver_carrinho"))

# ================= Limpar carrinho =================
@app.route("/limpar_carrinho")
def limpar_carrinho():
    session["carrinho"] = []
    session.modified = True
    flash("Carrinho limpo.", "info")
    return redirect(url_for("ver_carrinho"))

# ================= Finalizar compra =================
@app.route("/finalizar_compra")
def finalizar_compra():
    # Apenas mockup de finalização
    carrinho = session.get("carrinho", [])
    if not carrinho:
        flash("Seu carrinho está vazio.", "warning")
        return redirect(url_for("dashboard"))

    total = sum(item["price"] * item["qty"] for item in carrinho)
    session["carrinho"] = []  # Limpa após compra
    session.modified = True
    flash(f"Compra finalizada! Total pago: R$ {total:.2f}", "success")
    return redirect(url_for("dashboard"))

@app.route("/loja")
def loja():
    return render_template("loja.html")

racas = [
    "SRD (Vira-lata)", "Shih Tzu", "Spitz Alemão (Lulu da Pomerânia)",
    "Buldogue Francês", "Poodle", "Yorkshire Terrier", "Golden Retriever",
    "Labrador Retriever", "Lhasa Apso", "Pug", "Rottweiler",
    "Dachshund (Salsicha)", "Pastor Alemão", "Border Collie", "Maltês",
    "Pinscher (Miniatura)", "Fila Brasileiro (Raça Nacional)", "Cocker Spaniel Inglês",
    "Chihuahua", "Pitbull (American Pit Bull Terrier e variações)",
    # ... continue com todas as outras raças ...
    "Vira-lata Caramelo (Mascote cultural e variação de SRD)"
]

@app.route("/cadastrar_pet", methods=["GET", "POST"])
def cadastrar_pet():
    if "usuario" not in session:
        return redirect(url_for("login"))

    # salvar novo pet
    if request.method == "POST":
        nome = request.form["nome"]
        raca = request.form["raca"]
        historico = request.form.get("historico", "")
        foto = None

        # salvar foto do pet
        if "foto" in request.files:
            file = request.files["foto"]
            if file and file.filename:
                foto = secure_filename(file.filename)
                upload_path = "static/uploads"
                os.makedirs(upload_path, exist_ok=True)  # garante que a pasta exista
                file.save(os.path.join(upload_path, foto))

        # inserir pet no banco
        con = sqlite3.connect("petciber.db")
        cur = con.cursor()
        cur.execute("""
            INSERT INTO pets (dono_email, nome, raca, historico, foto)
            VALUES (?, ?, ?, ?, ?)
        """, (session["usuario"], nome, raca, historico, foto))
        con.commit()
        con.close()

        flash("Pet cadastrado com sucesso!", "success")
        return redirect(url_for("cadastrar_pet"))

    # carregar pets já cadastrados
    con = sqlite3.connect("petciber.db")
    cur = con.cursor()
    cur.execute("SELECT id, nome, raca, historico, foto FROM pets WHERE dono_email = ?", (session["usuario"],))
    pets = [{"id": r[0], "nome": r[1], "raca": r[2], "historico": r[3], "foto": r[4]} for r in cur.fetchall()]
    con.close()

    racas = ["Labrador", "Poodle", "Bulldog", "Golden Retriever", "SRD", "Shih Tzu", "Yorkshire"]

    return render_template("cadastrar_pet.html", pets=pets, racas=racas)

@app.route("/notificar_pet/<int:id>", methods=["POST"])
def notificar_pet(id):
    if "usuario" not in session:
        return redirect(url_for("login"))
    dono_email = session["usuario"]
    bpm = random.randint(85, 110)
    temp_corporal = round(random.uniform(37.0, 39.5), 1)
    temp_ambiente = round(random.uniform(22.0, 28.0), 1)
    atividade = random.choice(["baixa", "moderada", "alta"])
    estado = analisar_comportamento(bpm, temp_corporal, temp_ambiente, atividade)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor(

        )
        cursor.execute("SELECT * FROM pets WHERE dono_email = ?", (dono_email,))
        pets = cursor.fetchall()
    pets_com_estado = []
    for pet in pets:
        if pet[0] == id:
            pets_com_estado.append((pet[0], pet[1], pet[2], estado))
        else:
            pets_com_estado.append((pet[0], pet[1], pet[2], None))
    flash(f"O tutor foi notificado! Estado do pet '{[p[1] for p in pets if p[0] == id][0]}': {estado}")
    return render_template("cadastrar_pet.html", pets=pets_com_estado)

@app.route("/dados_sensores")
def dados_sensores():
    bpm = random.randint(85, 110)
    temp_corporal = round(random.uniform(37.0, 39.5), 1)
    temp_ambiente = round(random.uniform(22.0, 28.0), 1)
    atividade = random.choice(["baixa", "moderada", "alta"])
    estado_emocional = analisar_comportamento(bpm, temp_corporal, temp_ambiente, atividade)
    return jsonify({
        "bpm": bpm,
        "temp_corporal": temp_corporal,
        "temp_ambiente": temp_ambiente,
        "estado_emocional": estado_emocional
    })

# ------------------------------ CHECKLIST -----------------------------------

@app.route("/checklist", methods=["GET", "POST"])
def checklist():
    if "usuario" not in session:
        return redirect(url_for("login"))
    dono_email = session["usuario"]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome, raca, historico FROM pets WHERE dono_email = ?", (dono_email,))
        pet = cursor.fetchone()
    if not pet:
        flash("Cadastre um pet antes de acessar o checklist.")
        return redirect(url_for("cadastrar_pet"))

    if request.method == "POST":
        itens = request.form.to_dict()
        recomendacao = "Leve todos os itens essenciais!"
        produto_sugerido = "Coleira confortável"
        link_produto = "https://balticpets.com.br/"  # link real para Baltic Pets
        return render_template(
            "checklist.html",
            pet={"nome": pet[0], "raca": pet[1], "historico": pet[2]},
            recomendacao=recomendacao,
            produto_sugerido=produto_sugerido,
            link_produto=link_produto,
            cupom=BALTIC_COUPON
        )

    # GET
    return render_template(
        "checklist.html",
        pet={"nome": pet[0], "raca": pet[1], "historico": pet[2]},
        recomendacao=None,
        cupom=BALTIC_COUPON
    )

@app.route("/notificacoes_pet")
def notificacoes_pet():
    if "usuario" not in session:
        return jsonify([])
    dono_email = session["usuario"]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, raca, historico FROM pets WHERE dono_email = ?", (dono_email,))
        pets = cursor.fetchall()
    notificacoes = []
    for pet_id, nome, raca, historico in pets:
        bpm = random.randint(60, 150)
        temp_corporal = round(random.uniform(36.0, 40.0), 1)
        temp_ambiente = round(random.uniform(22.0, 28.0), 1)
        atividade = random.choice(["baixa", "moderada", "alta"])
        estado = analisar_comportamento(bpm, temp_corporal, temp_ambiente, atividade)
        if bpm < 70 or bpm > 140 or temp_corporal < 36.5 or temp_corporal > 39.5 or estado in ["Estressado", "Observação necessária"]:
            notificacoes.append({
                "nome": nome,
                "bpm": bpm,
                "temp_corporal": temp_corporal,
                "temp_ambiente": temp_ambiente,
                "estado": estado
            })
    return jsonify(notificacoes)

@app.route("/mapa")
def mapa():
    regioes = [
        {"nome": "Bairro Central", "lat": -23.55, "lng": -46.63, "media_bpm": 92, "emocao": "Calmo"},
        {"nome": "Zona Leste", "lat": -23.56, "lng": -46.52, "media_bpm": 105, "emocao": "Agitado"},
        {"nome": "Zona Sul", "lat": -23.62, "lng": -46.65, "media_bpm": 79, "emocao": "Sonolento"},
    ]
    return render_template("mapa.html", regioes=regioes)

# ----------------------------------------------------------------------------
# Agenda (com carteirinha)
# ----------------------------------------------------------------------------
@app.route("/agenda", methods=["GET", "POST"])
def agenda():
    if "usuario" not in session:
        return redirect(url_for("login"))
    dono = session["usuario"]
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id,nome FROM pets WHERE dono_email=?", (dono,))
        pets = c.fetchall()
        if request.method == "POST":
            from werkzeug.utils import secure_filename
            nome_evento = request.form["nome_evento"].strip()
            data_evento = request.form["data_evento"].strip()
            tipo = request.form["tipo"].strip()
            pet_id = request.form["pet_id"].strip()
            carteirinha_url = request.form.get("carteirinha_url", "").strip() or None
            file = request.files.get("carteirinha")
            carteirinha_path = None
            if file and file.filename:
                if _allowed(file.filename):
                    fname = secure_filename(f"{int(time.time())}_{file.filename}")
                    save_path = os.path.join(UPLOAD_DIR, fname)
                    file.save(save_path)
                    carteirinha_path = f"uploads/carteirinhas/{fname}"
                else:
                    flash("Arquivo da carteirinha deve ser PDF/JPG/PNG.", "warning")
            c.execute("""
                INSERT INTO eventos_pet
                    (nome_evento, data_evento, tipo, pet_id, carteirinha_path, carteirinha_url, notificado)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (nome_evento, data_evento, tipo, pet_id, carteirinha_path, carteirinha_url))
            conn.commit()
            flash("Evento adicionado!", "success")
            return redirect(url_for("agenda"))
        c.execute("""
            SELECT e.nome_evento, e.data_evento, e.tipo, p.nome,
                   e.carteirinha_path, e.carteirinha_url
            FROM eventos_pet e
            JOIN pets p ON e.pet_id = p.id
            WHERE p.dono_email = ?
            ORDER BY e.data_evento ASC
        """, (dono,))
        eventos = c.fetchall()
    return render_template("agenda.html", pets=pets, eventos=eventos,
                           push_supported=(_HAS_WEBPUSH and VAPID_PUBLIC_KEY))

# ----------------------------------------------------------------------------
# Radar
# ----------------------------------------------------------------------------
@app.route("/radar")
def radar():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("radar.html", usuario=session["usuario"])

# ----------------------------------------------------------------------------
# Chatbot
# ----------------------------------------------------------------------------
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    def responder(pergunta: str, tutor_email: str):
        txt = (pergunta or "").strip()
        low = txt.lower()
        if low.startswith("/help"):
            return ("Comandos: /status, /eventos, /checklist, /racao, "
                    "/asfalto <temp-ar> [sol|sombra], /radar, /agenda, /mapa")
        if low.startswith("/status") or "status do pet" in low:
            bpm = random.randint(80, 140)
            temp_corporal = round(random.uniform(37.0, 39.5), 1)
            temp_amb = round(random.uniform(20.0, 30.0), 1)
            atividade = random.choice(["baixa", "moderada", "alta"])
            estado = analisar_comportamento(bpm, temp_corporal, temp_amb, atividade)
            return (f"Status de agora:\n"
                    f"• Batimentos: {bpm} bpm\n"
                    f"• Temp. corporal: {temp_corporal} °C\n"
                    f"• Temp. ambiente: {temp_amb} °C\n"
                    f"• Atividade: {atividade}\n"
                    f"• Estado emocional: {estado}")
        if low.startswith("/eventos") or "próximos eventos" in low or "proximos eventos" in low:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("""
                  SELECT e.nome_evento, e.data_evento, e.tipo, p.nome
                  FROM eventos_pet e
                  JOIN pets p ON e.pet_id = p.id
                  WHERE p.dono_email = ?
                  ORDER BY e.data_evento ASC
                """, (tutor_email,))
                rows = c.fetchall()
            if not rows:
                return "Você ainda não tem eventos cadastrados. Abra a Agenda para adicionar."
            top = rows[:3]
            linhas = [f"• {n} ({t}) — {p} — {d}" for (n, d, t, p) in top]
            return "Próximos eventos:\n" + "\n".join(linhas)
        if low.startswith("/checklist") or "checklist" in low:
            return ("Checklist rápido para passeio:\n"
                    "• Guia/coleira e identificação\n"
                    "• Água e potinho portátil\n"
                    "• Saquinhos higiênicos\n"
                    "• Lenços/toalhinhas\n"
                    "• Protetor de coxins (em dias quentes)")
        if low.startswith("/racao") or "ração" in low or "alimentação" in low or "comida" in low:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT nome, raca FROM pets WHERE dono_email=? LIMIT 1", (tutor_email,))
                pet = c.fetchone()
            raca = (pet[1] if pet else "") or ""
            return f"Sugestão de ração para {raca or 'seu pet'}: ração premium de manutenção."
        if low.startswith("/asfalto") or "asfalto" in low:
            m = re.search(r'(-?\d{1,2}(?:[.,]\d)?)', low)
            if m:
                air = float(m.group(1).replace(",", "."))
                exp_sol = ("sol" in low) and ("sombra" not in low)
                a, sig, dica, lugar = resumo_asfalto(air, exp_sol)
                return (f"Asfalto estimado: {a} °C — sinal {sig.upper()}.\n"
                        f"{dica} Melhor agora: {lugar}.")
            return "Use assim: /asfalto 28 sol  (ou troque por 'sombra')."
        if low.startswith("/radar"):  return "Abrindo o Radar…"
        if low.startswith("/agenda"): return "Abrindo a Agenda…"
        if low.startswith("/mapa"):   return "Abrindo o Mapa…"
        return ("Posso ajudar com: /status, /eventos, /checklist, /racao e /asfalto <temp> [sol|sombra]. "
                "Também posso abrir /radar, /agenda e /mapa.")

    if request.method == 'POST':
        data = request.get_json()
        pergunta = data.get('mensagem', '')
        tutor_email = session.get('usuario', 'tutor@email.com')
        resposta = responder(pergunta, tutor_email)
        return jsonify({'resposta': resposta})

    tutor_email = session.get('usuario', 'tutor@email.com')
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT nome, raca, historico FROM pets WHERE dono_email = ?', (tutor_email,))
        pet = cursor.fetchone()

    if pet:
        nome_pet, raca_pet, historico = pet
        nome_tutor = tutor_email.split('@')[0].capitalize()
    else:
        nome_pet, raca_pet, historico, nome_tutor = "Seu Pet", "Desconhecida", "Sem histórico", "Tutor"

    return render_template('chatbot.html',
                           nome_tutor=nome_tutor,
                           nome_pet=nome_pet,
                           raca_pet=raca_pet,
                           historico=historico)

# ----------------------------------------------------------------------------
# Auxiliares & service worker
# ----------------------------------------------------------------------------
@app.route("/tasks/run-notifier")
def run_notifier_now():
    if "usuario" not in session:
        return redirect(url_for("login"))
    res = send_due_event_emails()
    flash(f"Lembretes enviados: {res['enviados']} | erros: {res['erros']}")
    return redirect(url_for("agenda"))

@app.route("/push/vapid-public-key")
def push_vapid_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})

@app.route("/push/subscribe", methods=["POST"])
def push_subscribe():
    if "usuario" not in session:
        return jsonify({"ok": False, "error": "auth"}), 401
    try:
        data = request.get_json(force=True)
        save_push_subscription(session["usuario"], data)
        return jsonify({"ok": True})
    except Exception as e:
        print("[PUSH][subscribe] erro:", e)
        return jsonify({"ok": False}), 400

def resumo_asfalto(temp_ar: float, exposto_ao_sol: bool):
    delta = 14 if exposto_ao_sol else 6
    asfalto = round(temp_ar + delta, 1)
    if asfalto <= 45:
        return asfalto, "verde", "Passeio liberado (prefira sombra).", "Parque arborizado"
    if asfalto <= 52:
        return asfalto, "amarelo", "Passeio curto em grama/sombra. Evite horários de pico.", "Praça com grama"
    return asfalto, "vermelho", "Evite sair agora. Opte por atividades indoor.", "Ambiente interno"

SW_JS = """self.addEventListener("push",event=>{let d={};try{d=event.data.json()}catch(e){}const t=d.title||"PETCIBER",o={body:d.body||"Você tem um lembrete.",icon:d.icon||"/static/brand/logo.png",badge:d.badge||"/static/brand/logo.png",data:{url:d.url||"/agenda"}};event.waitUntil(self.registration.showNotification(t,o))});self.addEventListener("notificationclick",event=>{event.notification.close();const u=(event.notification.data&&event.notification.data.url)||"/agenda";event.waitUntil(clients.matchAll({type:"window",includeUncontrolled:!0}).then(w=>{for(const c of w){if("focus"in c){c.navigate(u);return c.focus()}}if(clients.openWindow)return clients.openWindow(u)}))});"""
@app.route("/sw.js")
def service_worker():
    return Response(SW_JS, mimetype="application/javascript")

# ----------------------------------------------------------------------------
# Compat/APIs para ingestão (mantidas)
# ----------------------------------------------------------------------------
@limiter.limit("60/minute")
@app.route("/api/sensors/ingest", methods=["POST"])
def api_ingest():
    token = request.headers.get("x-api-key")
    if token != API_KEY:
        return jsonify({"error": "Acesso negado"}), 401
    data = request.get_json(silent=True) or {}
    pet_id = data.get("pet_id")
    bpm = data.get("bpm")
    temp = data.get("temp")
    if pet_id is None or bpm is None or temp is None:
        return jsonify({"error": "Envie pet_id, bpm, temp"}), 400
    try:
        pet_id = int(pet_id)
        bpm = float(bpm)
        temp = float(temp)
    except:
        return jsonify({"error": "pet_id/bpm/temp inválidos"}), 400
    alertas, previsoes = analisar_vitais_pet(bpm, temp)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO vitais(pet_id, bpm, temp, ts) VALUES (?, ?, ?, ?)",
                  (pet_id, bpm, temp, int(time.time())))
            conn.commit()
    except Exception as e:
        print("[DB vitais] erro:", e)
    payload = {"pet_id": pet_id, "bpm": bpm, "temperatura": temp, "alertas": alertas, "previsoes": previsoes}
    socketio.emit("sensor_update", payload, to=pet_room(pet_id))
    return jsonify({"ok": True, **payload})

@limiter.limit("60/minute")
@app.route("/monitorar", methods=["POST"])
def monitorar():
    token = request.headers.get("x-api-key")
    if token != API_KEY:
        return jsonify({"erro":"Acesso negado"}), 401
    data = request.get_json() or {}
    device_uid = data.get("device_uid")
    bpm       = data.get("bpm")
    temp_c    = data.get("temp_c")
    if not device_uid or bpm is None or temp_c is None:
        return jsonify({"erro":"Envie device_uid, bpm, temp_c"}), 400
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        row = c.execute("SELECT pet_id FROM devices WHERE device_uid=?", (device_uid,)).fetchone()
    if not row:
        return jsonify({"erro":"Dispositivo não cadastrado"}), 403
    pet_id = int(row[0])
    try:
        bpm = float(bpm); temp = float(temp_c)
    except:
        return jsonify({"erro":"bpm/temp inválidos"}), 400
    alertas, previsoes = analisar_vitais_pet(bpm, temp)
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO vitais(pet_id, bpm, temp, ts) VALUES (?, ?, ?, ?)",
                      (pet_id, bpm, temp, int(time.time())))
            conn.commit()
    except Exception as e:
        print("[DB vitais] erro:", e)
    payload = {"pet_id": pet_id, "bpm": bpm, "temperatura": temp, "alertas": alertas, "previsoes": previsoes, "device_uid": device_uid}
    socketio.emit("sensor_update", payload, to=pet_room(pet_id))
    return jsonify({"ok": True, **payload})

@socketio.on("join_pet")
def on_join_pet(data):
    pet_id = data.get("pet_id")
    if not pet_id:
        return
    room = pet_room(pet_id)
    join_room(room)
    emit("joined", {"room": room})

@socketio.on("leave_pet")
def on_leave_pet(data):
    pet_id = data.get("pet_id")
    if not pet_id:
        return
    room = pet_room(pet_id)
    leave_room(room)
    emit("left", {"room": room})

@app.route("/api/pet/<int:pet_id>/history")
def pet_history(pet_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT bpm, temp, ts FROM vitais
            WHERE pet_id=? ORDER BY ts DESC LIMIT 200
        """, (pet_id,)).fetchall()
    out = [{"bpm": float(r["bpm"]), "temp_c": float(r["temp"]), "ts": datetime.utcfromtimestamp(r["ts"]).isoformat()} for r in rows]
    return jsonify(out)

# ------------------------------ CHECKOUT ------------------------------------
from math import ceil

def _calc_total(price, qty, coupon_code):
    subtotal = price * qty
    discount = 0.0
    if coupon_code and coupon_code.upper() == BALTIC_COUPON["code"]:
        discount = subtotal * (BALTIC_COUPON["percent"]/100.0)
    total = round(subtotal - discount, 2)
    return subtotal, discount, total

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if "usuario" not in session:
        return redirect(url_for("login"))
    sku = request.args.get("sku","")
    qty = max(1, int(request.args.get("qty", "1")))
    prod = next((p for p in BALTIC_PRODUCTS if p["sku"]==sku), None)
    if not prod:
        flash("Produto não encontrado.", "warning")
        return redirect(url_for("dashboard"))
    coupon = request.args.get("coupon","").upper()
    subtotal, discount, total = _calc_total(prod["price"], qty, coupon)

    if request.method == "POST":
        method = request.form.get("payment_method","")
        card_ok = (method in ("credito","debito","pix"))
        if not card_ok:
            flash("Selecione uma forma de pagamento.", "warning")
            return redirect(request.url)

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
              INSERT INTO orders (user_email, sku, name, qty, price, payment_method, status, coupon)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session["usuario"], prod["sku"], prod["name"], qty, total, method, "pago", coupon or None))
            conn.commit()

        session["bonus_plan_discount_next_month"] = True
        flash("Compra aprovada! 🎉 Cupom aplicado e bônus garantido para o próximo mês.", "success")
        return redirect(url_for("dashboard"))

    return render_template("checkout.html",
        prod=prod, qty=qty, coupon=coupon,
        subtotal=subtotal, discount=discount, total=total,
        cupom=BALTIC_COUPON
    )

# ------------------------------- WIDGET -------------------------------------
@app.route("/dashboard_widget")
def dashboard_widget():
    pet_id = request.args.get("pet_id", type=int, default=0)
    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>PETCIBER • Painel do Pet</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      <style>
        body{{font-family:Arial,Helvetica,sans-serif;margin:0;padding:16px;background:#fafafa}}
        .wrap{{max-width:1100px;margin:0 auto}}
        h1{{color:#8b5a2b;margin:0 0 6px}}
        .sub{{color:#555;margin:0 0 16px}}
        .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
        .card{{background:#fff;border-radius:12px;box-shadow:0 6px 14px rgba(0,0,0,.08);padding:14px}}
        .kpi{{font-size:28px;font-weight:700}}
        .label{{color:#666;font-size:13px}}
        .alertas{{color:#c62828;font-weight:600}}
        .previsoes{{color:#2e7d32}}
        canvas{{max-width:100%;height:300px}}
        .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}}
        @media(max-width:900px){{.row{{grid-template-columns:1fr}}}}
      </style>
    </head>
    <body>
      <div class="wrap">
        <h1>Painel do Pet • PETCIBER</h1>
        <p class="sub">Monitoramento em tempo real (BPM + Temperatura)</p>
        <div class="grid">
          <div class="card"><div class="label">BPM</div><div id="kpi-bpm" class="kpi">--</div></div>
          <div class="card"><div class="label">Temperatura (°C)</div><div id="kpi-temp" class="kpi">--</div></div>
          <div class="card"><div class="label">Alertas</div><div id="kpi-alertas" class="alertas">--</div></div>
          <div class="card"><div class="label">Previsões</div><div id="kpi-previsoes" class="previsoes">--</div></div>
        </div>
        <div class="row">
          <div class="card"><canvas id="bpmChart"></canvas></div>
          <div class="card"><canvas id="tempChart"></canvas></div>
        </div>
      </div>
      <script>
        const PET_ID = {pet_id};
        const socket = io();
        socket.emit("join_pet", {{pet_id: PET_ID}});
        const elBpm = document.getElementById("kpi-bpm");
        const elTemp = document.getElementById("kpi-temp");
        const elAl = document.getElementById("kpi-alertas");
        const elPr = document.getElementById("kpi-previsoes");
        const bpmData = {{ labels: [], datasets: [{{ label: 'BPM', data: [], borderWidth:2, fill:false }}] }};
        const tempData = {{ labels: [], datasets: [{{ label: 'Temperatura', data: [], borderWidth:2, fill:false }}] }};
        const bpmChart = new Chart(document.getElementById('bpmChart'), {{
          type: 'line', data: bpmData,
          options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{title:{{display:true,text:'Tempo'}}}},y:{{title:{{display:true,text:'BPM'}}}}}}}}
        }});
        const tempChart = new Chart(document.getElementById('tempChart'), {{
          type: 'line', data: tempData,
          options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{title:{{display:true,text:'Tempo'}}}},y:{{title:{{display:true,text:'°C'}}}}}}}}
        }});
        function pushCharts(bpm, temp){{
          const now = new Date().toLocaleTimeString();
          if (bpmData.labels.length > 60){{ bpmData.labels.shift(); bpmData.datasets[0].data.shift(); }}
          if (tempData.labels.length > 60){{ tempData.labels.shift(); tempData.datasets[0].data.shift(); }}
          bpmData.labels.push(now); bpmData.datasets[0].data.push(bpm);
          tempData.labels.push(now); tempData.datasets[0].data.push(temp);
          bpmChart.update(); tempChart.update();
        }}
        socket.on("scan_detectado", (data)=>{{ if(data.pet_id!==PET_ID) return; console.log("Scan detectado:", data); }});
        socket.on("sensor_update", (data)=>{{
          if(data.pet_id!==PET_ID) return;
          elBpm.innerText = data.bpm;
          elTemp.innerText = data.temperatura;
          elAl.innerText = (data.alertas||[]).join(", ") || "—";
          elPr.innerText = (data.previsoes||[]).join(", ") || "—";
          pushCharts(Number(data.bpm), Number(data.temperatura));
        }});
        window.addEventListener("beforeunload", ()=>{{ socket.emit("leave_pet", {{pet_id: PET_ID}}); }});
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------
def porta_livre(inicio=5001, tentativas=50):
    p = inicio
    for _ in range(tentativas):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                p += 1
    raise OSError("Sem porta livre")

if __name__ == "__main__":
    port = porta_livre()
    print(f"[PETCIBER] Servidor em http://127.0.0.1:{port}")
    socketio.run(app, host="127.0.0.1", port=port, debug=True, use_reloader=False)