"""Tests for the demo health-risk ML model."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.health_model import ACTIVITY_LEVELS, HealthRiskModel  # noqa: E402


class HealthModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = HealthRiskModel()
        cls.accuracy = cls.model.train(verbose=False)

    def test_prediction_is_a_valid_label(self):
        result = self.model.predict(age=30, heart_rate=75, spo2=97, sleep_hours=7, activity_level=1, bmi=22)
        self.assertIn(result, ("Low", "Moderate", "High"))
        self.assertIsInstance(result, str)

    def test_clearly_unhealthy_inputs_are_not_low_risk(self):
        result = self.model.predict(age=65, heart_rate=135, spo2=89, sleep_hours=3, activity_level=0, bmi=33)
        self.assertNotEqual(result, "Low")

    def test_accuracy_is_reasonable_for_demo_data(self):
        self.assertGreater(self.accuracy, 0.6)
        self.assertGreater(self.model.metrics["cv_accuracy_mean"], 0.6)
        self.assertEqual(self.model.metrics["rows"], 300)

    def test_predict_trains_lazily(self):
        fresh = HealthRiskModel()
        self.assertFalse(fresh.is_trained)
        fresh.predict(30, 75, 97, 7, 1, 22)
        self.assertTrue(fresh.is_trained)

    def test_activity_level_encoding(self):
        self.assertEqual(ACTIVITY_LEVELS, {"low": 0, "moderate": 1, "high": 2})


if __name__ == "__main__":
    unittest.main()
