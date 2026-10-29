"""Tests for the pose-coach logic. They use fake landmarks: no camera,
OpenCV or MediaPipe is needed."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from camera.coach import EXERCISES, ExerciseSession, Landmark as L, calculate_angle  # noqa: E402


def landmarks(**points):
    """33 invisible landmarks, with the named ones set to (x, y[, visibility])."""
    lms = [SimpleNamespace(x=0.0, y=0.0, visibility=0.0) for _ in range(33)]
    for name, value in points.items():
        x, y, *vis = value
        lms[int(L[name.upper()])] = SimpleNamespace(x=x, y=y, visibility=vis[0] if vis else 1.0)
    return lms


def legs(knee_bend):
    """Both legs. 'straight' = 180 degrees, 'bent' = 90 degrees at the knee."""
    hip = (0.5, 0.4) if knee_bend == "straight" else (0.7, 0.6)
    knee = (0.5, 0.6)
    ankle = (0.5, 0.8)
    pts = {}
    for side in ("left", "right"):
        pts[f"{side}_hip"], pts[f"{side}_knee"], pts[f"{side}_ankle"] = hip, knee, ankle
    return landmarks(**pts)


def arms(elbow_bend):
    wrist = (0.5, 0.7) if elbow_bend == "straight" else (0.7, 0.5)
    pts = {}
    for side in ("left", "right"):
        pts[f"{side}_shoulder"], pts[f"{side}_elbow"], pts[f"{side}_wrist"] = (0.5, 0.3), (0.5, 0.5), wrist
    return landmarks(**pts)


class AngleTests(unittest.TestCase):
    def test_right_angle(self):
        self.assertAlmostEqual(calculate_angle((0, 1), (0, 0), (1, 0)), 90)

    def test_straight_line(self):
        self.assertAlmostEqual(calculate_angle((0, 0), (1, 0), (2, 0)), 180)

    def test_symmetric_and_in_range(self):
        a, b, c = (0.1, 0.9), (0.4, 0.5), (0.8, 0.7)
        self.assertAlmostEqual(calculate_angle(a, b, c), calculate_angle(c, b, a))
        self.assertTrue(0 <= calculate_angle(a, b, c) <= 180)


class SessionTests(unittest.TestCase):
    def test_all_exercises_have_label_and_tutorial(self):
        self.assertEqual(len(EXERCISES), 7)
        for key, meta in EXERCISES.items():
            self.assertTrue(meta["label"])
            self.assertTrue(meta["tutorial"].startswith("https://www.youtube.com/results?search_query="))
            ExerciseSession(key)  # every key must have an analyser

    def test_select_unknown_raises(self):
        with self.assertRaises(ValueError):
            ExerciseSession().select("burpee")

    def test_reset(self):
        s = ExerciseSession("squat")
        s._state["reps"] = 4
        s.reset()
        self.assertEqual(s.snapshot()["reps"], 0)


class RepCountingTests(unittest.TestCase):
    def feed(self, session, frames):
        for frame in frames:
            session.analyse(frame)
        return session.snapshot()["reps"]

    def test_squat_counts_one_rep_per_down_up_cycle(self):
        s = ExerciseSession("squat")
        self.assertEqual(self.feed(s, [legs("straight")]), 0)          # standing: no rep
        self.assertEqual(self.feed(s, [legs("bent")]), 0)              # down: not yet
        self.assertEqual(self.feed(s, [legs("straight")]), 1)          # up: counted
        self.assertEqual(self.feed(s, [legs("straight")] * 5), 1)      # holding: not recounted
        self.assertEqual(self.feed(s, [legs("bent"), legs("straight")]), 2)

    def test_lunge_counts(self):
        s = ExerciseSession("lunge")
        self.assertEqual(self.feed(s, [legs("straight"), legs("bent"), legs("straight")]), 1)

    def test_pushup_counts(self):
        s = ExerciseSession("pushup")
        self.assertEqual(self.feed(s, [arms("straight"), arms("bent"), arms("straight")]), 1)

    def test_pullup_counts(self):
        s = ExerciseSession("pullup")
        self.assertEqual(self.feed(s, [arms("straight"), arms("bent"), arms("straight")]), 1)

    def test_bicep_curl_needs_full_curl(self):
        s = ExerciseSession("bicep_curl")
        self.assertEqual(self.feed(s, [arms("straight"), arms("bent"), arms("straight")]), 0)  # 90 deg is not a curl
        tight = landmarks(
            left_shoulder=(0.5, 0.3), left_elbow=(0.5, 0.5), left_wrist=(0.5, 0.3),
            right_shoulder=(0.5, 0.3), right_elbow=(0.5, 0.5), right_wrist=(0.5, 0.3))
        self.assertEqual(self.feed(s, [tight, arms("straight")]), 1)

    def test_shoulder_press_does_not_count_before_bottom_position(self):
        s = ExerciseSession("shoulder_press")
        self.assertEqual(self.feed(s, [arms("straight")] * 3), 0)      # bug fix: no free rep
        self.assertEqual(self.feed(s, [arms("bent"), arms("straight")]), 1)

    def test_jumping_jack(self):
        closed = landmarks(left_shoulder=(0.45, 0.3), right_shoulder=(0.55, 0.3),
                           left_wrist=(0.45, 0.6), right_wrist=(0.55, 0.6),
                           left_ankle=(0.47, 0.9), right_ankle=(0.53, 0.9))
        opened = landmarks(left_shoulder=(0.45, 0.3), right_shoulder=(0.55, 0.3),
                           left_wrist=(0.30, 0.1), right_wrist=(0.70, 0.1),
                           left_ankle=(0.30, 0.9), right_ankle=(0.70, 0.9))
        s = ExerciseSession("jumping_jack")
        self.assertEqual(self.feed(s, [closed, closed]), 0)
        self.assertEqual(self.feed(s, [opened, closed]), 1)

    def test_invisible_body_waits_and_never_counts(self):
        for key in EXERCISES:
            with self.subTest(exercise=key):
                s = ExerciseSession(key)
                feedback, form, _angle, _stage = s.analyse(landmarks())
                self.assertEqual(form, "WAITING")
                self.assertEqual(s.snapshot()["reps"], 0)
                self.assertTrue(feedback)


class FormCueTests(unittest.TestCase):
    def test_pushup_sagging_hips_flagged(self):
        pts = {}
        for side in ("left", "right"):
            pts[f"{side}_shoulder"], pts[f"{side}_elbow"], pts[f"{side}_wrist"] = (0.2, 0.5), (0.2, 0.65), (0.2, 0.8)
            pts[f"{side}_hip"], pts[f"{side}_ankle"] = (0.5, 0.8), (0.8, 0.5)  # hip far below the body line
        _fb, form, _a, _s = ExerciseSession("pushup").analyse(landmarks(**pts))
        self.assertEqual(form, "WRONG")

    def test_pushup_straight_body_is_good(self):
        pts = {}
        for side in ("left", "right"):
            pts[f"{side}_shoulder"], pts[f"{side}_elbow"], pts[f"{side}_wrist"] = (0.2, 0.5), (0.2, 0.65), (0.2, 0.8)
            pts[f"{side}_hip"], pts[f"{side}_ankle"] = (0.5, 0.5), (0.8, 0.5)
        _fb, form, _a, _s = ExerciseSession("pushup").analyse(landmarks(**pts))
        self.assertEqual(form, "GOOD")

    def test_squat_knees_caving_flagged(self):
        pts = {}
        for side, ankle_x in (("left", 0.4), ("right", 0.6)):
            pts[f"{side}_hip"], pts[f"{side}_knee"], pts[f"{side}_ankle"] = (0.5, 0.4), (ankle_x + 0.2, 0.6), (ankle_x, 0.8)
        _fb, form, _a, _s = ExerciseSession("squat").analyse(landmarks(**pts))
        self.assertEqual(form, "WRONG")

    def test_better_seen_arm_is_used_in_side_view(self):
        # Right arm is bent and clearly visible; the left arm is straight but barely visible.
        pts = dict(
            right_shoulder=(0.5, 0.3, 0.95), right_elbow=(0.5, 0.5, 0.95), right_wrist=(0.7, 0.5, 0.95),
            left_shoulder=(0.5, 0.3, 0.4), left_elbow=(0.5, 0.5, 0.4), left_wrist=(0.5, 0.7, 0.4))
        s = ExerciseSession("pushup")
        s.analyse(landmarks(**pts))
        self.assertEqual(s.snapshot()["angle"], 90)


if __name__ == "__main__":
    unittest.main()
