"""Tests for the nutrition journal blueprint."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as flask_app_module  # noqa: E402


class NutritionTests(unittest.TestCase):
    def setUp(self):
        flask_app_module.app.config["TESTING"] = True
        flask_app_module.init_db()
        self.client = flask_app_module.app.test_client()
        # Start every test from an empty journal.
        import sqlite3
        db = sqlite3.connect(flask_app_module.NUTRITION_DB_PATH)
        db.execute("DELETE FROM nutrition_meals")
        db.commit()
        db.close()

    def add(self, **overrides):
        payload = {"meal": "Oats", "category": "Breakfast", "date": date.today().isoformat(),
                   "calories": 350, "protein": 12, "carbs": 55, "fat": 7, "portion": "1 bowl"}
        payload.update(overrides)
        return self.client.post("/nutrition/api/meals", json=payload)

    def test_page_renders_and_nav_link_exists(self):
        self.assertEqual(self.client.get("/nutrition").status_code, 200)
        self.assertIn(b"/nutrition", self.client.get("/").data)

    def test_add_and_summary(self):
        self.assertEqual(self.add().status_code, 201)
        self.assertEqual(self.add(meal="Rice", calories=500, protein=10, carbs=90, fat=5).status_code, 201)
        data = self.client.get("/nutrition/api/summary").get_json()
        self.assertEqual(data["today"]["calories"], 850)
        self.assertEqual(data["today"]["protein"], 22)
        self.assertEqual(len(data["meals"]), 2)
        self.assertEqual(len(data["week"]), 7)
        self.assertEqual(data["week"][-1]["calories"], 850)

    def test_summary_other_day_is_separate(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.add(date=yesterday, calories=200)
        today = self.client.get("/nutrition/api/summary").get_json()
        self.assertEqual(today["today"]["calories"], 0)
        self.assertEqual(today["week"][-2]["calories"], 200)

    def test_delete(self):
        meal_id = self.add().get_json()["id"]
        self.assertEqual(self.client.delete(f"/nutrition/api/meals/{meal_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/nutrition/api/meals/{meal_id}").status_code, 404)

    def test_validation(self):
        bad_payloads = [
            {"meal": ""}, {"meal": "x" * 101}, {"category": "Brunch"},
            {"calories": -1}, {"calories": 10001}, {"protein": "abc"}, {"fat": float("nan")},
            {"date": "not-a-date"}, {"date": (date.today() + timedelta(days=30)).isoformat()},
        ]
        for overrides in bad_payloads:
            with self.subTest(overrides=overrides):
                self.assertEqual(self.add(**overrides).status_code, 400)

    def test_summary_invalid_date(self):
        self.assertEqual(self.client.get("/nutrition/api/summary?date=oops").status_code, 400)


if __name__ == "__main__":
    unittest.main()
