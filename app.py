import json
import math
import os
import sqlite3
import string
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signbridge.db")


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sign_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sign_id INTEGER NOT NULL,
            landmarks TEXT NOT NULL,
            FOREIGN KEY (sign_id) REFERENCES signs(id)
        )
    """)
    # Add starter signs (names only) the first time
    count = db.execute("SELECT COUNT(*) FROM signs").fetchone()[0]
    if count == 0:
        letters = [(c, "Alphabet") for c in string.ascii_uppercase]
        numbers = [(str(n), "Numbers") for n in range(1, 11)]
        db.executemany("INSERT INTO signs (name, category) VALUES (?, ?)",
                       letters + numbers)
    db.commit()
    db.close()


def init_quiz_tables():
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sign_id INTEGER NOT NULL,
            times_correct INTEGER NOT NULL DEFAULT 0,
            last_practised TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, sign_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (sign_id) REFERENCES signs(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            correct INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.commit()
    db.close()


init_db()
init_quiz_tables()


# ---------- login protection ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ---------- admin protection ----------
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Admins only.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ---------- pages ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not email or not password:
            flash("Please fill in all fields.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            db = get_db()
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            role = "admin" if count == 0 else "student"  # first user = admin
            try:
                db.execute(
                    "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    (username, email, generate_password_hash(password), role),
                )
                db.commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That username or email is already taken.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("Welcome back, " + user["username"] + "!", "success")
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]

    stats = db.execute("""
        SELECT COUNT(*) AS quizzes,
               COALESCE(MAX(score), 0) AS best,
               COALESCE(SUM(correct), 0) AS correct,
               COALESCE(SUM(total), 0) AS total
        FROM quiz_results WHERE user_id = ?
    """, (uid,)).fetchone()
    accuracy = round(100 * stats["correct"] / stats["total"]) if stats["total"] else 0

    ready = db.execute("""
        SELECT COUNT(*) FROM signs s
        WHERE EXISTS (SELECT 1 FROM sign_samples p WHERE p.sign_id = s.id)
    """).fetchone()[0]
    learned = db.execute(
        "SELECT COUNT(*) FROM progress WHERE user_id = ? AND times_correct > 0",
        (uid,)).fetchone()[0]

    history = [dict(r) for r in db.execute("""
        SELECT score, correct, total, created_at
        FROM quiz_results WHERE user_id = ? ORDER BY id DESC LIMIT 10
    """, (uid,)).fetchall()]

    per_sign = [dict(r) for r in db.execute("""
        SELECT s.name, p.times_correct
        FROM progress p JOIN signs s ON s.id = p.sign_id
        WHERE p.user_id = ?
        ORDER BY p.times_correct DESC, s.name LIMIT 10
    """, (uid,)).fetchall()]

    leaders = [dict(r) for r in db.execute("""
        SELECT u.username, MAX(q.score) AS best, COUNT(*) AS quizzes
        FROM quiz_results q JOIN users u ON u.id = q.user_id
        GROUP BY u.id ORDER BY best DESC LIMIT 10
    """).fetchall()]

    chronological = list(reversed(history))
    return render_template(
        "dashboard.html",
        stats=stats, accuracy=accuracy, ready=ready, learned=learned,
        history=history, leaders=leaders,
        score_labels=["Quiz " + str(i + 1) for i in range(len(chronological))],
        score_values=[h["score"] for h in chronological],
        sign_labels=[p["name"] for p in per_sign],
        sign_values=[p["times_correct"] for p in per_sign],
    )


@app.route("/learn")
@login_required
def learn():
    category = request.args.get("category", "All")
    query = """
        SELECT s.id, s.name, s.category, s.description, COUNT(p.id) AS samples
        FROM signs s
        LEFT JOIN sign_samples p ON p.sign_id = s.id
    """
    params = ()
    if category in ("Alphabet", "Numbers", "Words"):
        query += " WHERE s.category = ?"
        params = (category,)
    query += " GROUP BY s.id ORDER BY s.category, s.id"
    db = get_db()
    signs = db.execute(query, params).fetchall()
    rows = db.execute(
        "SELECT sign_id, landmarks, MIN(id) FROM sign_samples GROUP BY sign_id"
    ).fetchall()
    shapes = {str(r["sign_id"]): json.loads(r["landmarks"]) for r in rows}
    return render_template("learn.html", signs=signs, category=category, shapes=shapes)


# ---------- admin pages ----------
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "Words")
        if not name:
            flash("Please enter a sign name.", "error")
        elif category not in ("Alphabet", "Numbers", "Words"):
            flash("Invalid category.", "error")
        else:
            try:
                db.execute("INSERT INTO signs (name, category) VALUES (?, ?)",
                           (name, category))
                db.commit()
                flash("Sign added.", "success")
            except sqlite3.IntegrityError:
                flash("That sign already exists.", "error")
        return redirect(url_for("admin"))

    signs = db.execute("""
        SELECT s.id, s.name, s.category, s.description, COUNT(p.id) AS samples
        FROM signs s
        LEFT JOIN sign_samples p ON p.sign_id = s.id
        GROUP BY s.id ORDER BY s.category, s.id
    """).fetchall()
    return render_template("admin.html", signs=signs)


@app.route("/admin/sign/<int:sign_id>/description", methods=["POST"])
@admin_required
def update_description(sign_id):
    desc = request.form.get("description", "").strip()
    db = get_db()
    db.execute("UPDATE signs SET description = ? WHERE id = ?", (desc, sign_id))
    db.commit()
    flash("Description saved.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/sign/<int:sign_id>/clear", methods=["POST"])
@admin_required
def clear_samples(sign_id):
    db = get_db()
    db.execute("DELETE FROM sign_samples WHERE sign_id = ?", (sign_id,))
    db.commit()
    flash("All samples deleted for that sign.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/record/<int:sign_id>")
@admin_required
def record(sign_id):
    db = get_db()
    sign = db.execute("SELECT * FROM signs WHERE id = ?", (sign_id,)).fetchone()
    if sign is None:
        abort(404)
    count = db.execute("SELECT COUNT(*) FROM sign_samples WHERE sign_id = ?",
                       (sign_id,)).fetchone()[0]
    return render_template("record.html", sign=sign, count=count)


@app.route("/api/samples/<int:sign_id>", methods=["POST"])
@admin_required
def add_sample(sign_id):
    data = request.get_json(silent=True) or {}
    pts = data.get("landmarks")
    ok = (isinstance(pts, list) and len(pts) == 42 and
          all(isinstance(v, (int, float)) and not isinstance(v, bool)
              and math.isfinite(v) for v in pts))
    if not ok:
        return jsonify(error="Invalid landmarks"), 400
    db = get_db()
    if db.execute("SELECT 1 FROM signs WHERE id = ?", (sign_id,)).fetchone() is None:
        return jsonify(error="No such sign"), 404
    db.execute("INSERT INTO sign_samples (sign_id, landmarks) VALUES (?, ?)",
               (sign_id, json.dumps(pts)))
    db.commit()
    count = db.execute("SELECT COUNT(*) FROM sign_samples WHERE sign_id = ?",
                       (sign_id,)).fetchone()[0]
    return jsonify(count=count)


# ---------- practice ----------
@app.route("/practice")
@login_required
def practice():
    signs = get_db().execute("""
        SELECT s.id, s.name, s.category, s.description
        FROM signs s
        WHERE EXISTS (SELECT 1 FROM sign_samples p WHERE p.sign_id = s.id)
        ORDER BY s.category, s.id
    """).fetchall()
    return render_template("practice.html", signs=signs)


@app.route("/api/samples")
@login_required
def all_samples():
    rows = get_db().execute("""
        SELECT s.name, p.landmarks
        FROM sign_samples p JOIN signs s ON s.id = p.sign_id
    """).fetchall()
    return jsonify([{"name": r["name"], "points": json.loads(r["landmarks"])}
                    for r in rows])


# ---------- quiz ----------
@app.route("/quiz")
@login_required
def quiz():
    return render_template("quiz.html")


@app.route("/api/quiz/submit", methods=["POST"])
@login_required
def quiz_submit():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    if not isinstance(answers, list) or not (1 <= len(answers) <= 50):
        return jsonify(error="Invalid answers"), 400

    db = get_db()
    sign_ids = {r["name"]: r["id"] for r in db.execute("SELECT id, name FROM signs")}
    score = 0
    correct = 0
    total = 0

    for a in answers:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        if not isinstance(name, str) or name not in sign_ids:
            continue
        total += 1
        if a.get("correct") is True:
            tl = a.get("time_left", 0)
            if (not isinstance(tl, (int, float)) or isinstance(tl, bool)
                    or not math.isfinite(tl)):
                tl = 0
            tl = max(0, min(15, tl))
            score += 10 + int(tl)
            correct += 1
            db.execute("""
                INSERT INTO progress (user_id, sign_id, times_correct, last_practised)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, sign_id) DO UPDATE SET
                    times_correct = times_correct + 1,
                    last_practised = CURRENT_TIMESTAMP
            """, (session["user_id"], sign_ids[name]))

    if total == 0:
        return jsonify(error="No valid answers"), 400

    db.execute("INSERT INTO quiz_results (user_id, score, correct, total) VALUES (?, ?, ?, ?)",
               (session["user_id"], score, correct, total))
    db.commit()
    return jsonify(score=score, correct=correct, total=total)


# ---------- translator ----------
@app.route("/translator")
@login_required
def translator():
    return render_template("translator.html")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")