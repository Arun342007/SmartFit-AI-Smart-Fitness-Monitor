"""
AI-Powered Smart Fitness Tracking and Personalized Health Monitoring System
----------------------------------------------------------------------------
Main Flask application.

IMPORTANT DISCLAIMER:
This application is an ACADEMIC / EDUCATIONAL project built primarily to
demonstrate Software Configuration Management (SCM) and DevOps practices
(Git, GitHub, Jenkins, Docker). The health-risk prediction and alerts are
DEMO features built on a small synthetic dataset. They are NOT a medical
diagnosis system and must never be used for real clinical decisions.

Configuration (environment variables, all optional):
    SMARTFIT_INSTANCE_DIR  folder for the SQLite databases (default: ./instance)
    SECRET_KEY             Flask secret key (set a real value in production)
    HOST / PORT            dev-server bind address (default 127.0.0.1:5000)
    FLASK_DEBUG=1          enable Flask debug mode (never in production)
"""

import math
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from flask import (
    Flask, Response, flash, g, jsonify, redirect, render_template, request,
    send_from_directory, url_for,
)

from camera import coach
from models.health_model import ACTIVITY_LEVELS, HealthRiskModel
from nutrition_feature import init_nutrition_db, nutrition_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.abspath(
    os.environ.get("SMARTFIT_INSTANCE_DIR") or os.path.join(BASE_DIR, "instance")
)
DB_PATH = os.path.join(INSTANCE_DIR, "health_monitor.db")
NUTRITION_DB_PATH = os.path.join(INSTANCE_DIR, "nutrition_meals.db")

app = Flask(__name__)
app.config.update(
    DATABASE=DB_PATH,
    NUTRITION_DATABASE=NUTRITION_DB_PATH,
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
)
app.register_blueprint(nutrition_bp)

# Train the demo ML model once at start-up.
health_model = HealthRiskModel()
health_model.train()

# Exercise catalogue + shared coaching session live in camera/coach.py.
EXERCISES = coach.EXERCISES
exercise_session = coach.session


# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def now_local():
    """Local timestamp string used for logged_at (keeps "today" consistent)."""
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def get_db():
    """Open a database connection for the current request context."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all required tables (idempotent) and seed one demo user."""
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    conn = sqlite3.connect(app.config["DATABASE"], timeout=10)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS health_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                heart_rate INTEGER,
                spo2 INTEGER,
                sleep_hours REAL,
                steps INTEGER,
                calories_burned REAL,
                bmi REAL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                activity_type TEXT,
                duration_minutes INTEGER,
                calories_burned REAL,
                logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT,
                recommendation_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                alert_type TEXT,
                message TEXT,
                severity TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )
        # Seed one demo user + a sample health record so the dashboard is never
        # empty on first run.
        if cur.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            cur.execute("INSERT INTO users (name, age) VALUES (?, ?)", ("Demo User", 24))
            user_id = cur.lastrowid
            cur.execute(
                """INSERT INTO health_records
                   (user_id, heart_rate, spo2, sleep_hours, steps, calories_burned, bmi)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, 78, 97, 6.5, 6400, 320.0, 22.5),
            )
            cur.execute(
                """INSERT INTO activities
                   (user_id, activity_type, duration_minutes, calories_burned, logged_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, "Walking", 35, 150.0, now_local()),
            )
        conn.commit()
    finally:
        conn.close()
    init_nutrition_db(app.config["NUTRITION_DATABASE"])


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------
def read_number(form, name, label, low, high, default=None):
    """Read a finite float within [low, high] from a form; raises ValueError."""
    raw = (form.get(name) or "").strip()
    if raw == "":
        if default is not None:
            return default
        raise ValueError(f"{label} is required.")
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(value) or value < low or value > high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}.")
    return value


def read_activity_level(form):
    label = (form.get("activity_level") or "moderate").lower()
    if label not in ACTIVITY_LEVELS:
        raise ValueError("Activity level must be low, moderate or high.")
    return label


# ----------------------------------------------------------------------
# Demo alert-threshold and recommendation logic
# ----------------------------------------------------------------------
def generate_alerts(heart_rate, spo2, sleep_hours):
    """Return a list of demo alert dicts based on simple fixed thresholds.

    These thresholds are illustrative only and are NOT clinically validated.
    """
    alerts = []
    if heart_rate is not None:
        if heart_rate > 130:
            alerts.append({"type": "Heart Rate", "message": "Very high heart rate detected.", "severity": "High"})
        elif heart_rate < 45:
            alerts.append({"type": "Heart Rate", "message": "Unusually low heart rate detected.", "severity": "High"})
    if spo2 is not None and spo2 < 92:
        alerts.append({"type": "SpO2", "message": "Low blood oxygen (SpO2) level detected.", "severity": "High"})
    if sleep_hours is not None and sleep_hours < 4:
        alerts.append({"type": "Sleep", "message": "Very low sleep duration detected.", "severity": "Moderate"})
    return alerts


def generate_recommendations(activity_level, sleep_hours, bmi):
    """Very simple rule-based demo recommendations (not medical advice)."""
    recs = {"exercise": [], "diet": [], "sleep": [], "daily_activity": []}

    if activity_level == "low":
        recs["exercise"].append("Add a 20-30 minute brisk walk to your day.")
        recs["daily_activity"].append("Try to reach at least 6,000 steps/day.")
    elif activity_level == "moderate":
        recs["exercise"].append("Consider adding one extra cardio session per week.")
        recs["daily_activity"].append("Aim for 8,000-10,000 steps/day.")
    else:
        recs["exercise"].append("Great activity level — keep mixing cardio and strength training.")
        recs["daily_activity"].append("Maintain your current activity routine.")

    if sleep_hours is not None and sleep_hours < 6:
        recs["sleep"].append("Try to increase sleep to 7-8 hours for better recovery.")
    else:
        recs["sleep"].append("Your sleep duration looks healthy — keep it consistent.")

    if bmi is not None and bmi >= 25:
        recs["diet"].append("Consider more fiber-rich foods and reduce refined sugar intake.")
    elif bmi is not None and bmi < 18.5:
        recs["diet"].append("Consider a slightly higher calorie intake with balanced nutrients.")
    else:
        recs["diet"].append("Your BMI is in a healthy range — maintain a balanced diet.")
    return recs


# ----------------------------------------------------------------------
# Routes: pages
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


def weekly_calories(db):
    """Calories burned per day (from logged activities) for the last 7 days."""
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    rows = db.execute(
        """SELECT date(logged_at) AS day, SUM(calories_burned) AS total
           FROM activities WHERE date(logged_at) >= ? GROUP BY day""",
        (days[0].isoformat(),),
    ).fetchall()
    totals = {r["day"]: float(r["total"] or 0) for r in rows}
    return {
        "labels": [d.strftime("%a") for d in days],
        "values": [round(totals.get(d.isoformat(), 0), 1) for d in days],
    }


@app.route("/dashboard")
def dashboard():
    db = get_db()
    row = db.execute("SELECT * FROM health_records ORDER BY id DESC LIMIT 1").fetchone()
    record = dict(row) if row else None
    activities = db.execute("SELECT * FROM activities ORDER BY id DESC LIMIT 5").fetchall()
    weekly = weekly_calories(db)
    # Prefer the real calories logged today over the stored wearable-style value.
    if record is not None and weekly["values"][-1] > 0:
        record["calories_burned"] = weekly["values"][-1]
    return render_template("dashboard.html", record=record, activities=activities, weekly=weekly)


@app.route("/activity", methods=["GET", "POST"])
def activity():
    db = get_db()
    if request.method == "POST":
        met_values = {"Walking": 3.5, "Running": 8.0, "Cycling": 6.0, "Other": 4.0}
        activity_type = request.form.get("activity_type", "Walking")
        try:
            if activity_type not in met_values:
                raise ValueError("Choose a valid activity type.")
            duration = int(read_number(request.form, "duration_minutes", "Duration", 1, 600))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("activity"))
        # Simple demo calorie estimate (MET-based, assumes a 70 kg person).
        calories = round(met_values[activity_type] * 3.5 * 70 / 200 * duration, 1)
        db.execute(
            """INSERT INTO activities (user_id, activity_type, duration_minutes, calories_burned, logged_at)
               VALUES (1, ?, ?, ?, ?)""",
            (activity_type, duration, calories, now_local()),
        )
        db.commit()
        flash(f"Logged {duration} min of {activity_type} (~{calories} kcal).", "success")
        return redirect(url_for("activity"))  # Post/Redirect/Get: no duplicate on refresh

    activities = db.execute("SELECT * FROM activities ORDER BY id DESC LIMIT 10").fetchall()
    return render_template("activity.html", activities=activities)


@app.route("/predict", methods=["GET", "POST"])
def predict():
    result, error, input_values = None, None, None
    status = 200
    if request.method == "POST":
        try:
            age = read_number(request.form, "age", "Age", 1, 120)
            heart_rate = read_number(request.form, "heart_rate", "Heart rate", 20, 250)
            spo2 = read_number(request.form, "spo2", "SpO2", 50, 100)
            sleep_hours = read_number(request.form, "sleep_hours", "Sleep hours", 0, 24)
            bmi = read_number(request.form, "bmi", "BMI", 10, 70)
            level_label = read_activity_level(request.form)
        except ValueError as exc:
            error, status = str(exc), 400
        else:
            input_values = {
                "age": age, "heart_rate": heart_rate, "spo2": spo2,
                "sleep_hours": sleep_hours, "bmi": bmi, "activity_level": level_label,
            }
            result = health_model.predict(
                age, heart_rate, spo2, sleep_hours, ACTIVITY_LEVELS[level_label], bmi
            )
            db = get_db()
            # Store the readings so the dashboard shows the latest values
            # (steps / calories are carried over from the previous record).
            prev = db.execute(
                "SELECT steps, calories_burned FROM health_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
            db.execute(
                """INSERT INTO health_records
                   (user_id, heart_rate, spo2, sleep_hours, steps, calories_burned, bmi, recorded_at)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?)""",
                (int(round(heart_rate)), int(round(spo2)), sleep_hours,
                 prev["steps"] if prev else None,
                 prev["calories_burned"] if prev else None, bmi, now_local()),
            )
            for a in generate_alerts(heart_rate, spo2, sleep_hours):
                db.execute(
                    "INSERT INTO alerts (user_id, alert_type, message, severity) VALUES (1, ?, ?, ?)",
                    (a["type"], a["message"], a["severity"]),
                )
            db.commit()
    return render_template(
        "prediction.html", result=result, error=error, input_values=input_values
    ), status


@app.route("/recommendations", methods=["GET", "POST"])
def recommendations():
    status = 200
    activity_level, sleep_hours, bmi = "moderate", 7.0, 22.0
    if request.method == "POST":
        try:
            activity_level = read_activity_level(request.form)
            sleep_hours = read_number(request.form, "sleep_hours", "Sleep hours", 0, 24, default=7.0)
            bmi = read_number(request.form, "bmi", "BMI", 10, 70, default=22.0)
        except ValueError as exc:
            flash(str(exc), "danger")
            activity_level, sleep_hours, bmi = "moderate", 7.0, 22.0
            status = 400
        else:
            recs = generate_recommendations(activity_level, sleep_hours, bmi)
            db = get_db()
            today = date.today().isoformat()
            for category, items in recs.items():
                for text in items:
                    # Skip text that was already saved today (no duplicate rows).
                    exists = db.execute(
                        """SELECT 1 FROM recommendations
                           WHERE user_id=1 AND recommendation_text=? AND date(created_at)=?""",
                        (text, today),
                    ).fetchone()
                    if not exists:
                        db.execute(
                            "INSERT INTO recommendations (user_id, category, recommendation_text, created_at) "
                            "VALUES (1, ?, ?, ?)", (category, text, now_local()),
                        )
            db.commit()
            return render_template("recommendations.html", recs=recs)
    recs = generate_recommendations(activity_level, sleep_hours, bmi)
    return render_template("recommendations.html", recs=recs), status


@app.route("/alerts")
def alerts_page():
    all_alerts = get_db().execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("alerts.html", alerts=all_alerts)


@app.route("/api/health-check")
def health_check():
    """Simple JSON health-check endpoint, also used by Docker/Jenkins."""
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


# ----------------------------------------------------------------------
# Routes: exercise coach
# ----------------------------------------------------------------------
@app.route("/camera")
def camera_page():
    return redirect(url_for("dashboard") + "#exercise-studio")


@app.route("/video_feed")
def video_feed():
    available, reason = coach.backend_status()
    if not available:
        # No OpenCV/MediaPipe (e.g. Docker/CI): show a placeholder, not an error.
        exercise_session.set_status(reason)
        response = send_from_directory(app.static_folder, "img/camera-unavailable.png")
        response.headers["Cache-Control"] = "no-store"
        return response
    return Response(coach.generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/set_exercise", methods=["POST"])
def set_exercise():
    selected = (request.get_json(silent=True) or {}).get("exercise", "squat")
    try:
        exercise_session.select(selected)
    except ValueError:
        return jsonify({"error": "Unsupported exercise"}), 400
    return jsonify({
        "ok": True, **exercise_session.snapshot(),
        "label": EXERCISES[selected]["label"], "tutorial_url": EXERCISES[selected]["tutorial"],
    })


@app.route("/exercise_data")
@app.route("/squat_data")  # legacy name kept for backwards compatibility
def exercise_data():
    snap = exercise_session.snapshot()
    selected = snap["exercise"]
    return jsonify({
        **snap,
        "squats": snap["reps"], "count": snap["reps"], "position": snap["stage"],  # legacy keys
        "label": EXERCISES[selected]["label"],
        "tutorial_url": EXERCISES[selected]["tutorial"],
        "available_exercises": [{"id": k, "label": v["label"]} for k, v in EXERCISES.items()],
    })


@app.route("/reset_exercise", methods=["GET", "POST"])
@app.route("/reset_squats", methods=["GET", "POST"])  # legacy name
def reset_exercise():
    exercise_session.reset()
    snap = exercise_session.snapshot()
    return jsonify({"status": "reset", "squats": 0, **snap})


# Make sure the databases exist when imported (pytest, gunicorn) or run directly.
init_db()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
