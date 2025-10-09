# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import os, json, re, time, uuid
import requests
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Config
APP_SECRET = os.getenv("FLASK_SECRET", "change-this-secret")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # change in production
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1425714463482580992/thC-ULGdsTvsOZ52UXS4AFzaijaB90Z3GCJ0CrVRxFUAFDIAb7B6XYGqZycnPHMyMws_")
SITE_BASE = os.getenv("SITE_BASE", "https://webforppt.onrender.com")  # change for your deployed site

USERS_FILE = "users.json"
QUEUE_FILE = "card_queue.json"
UPLOAD_FOLDER = "uploads"

app = Flask(__name__)
app.secret_key = APP_SECRET
app.permanent_session_lifetime = timedelta(days=7)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Utils: users ----------
def load_users():
    if not os.path.exists(USERS_FILE):
        return {"users": []}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_user(username):
    data = load_users()
    for u in data.get("users", []):
        if u.get("username") == username:
            return u
    return None

def create_user(username, password_plain):
    data = load_users()
    hashed = generate_password_hash(password_plain)
    new = {"username": username, "password_hash": hashed, "balance": 0.0}
    data["users"].append(new)
    save_users(data)
    return new

def update_user_balance(username, amount):
    data = load_users()
    for u in data.get("users", []):
        if u["username"] == username:
            u["balance"] = u.get("balance", 0.0) + amount
            save_users(data)
            return u
    return None

# ---------- Utils: queue ----------
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_queue(q):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)

# ---------- Password policy ----------
def validate_password(pw):
    if len(pw) < 8:
        return False, "Mật khẩu phải >= 8 ký tự."
    if not re.search(r"\d", pw):
        return False, "Mật khẩu phải có ít nhất 1 chữ số."
    if not re.search(r"[A-Z]", pw):
        return False, "Mật khẩu phải có ít nhất 1 chữ hoa."
    return True, ""

# ---------- Discord notification ----------
def send_discord_notification(item):
    """
    Send a Discord webhook message. Include approve/reject links back to site admin.
    """
    if not DISCORD_WEBHOOK:
        print("No DISCORD_WEBHOOK configured")
        return False
    approve_url = f"{SITE_BASE.rstrip('/')}/admin/approve/{item['id']}"
    reject_url = f"{SITE_BASE.rstrip('/')}/admin/reject/{item['id']}"
    content = (f"Top-up request from **{item['username']}**\n"
               f"Card type: **{item['card_type']}**\nSerial: `{item['serial']}`\nCode: `{item['code']}`\n\n"
               f"Approve: {approve_url}\nReject: {reject_url}")
    embed = {
        "title": "New Top-up Request",
        "description": f"User: {item['username']}\nCard: {item['card_type']}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(item.get("created_at", time.time())))
    }
    payload = {"content": content, "embeds": [embed]}
    try:
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print("Discord webhook error:", e)
        return False

# ---------- Routes ----------
@app.route("/")
def index():
    user = None
    if 'username' in session:
        user = find_user(session['username'])
    files = os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else []
    return render_template("index.html", files=files, user=user)

# Register
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if not username or not password:
            flash("Vui lòng điền username và password", "danger")
            return redirect(url_for("register"))
        if find_user(username):
            flash("Tên tài khoản đã được đặt", "danger")
            return redirect(url_for("register"))
        ok, msg = validate_password(password)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("register"))
        create_user(username, password)
        flash("Đăng ký thành công. Hãy đăng nhập.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# Login
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        u = find_user(username)
        if not u or not check_password_hash(u["password_hash"], password):
            flash("Thông tin đăng nhập không đúng", "danger")
            return redirect(url_for("login"))
        session.permanent = True
        session["username"] = username
        flash("Đăng nhập thành công", "success")
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất", "info")
    return redirect(url_for("index"))

# Upload (user must be logged in)
@app.route("/upload", methods=["POST"])
def upload_file():
    if "username" not in session:
        flash("Bạn cần đăng nhập để upload", "danger")
        return redirect(url_for("login"))
    if "file" not in request.files:
        flash("Không có file", "danger")
        return redirect(url_for("index"))
    f = request.files["file"]
    if f.filename == "":
        flash("No selected file", "danger")
        return redirect(url_for("index"))
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    safe_name = f.filename
    f.save(os.path.join(UPLOAD_FOLDER, safe_name))
    flash("Upload thành công", "success")
    return redirect(url_for("index"))

@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

# Top-up: user submits card -> saved to queue and Discord notified
@app.route("/topup", methods=["GET","POST"])
def topup():
    if "username" not in session:
        flash("Bạn cần đăng nhập để nạp thẻ", "danger")
        return redirect(url_for("login"))
    if request.method == "POST":
        card_type = request.form.get("card_type","").strip()
        serial = request.form.get("serial","").strip()
        code = request.form.get("code","").strip()
        if not card_type or not serial or not code:
            flash("Vui lòng nhập đầy đủ thông tin thẻ", "danger")
            return redirect(url_for("topup"))
        item = {
            "id": str(uuid.uuid4()),
            "username": session["username"],
            "card_type": card_type,
            "serial": serial,
            "code": code,
            "status": "pending",
            "created_at": int(time.time())
        }
        q = load_queue()
        q.append(item)
        save_queue(q)
        ok = send_discord_notification(item)
        if ok:
            flash("Yêu cầu nạp đã gửi tới Discord. Admin sẽ kiểm tra.", "info")
        else:
            flash("Gửi Discord thất bại — admin kiểm tra trang admin.", "warning")
        return redirect(url_for("index"))
    return render_template("topup.html")

# Admin login + dashboard
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Mật khẩu admin sai", "danger")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    q = load_queue()
    return render_template("admin_dashboard.html", queue=q)

@app.route("/admin/approve/<item_id>", methods=["GET","POST"])
def admin_approve(item_id):
    if not session.get("is_admin"):
        flash("Admin login required", "danger")
        return redirect(url_for("admin_login"))
    q = load_queue()
    for it in q:
        if it["id"] == item_id and it["status"] == "pending":
            # amount can be provided in POST form (admin chooses), default 100000
            if request.method == "POST":
                amount = float(request.form.get("amount", 100000))
            else:
                # GET: allow approving via link with ?amount=...
                try:
                    amount = float(request.args.get("amount", 100000))
                except:
                    amount = 100000.0
            it["status"] = "approved"
            it["credited_amount"] = amount
            it["processed_at"] = int(time.time())
            update_user_balance(it["username"], amount)
            save_queue(q)
            flash(f"Đã duyệt và cộng {amount} cho {it['username']}", "success")
            return redirect(url_for("admin_dashboard"))
    flash("Item không tồn tại hoặc đã xử lý", "warning")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/reject/<item_id>", methods=["POST","GET"])
def admin_reject(item_id):
    if not session.get("is_admin"):
        flash("Admin login required", "danger")
        return redirect(url_for("admin_login"))
    q = load_queue()
    for it in q:
        if it["id"] == item_id and it["status"] == "pending":
            it["status"] = "rejected"
            it["processed_at"] = int(time.time())
            save_queue(q)
            flash("Đã từ chối yêu cầu", "info")
            return redirect(url_for("admin_dashboard"))
    flash("Item không tồn tại", "warning")
    return redirect(url_for("admin_dashboard"))

# API: balance
@app.route("/api/balance")
def api_balance():
    if "username" not in session:
        return {"error": "not authenticated"}, 401
    u = find_user(session["username"])
    return {"username": u["username"], "balance": u.get("balance", 0.0)}

# Ensure files exist and run
if __name__ == "__main__":
    if not os.path.exists(USERS_FILE):
        save_users({"users": []})
    if not os.path.exists(QUEUE_FILE):
        save_queue([])
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
