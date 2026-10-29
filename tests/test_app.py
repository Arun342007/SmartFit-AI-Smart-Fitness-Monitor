"""Tests for the Flask routes, validation, alerts and recommendations."""
import os
import sqlite3
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as flask_app_module  # noqa: E402
from camera import coach  # noqa: E402

LOW_RISK = {"age": "25", "heart_rate": "70", "spo2": "98", "sleep_hours": "8",
            "bmi": "21", "activity_level": "high"}
HIGH_RISK = {"age": "65", "heart_rate": "135", "spo2": "89", "sleep_hours": "3",
             "bmi": "33", "activity_level": "low"}


class AppTestCase(unittest.TestCase):
    def setUp(self):
        flask_app_module.app.config["TESTING"] = True
        flask_app_module.init_db()
        coach.session.select("squat")
        self.client = flask_app_module.app.test_client()


class PageTests(AppTestCase):
    def test_home_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Smart Fitness", r.data)

    def test_dashboard_page_has_real_chart_data_and_all_exercises(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Dashboard", r.data)
        self.assertIn(b'id="sfWeeklyData"', r.data)
        for option in (b"Squat", b"Push-up", b"Pull-up", b"Lunge", b"Jumping jack",
                       b"Bicep curl", b"Shoulder press"):
            self.assertIn(option, r.data)

    def test_all_simple_pages_render(self):
        for path in ("/activity", "/predict", "/recommendations", "/alerts", "/nutrition"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_camera_route_redirects_to_exercise_studio(self):
        r = self.client.get("/camera")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/dashboard#exercise-studio"))

    def test_health_check_api(self):
        r = self.client.get("/api/health-check")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")


class ActivityTests(AppTestCase):
    def test_activity_post_redirects_and_shows_flash(self):
        r = self.client.post("/activity", data={"activity_type": "Running", "duration_minutes": "20"})
        self.assertEqual(r.status_code, 302)  # Post/Redirect/Get
        page = self.client.get("/activity")
        self.assertIn(b"Logged 20 min of Running", page.data)
        self.assertIn(b"Running", page.data)

    def test_activity_calories_use_met_formula(self):
        self.client.post("/activity", data={"activity_type": "Running", "duration_minutes": "30"})
        db = sqlite3.connect(flask_app_module.DB_PATH)
        calories = db.execute(
            "SELECT calories_burned FROM activities ORDER BY id DESC LIMIT 1").fetchone()[0]
        db.close()
        self.assertAlmostEqual(calories, 8.0 * 3.5 * 70 / 200 * 30, places=1)

    def test_activity_invalid_input_does_not_crash(self):
        for data in ({"activity_type": "Running", "duration_minutes": "abc"},
                     {"activity_type": "Running", "duration_minutes": ""},
                     {"activity_type": "Running", "duration_minutes": "-5"},
                     {"activity_type": "Running", "duration_minutes": "99999"},
                     {"activity_type": "Skydiving", "duration_minutes": "20"}):
            with self.subTest(data=data):
                r = self.client.post("/activity", data=data, follow_redirects=True)
                self.assertEqual(r.status_code, 200)
                self.assertIn(b"alert-danger", r.data)


class PredictionTests(AppTestCase):
    def test_low_risk_prediction_renders_a_label(self):
        r = self.client.post("/predict", data=LOW_RISK)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(f"{label} Risk".encode() in r.data for label in ("Low", "Moderate", "High")))

    def test_prediction_saves_record_for_dashboard(self):
        self.client.post("/predict", data={**LOW_RISK, "heart_rate": "88"})
        db = sqlite3.connect(flask_app_module.DB_PATH)
        hr = db.execute("SELECT heart_rate FROM health_records ORDER BY id DESC LIMIT 1").fetchone()[0]
        db.close()
        self.assertEqual(hr, 88)

    def test_high_risk_triggers_alerts(self):
        r = self.client.post("/predict", data=HIGH_RISK)
        self.assertEqual(r.status_code, 200)
        alerts = self.client.get("/alerts")
        self.assertIn(b"Very high heart rate", alerts.data)
        self.assertIn(b"Low blood oxygen", alerts.data)

    def test_invalid_input_returns_400_with_message(self):
        for field, value in (("age", "abc"), ("age", "500"), ("heart_rate", "-1"),
                             ("spo2", "nan"), ("bmi", ""), ("sleep_hours", "99"),
                             ("activity_level", "extreme")):
            with self.subTest(field=field, value=value):
                r = self.client.post("/predict", data={**LOW_RISK, field: value})
                self.assertEqual(r.status_code, 400)
                self.assertIn(b"alert-danger", r.data)


class RecommendationTests(AppTestCase):
    def test_get_defaults(self):
        r = self.client.get("/recommendations")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Recommendations", r.data)

    def test_post_valid_and_no_duplicate_rows_same_day(self):
        data = {"activity_level": "low", "sleep_hours": "5", "bmi": "27"}
        self.assertEqual(self.client.post("/recommendations", data=data).status_code, 200)
        count = lambda: sqlite3.connect(flask_app_module.DB_PATH).execute(  # noqa: E731
            "SELECT COUNT(*) FROM recommendations").fetchone()[0]
        first = count()
        self.client.post("/recommendations", data=data)
        self.assertEqual(count(), first)

    def test_post_invalid_returns_400_not_500(self):
        r = self.client.post("/recommendations",
                             data={"activity_level": "low", "sleep_hours": "abc", "bmi": "22"})
        self.assertEqual(r.status_code, 400)

    def test_rules(self):
        recs = flask_app_module.generate_recommendations("low", 5, 27)
        self.assertIn("Try to increase sleep", recs["sleep"][0])
        self.assertIn("fiber", recs["diet"][0])
        self.assertIn("brisk walk", recs["exercise"][0])


class AlertLogicTests(unittest.TestCase):
    def test_all_three_alerts(self):
        alerts = flask_app_module.generate_alerts(heart_rate=150, spo2=85, sleep_hours=2)
        self.assertEqual(len(alerts), 3)

    def test_low_heart_rate_alert(self):
        self.assertEqual(flask_app_module.generate_alerts(40, 98, 8)[0]["type"], "Heart Rate")

    def test_no_alerts(self):
        self.assertEqual(flask_app_module.generate_alerts(75, 98, 8), [])


class DatabaseTests(AppTestCase):
    def test_tables_exist(self):
        self.assertTrue(os.path.exists(flask_app_module.DB_PATH))
        db = sqlite3.connect(flask_app_module.DB_PATH)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        db.close()
        self.assertTrue({"users", "health_records", "activities", "recommendations", "alerts"} <= tables)

    def test_databases_live_in_the_test_instance_folder(self):
        self.assertEqual(os.path.dirname(flask_app_module.DB_PATH),
                         os.environ["SMARTFIT_INSTANCE_DIR"])


class ValidationHelperTests(unittest.TestCase):
    def test_read_number(self):
        read = flask_app_module.read_number
        self.assertEqual(read({"x": "5"}, "x", "X", 0, 10), 5.0)
        self.assertEqual(read({}, "x", "X", 0, 10, default=3.0), 3.0)
        for bad in ("abc", "11", "-1", "inf", "nan", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                read({"x": bad}, "x", "X", 0, 10)


class ExerciseEndpointTests(AppTestCase):
    def test_set_exercise_and_data(self):
        r = self.client.post("/set_exercise", json={"exercise": "pushup"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["label"], "Push-up")
        data = self.client.get("/exercise_data").get_json()
        self.assertEqual(data["exercise"], "pushup")
        self.assertEqual(data["reps"], 0)
        self.assertIn("youtube.com", data["tutorial_url"])
        self.assertEqual(len(data["available_exercises"]), 7)

    def test_unsupported_exercise_rejected(self):
        self.assertEqual(self.client.post("/set_exercise", json={"exercise": "burpee"}).status_code, 400)

    def test_legacy_routes_still_work(self):
        self.assertEqual(self.client.get("/squat_data").status_code, 200)
        self.assertEqual(self.client.post("/reset_squats").status_code, 200)
        self.assertEqual(self.client.post("/reset_exercise").status_code, 200)

    def test_reset_clears_reps(self):
        coach.session._state["reps"] = 9
        r = self.client.post("/reset_exercise")
        self.assertEqual(r.get_json()["reps"], 0)

    def test_video_feed_placeholder_without_camera_backend(self):
        with mock.patch.object(coach, "backend_status", return_value=(False, "no camera libs")):
            r = self.client.get("/video_feed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/png")
        self.assertIn("no camera libs", self.client.get("/exercise_data").get_json()["feedback"])

    def test_importing_app_does_not_import_opencv_or_mediapipe(self):
        # Guards the CI/Docker fix: heavy camera libs must stay lazy.
        import subprocess
        code = ("import sys, os; os.environ['SMARTFIT_INSTANCE_DIR']=sys.argv[1];"
                "import app; print('cv2' in sys.modules, 'mediapipe' in sys.modules)")
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        out = subprocess.run([sys.executable, "-c", code, os.environ["SMARTFIT_INSTANCE_DIR"]],
                             cwd=root, capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(out[-2:], ["False", "False"])


if __name__ == "__main__":
    unittest.main()
