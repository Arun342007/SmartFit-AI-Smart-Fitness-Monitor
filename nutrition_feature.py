"""Nutrition journal blueprint for the Smart Fitness Monitor.

Registered in app.py (``app.register_blueprint(nutrition_bp)``). Pages and API:

    GET    /nutrition                  journal page (templates/nutrition.html)
    GET    /nutrition/api/summary      day totals, meals and the 7-day trend
    POST   /nutrition/api/meals        add a meal (JSON)
    DELETE /nutrition/api/meals/<id>   delete a meal

The database file location comes from ``app.config["NUTRITION_DATABASE"]``.
"""
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request

nutrition_bp = Blueprint("nutrition", __name__)

MEAL_CATEGORIES = ("Breakfast", "Lunch", "Dinner", "Snack", "Pre-workout", "Post-workout")
LIMITS = {"calories": 10000, "protein": 500, "carbs": 1000, "fat": 500}


def _connect():
    conn = sqlite3.connect(current_app.config["NUTRITION_DATABASE"], timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_nutrition_db(path):
    """Create the nutrition table if needed (called once at app start-up)."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS nutrition_meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meal TEXT NOT NULL,
                category TEXT NOT NULL,
                meal_date TEXT NOT NULL,
                calories REAL NOT NULL DEFAULT 0,
                protein REAL NOT NULL DEFAULT 0,
                carbs REAL NOT NULL DEFAULT 0,
                fat REAL NOT NULL DEFAULT 0,
                portion TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL)"""
        )
        conn.commit()


def _item(row):
    return {
        "id": row["id"], "meal": row["meal"], "category": row["category"],
        "date": row["meal_date"], "calories": row["calories"],
        "protein": row["protein"], "carbs": row["carbs"], "fat": row["fat"],
        "portion": row["portion"], "created_at": row["created_at"],
    }


def _number(payload, key):
    try:
        value = float(payload.get(key, 0))
    except (TypeError, ValueError):
        raise ValueError(f"{key.title()} must be a number.")
    if value != value or value < 0 or value > LIMITS[key]:  # value != value -> NaN
        raise ValueError(f"{key.title()} must be between 0 and {LIMITS[key]}.")
    return value


@nutrition_bp.get("/nutrition")
def nutrition_page():
    return render_template("nutrition.html")


@nutrition_bp.get("/nutrition/api/summary")
def nutrition_summary():
    try:
        selected = date.fromisoformat(request.args.get("date", date.today().isoformat()))
    except ValueError:
        return jsonify({"error": "Invalid date."}), 400
    start = selected - timedelta(days=6)
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM nutrition_meals WHERE meal_date=? ORDER BY id DESC",
            (selected.isoformat(),),
        ).fetchall()
        week_rows = conn.execute(
            "SELECT meal_date, SUM(calories) AS calories FROM nutrition_meals "
            "WHERE meal_date BETWEEN ? AND ? GROUP BY meal_date",
            (start.isoformat(), selected.isoformat()),
        ).fetchall()
    totals = {k: sum(float(r[k]) for r in rows) for k in LIMITS}
    by_day = {r["meal_date"]: float(r["calories"] or 0) for r in week_rows}
    week = []
    for i in range(7):
        day = start + timedelta(days=i)
        week.append({"date": day.isoformat(), "day": day.strftime("%a"),
                     "calories": by_day.get(day.isoformat(), 0)})
    return jsonify({"today": totals, "meals": [_item(r) for r in rows], "week": week})


@nutrition_bp.post("/nutrition/api/meals")
def nutrition_add_meal():
    payload = request.get_json(silent=True) or {}
    meal = str(payload.get("meal", "")).strip()
    if not meal or len(meal) > 100:
        return jsonify({"error": "Enter a meal name (up to 100 characters)."}), 400
    category = str(payload.get("category", "Snack"))
    if category not in MEAL_CATEGORIES:
        return jsonify({"error": "Choose a valid meal type."}), 400
    try:
        meal_date = date.fromisoformat(str(payload.get("date", date.today().isoformat())))
        if meal_date > date.today() + timedelta(days=1):
            raise ValueError("Date cannot be more than one day in the future.")
        values = {key: _number(payload, key) for key in LIMITS}
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    with closing(_connect()) as conn:
        cur = conn.execute(
            "INSERT INTO nutrition_meals "
            "(meal, category, meal_date, calories, protein, carbs, fat, portion, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (meal, category, meal_date.isoformat(), values["calories"], values["protein"],
             values["carbs"], values["fat"], str(payload.get("portion", ""))[:120],
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        meal_id = cur.lastrowid
    return jsonify({"ok": True, "id": meal_id}), 201


@nutrition_bp.delete("/nutrition/api/meals/<int:meal_id>")
def nutrition_delete_meal(meal_id):
    with closing(_connect()) as conn:
        cur = conn.execute("DELETE FROM nutrition_meals WHERE id=?", (meal_id,))
        conn.commit()
        deleted = cur.rowcount
    if deleted == 0:
        return jsonify({"error": "Meal entry not found."}), 404
    return jsonify({"ok": True})
