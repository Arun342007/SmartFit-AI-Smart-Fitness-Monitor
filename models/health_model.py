"""
health_model.py
----------------
A small, self-contained DEMO machine-learning model used for the
"Health Risk Prediction" feature.

The model is trained on a small SYNTHETIC dataset (data/sample_health_data.csv)
with scikit-learn's RandomForestClassifier. It exists purely to demonstrate an
AI/ML component integrated into the SCM/DevOps pipeline.

DISCLAIMER: This is an educational demo model only. It must NEVER be used for
real medical decisions or real patient data.
"""

import os

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "data", "sample_health_data.csv")

LABELS = ["Low", "Moderate", "High"]
FEATURE_COLUMNS = ["age", "heart_rate", "spo2", "sleep_hours", "activity_level", "bmi"]
ACTIVITY_LEVELS = {"low": 0, "moderate": 1, "high": 2}


class HealthRiskModel:
    """Wraps a scikit-learn classifier trained on demo health data."""

    def __init__(self, data_path=DATA_PATH):
        self.data_path = data_path
        # class_weight="balanced" compensates for the small number of "Low" rows.
        self.model = RandomForestClassifier(
            n_estimators=100, max_depth=6, random_state=42, class_weight="balanced"
        )
        self.feature_columns = list(FEATURE_COLUMNS)
        self.is_trained = False
        self.metrics = {}

    def train(self, verbose=True):
        """Train on the synthetic CSV; returns hold-out accuracy.

        Also stores 5-fold cross-validated accuracy in ``self.metrics``, which
        is a steadier estimate than a single split on a 300-row dataset.
        """
        df = pd.read_csv(self.data_path)
        X, y = df[self.feature_columns], df["risk_label"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        self.model.fit(X_train, y_train)
        self.is_trained = True

        holdout = float(self.model.score(X_test, y_test))
        cv = cross_val_score(
            RandomForestClassifier(
                n_estimators=100, max_depth=6, random_state=42, class_weight="balanced"
            ),
            X, y, cv=5,
        )
        self.metrics = {
            "holdout_accuracy": round(holdout, 3),
            "cv_accuracy_mean": round(float(cv.mean()), 3),
            "rows": int(len(df)),
        }
        if verbose:
            print(f"[HealthRiskModel] Demo model trained. {self.metrics}")
        return holdout

    def predict(self, age, heart_rate, spo2, sleep_hours, activity_level, bmi):
        """Predict a risk label ('Low' / 'Moderate' / 'High') for one sample."""
        if not self.is_trained:
            self.train(verbose=False)
        row = pd.DataFrame(
            [[age, heart_rate, spo2, sleep_hours, activity_level, bmi]],
            columns=self.feature_columns,
        )
        return str(self.model.predict(row)[0])


if __name__ == "__main__":
    m = HealthRiskModel()
    m.train()
    print("Sample prediction:", m.predict(45, 110, 93, 4, 0, 29))
