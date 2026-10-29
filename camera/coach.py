"""
camera/coach.py
---------------
Multi-exercise pose coach (prototype).

* The rep-counting / form-cue logic is plain Python. It only needs objects with
  ``.x``, ``.y`` and ``.visibility`` attributes (MediaPipe landmarks look like
  that), so it can be unit-tested without a webcam, OpenCV or MediaPipe.
* OpenCV and MediaPipe are imported lazily, only when a camera stream is
  actually started. Importing this module (and therefore the Flask app) works
  in CI, in Docker and on machines without a webcam / OpenGL libraries.

DISCLAIMER: the rules below are simple landmark-angle heuristics. They are not a
trained form classifier and not a medical or safety assessment.
"""

import math
import os
import threading
from enum import IntEnum
from urllib.parse import quote_plus


# ----------------------------------------------------------------------
# Landmarks (MediaPipe Pose indices) and exercise catalogue
# ----------------------------------------------------------------------
class Landmark(IntEnum):
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28


L = Landmark

_TUTORIAL_QUERIES = {
    "squat": "squat proper form tutorial",
    "pushup": "push up proper form tutorial",
    "pullup": "pull up proper form tutorial",
    "lunge": "bodyweight lunge proper form tutorial",
    "jumping_jack": "jumping jacks proper form tutorial",
    "bicep_curl": "bicep curl proper form tutorial",
    "shoulder_press": "dumbbell shoulder press proper form tutorial",
}
_LABELS = {
    "squat": "Squat",
    "pushup": "Push-up",
    "pullup": "Pull-up",
    "lunge": "Lunge",
    "jumping_jack": "Jumping jack",
    "bicep_curl": "Bicep curl",
    "shoulder_press": "Shoulder press",
}
EXERCISES = {
    key: {
        "label": _LABELS[key],
        "tutorial": "https://www.youtube.com/results?search_query=" + quote_plus(query),
    }
    for key, query in _TUTORIAL_QUERIES.items()
}

ARM_TRIPLES = (
    (L.LEFT_SHOULDER, L.LEFT_ELBOW, L.LEFT_WRIST),
    (L.RIGHT_SHOULDER, L.RIGHT_ELBOW, L.RIGHT_WRIST),
)
LEG_TRIPLES = (
    (L.LEFT_HIP, L.LEFT_KNEE, L.LEFT_ANKLE),
    (L.RIGHT_HIP, L.RIGHT_KNEE, L.RIGHT_ANKLE),
)
TORSO_TRIPLES = (  # shoulder, hip, ankle for each side
    (L.LEFT_SHOULDER, L.LEFT_HIP, L.LEFT_ANKLE),
    (L.RIGHT_SHOULDER, L.RIGHT_HIP, L.RIGHT_ANKLE),
)
SIDE_PAIRS = (  # shoulder, hip for each side
    (L.LEFT_SHOULDER, L.LEFT_HIP),
    (L.RIGHT_SHOULDER, L.RIGHT_HIP),
)


# ----------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------
def calculate_angle(a, b, c):
    """Return the 0-180 degree angle ABC from (x, y) points."""
    angle = abs(
        math.degrees(
            math.atan2(c[1] - b[1], c[0] - b[0])
            - math.atan2(a[1] - b[1], a[0] - b[0])
        )
    )
    return 360 - angle if angle > 180 else angle


def _point(landmarks, idx):
    lm = landmarks[int(idx)]
    return (lm.x, lm.y)


def _vis(landmarks, idx):
    return getattr(landmarks[int(idx)], "visibility", 1.0)


def _group_visibility(landmarks, ids):
    return min(_vis(landmarks, i) for i in ids)


def _joint_angle(landmarks, triples, minimum=0.35):
    """Mean angle of the visible limbs in ``triples``.

    If both sides are visible but one is clearly better seen (typical for a
    side-on camera view) only the better side is used, which keeps the angle
    from being dragged around by a half-hidden limb.
    Returns ``None`` when no limb is visible enough.
    """
    seen = []
    for triple in triples:
        vis = _group_visibility(landmarks, triple)
        if vis >= minimum:
            seen.append((vis, calculate_angle(*(_point(landmarks, i) for i in triple))))
    if not seen:
        return None
    if len(seen) == 2 and abs(seen[0][0] - seen[1][0]) > 0.25:
        return max(seen)[1]
    return sum(angle for _, angle in seen) / len(seen)


def _best_group(landmarks, groups, minimum=0.35):
    """Return the points of the best visible landmark group, or ``None``."""
    best, best_vis = None, minimum
    for group in groups:
        vis = _group_visibility(landmarks, group)
        if vis >= best_vis:
            best, best_vis = group, vis
    return None if best is None else [_point(landmarks, i) for i in best]


# ----------------------------------------------------------------------
# Session state + analysis
# ----------------------------------------------------------------------
class ExerciseSession:
    """Thread-safe state of the current coaching session (single camera)."""

    def __init__(self, exercise="squat"):
        self._lock = threading.RLock()
        self._armed = False  # True once the "down/top" half of a rep was reached
        self._state = {}
        self.select(exercise)

    # -- public state API ------------------------------------------------
    def select(self, exercise):
        if exercise not in EXERCISES:
            raise ValueError(f"Unsupported exercise: {exercise}")
        with self._lock:
            self._armed = False
            self._state = {
                "exercise": exercise, "reps": 0, "stage": "Ready", "angle": 0,
                "feedback": "Exercise changed. Get into the starting position.",
                "form": "WAITING", "tutorial": exercise,
            }

    def reset(self):
        with self._lock:
            self._armed = False
            self._state.update(
                reps=0, stage="Ready", angle=0, form="WAITING",
                feedback="Counter reset. Start when ready.",
            )

    def set_status(self, feedback, form="WAITING"):
        with self._lock:
            self._state.update(feedback=feedback, form=form)

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    @property
    def exercise(self):
        with self._lock:
            return self._state["exercise"]

    # -- analysis ----------------------------------------------------------
    def analyse(self, landmarks):
        """Update the state from one frame of landmarks.

        Returns ``(feedback, form, angle, stage)``.
        """
        with self._lock:
            exercise = self._state["exercise"]
            handler = getattr(self, f"_analyse_{exercise}")
            result = handler(landmarks)
            feedback, form, angle, stage = result
            self._state.update(
                feedback=feedback, form=form, angle=int(angle), stage=stage,
                tutorial=exercise,
            )
            return feedback, form, int(angle), stage

    def _count(self):
        self._state["reps"] += 1

    # Each handler returns (feedback, form, angle, stage).
    def _waiting(self, message):
        return message, "WAITING", 0, self._state["stage"]

    def _leg_exercise(self, landmarks, down_below, label_down, label_up, label_mid):
        angle = _joint_angle(landmarks, LEG_TRIPLES)
        if angle is None:
            return self._waiting("Show your hips, knees and ankles clearly to the camera.")

        form, feedback = "GOOD", label_mid
        # Approximate front-view knee-tracking cue (knee x vs ankle x).
        knees_ankles = [L.LEFT_KNEE, L.LEFT_ANKLE, L.RIGHT_KNEE, L.RIGHT_ANKLE]
        if all(_vis(landmarks, i) >= 0.45 for i in knees_ankles):
            lk, la = _point(landmarks, L.LEFT_KNEE), _point(landmarks, L.LEFT_ANKLE)
            rk, ra = _point(landmarks, L.RIGHT_KNEE), _point(landmarks, L.RIGHT_ANKLE)
            if max(abs(lk[0] - la[0]), abs(rk[0] - ra[0])) > 0.10:
                form = "WRONG"
                feedback = "Form looks off: keep your knees tracking in line with your feet."

        stage = self._state["stage"]
        if angle < down_below:
            stage, self._armed = "Down", True
            if form == "GOOD":
                feedback = label_down
        elif angle > 155:
            if self._armed:
                self._count()
                self._armed = False
            stage = "Up"
            if form == "GOOD":
                feedback = label_up
        return feedback, form, angle, stage

    def _analyse_squat(self, lms):
        return self._leg_exercise(
            lms, 115,
            "Good depth; keep your heels planted and knees tracking with toes.",
            "Stand tall; begin the next rep when ready.",
            "Lower and rise with control through a comfortable range.",
        )

    def _analyse_lunge(self, lms):
        return self._leg_exercise(
            lms, 105,
            "Keep your front knee aligned over your foot and torso steady.",
            "Return to standing with control.",
            "Lower vertically; maintain balance.",
        )

    def _arm_angle_or_wait(self, lms):
        angle = _joint_angle(lms, ARM_TRIPLES)
        if angle is None:
            return None, self._waiting(
                "Show at least one shoulder, elbow and wrist clearly; try a side view."
            )
        return angle, None

    def _analyse_pushup(self, lms):
        angle, wait = self._arm_angle_or_wait(lms)
        if wait:
            return wait
        form, feedback = "GOOD", "Lower your chest, then press back up through a controlled range."
        torso = _best_group(lms, TORSO_TRIPLES)
        if torso:
            shoulder, hip, ankle = torso
            dx, dy = ankle[0] - shoulder[0], ankle[1] - shoulder[1]
            denom = max(math.hypot(dx, dy), 0.001)
            # Distance from the hip to the shoulder-ankle line (2D).
            off_line = abs(dy * hip[0] - dx * hip[1] + ankle[0] * shoulder[1] - ankle[1] * shoulder[0]) / denom
            if off_line > 0.10:
                form = "WRONG"
                feedback = "Form looks off: keep shoulders, hips and ankles in a straight line."
        stage = self._state["stage"]
        if angle < 105:
            stage, self._armed = "Down", True
            if form == "GOOD":
                feedback = "Bottom position; press up while keeping your body aligned."
        elif angle > 150:
            if self._armed:
                self._count()
                self._armed = False
            stage = "Up"
            if form == "GOOD":
                feedback = "Form looks good: arms extended and body aligned."
        return feedback, form, angle, stage

    def _analyse_pullup(self, lms):
        angle, wait = self._arm_angle_or_wait(lms)
        if wait:
            return wait
        form, feedback = "GOOD", "Pull upward and keep your body as still as possible."
        torso = _best_group(lms, TORSO_TRIPLES)
        if torso:
            shoulder, hip, ankle = torso
            if abs(hip[0] - (shoulder[0] + ankle[0]) / 2) > 0.16:
                form = "WRONG"
                feedback = "Form looks off: reduce swinging and keep your torso controlled."
        stage = self._state["stage"]
        if angle < 105:
            stage, self._armed = "Top", True
            if form == "GOOD":
                feedback = "Pull to the top without swinging."
        elif angle > 145:
            if self._armed:
                self._count()
                self._armed = False
            stage = "Hang"
            if form == "GOOD":
                feedback = "Form looks good: return to a controlled hang."
        return feedback, form, angle, stage

    def _analyse_bicep_curl(self, lms):
        angle, wait = self._arm_angle_or_wait(lms)
        if wait:
            return wait
        form, feedback = "GOOD", "Curl and extend through a controlled range without swinging."
        side = _best_group(lms, SIDE_PAIRS)
        if side and abs(side[0][0] - side[1][0]) > 0.18:
            form = "WRONG"
            feedback = "Form looks off: keep your torso still and elbows close to your sides."
        stage = self._state["stage"]
        if angle < 65:
            stage, self._armed = "Curl", True
            if form == "GOOD":
                feedback = "Top of curl; keep elbows close to your torso."
        elif angle > 145:
            if self._armed:
                self._count()
                self._armed = False
            stage = "Extend"
            if form == "GOOD":
                feedback = "Form looks good: lower slowly until your arm is nearly straight."
        return feedback, form, angle, stage

    def _analyse_shoulder_press(self, lms):
        angle, wait = self._arm_angle_or_wait(lms)
        if wait:
            return wait
        form, feedback = "GOOD", "Press vertically without arching your lower back excessively."
        side = _best_group(lms, SIDE_PAIRS)
        if side and abs(side[0][0] - side[1][0]) > 0.15:
            form = "WRONG"
            feedback = "Form looks off: brace your core and avoid leaning or arching your back."
        stage = "Moving"
        if angle > 150:
            # A rep only counts after the bottom (shoulder-level) position was
            # reached, so starting with arms already extended doesn't count.
            if self._armed:
                self._count()
                self._armed = False
            stage = "Top"
            if form == "GOOD":
                feedback = "Form looks good: arms extended overhead; lower under control."
        elif angle < 105:
            stage, self._armed = "Bottom", True
            if form == "GOOD":
                feedback = "Start from shoulder level and keep your core braced."
        return feedback, form, angle, stage

    def _analyse_jumping_jack(self, lms):
        ids = [L.LEFT_SHOULDER, L.RIGHT_SHOULDER, L.LEFT_WRIST, L.RIGHT_WRIST,
               L.LEFT_ANKLE, L.RIGHT_ANKLE]
        if _group_visibility(lms, ids) < 0.35:
            return self._waiting("Keep your arms and feet visible in the camera frame.")
        ls, rs = _point(lms, L.LEFT_SHOULDER), _point(lms, L.RIGHT_SHOULDER)
        lw, rw = _point(lms, L.LEFT_WRIST), _point(lms, L.RIGHT_WRIST)
        la, ra = _point(lms, L.LEFT_ANKLE), _point(lms, L.RIGHT_ANKLE)
        shoulder_width = max(abs(ls[0] - rs[0]), 0.01)
        arms_up = lw[1] < ls[1] and rw[1] < rs[1]
        feet_apart = abs(la[0] - ra[0]) > shoulder_width * 1.45
        if arms_up and feet_apart:
            self._armed = True
            return "Open position; land softly with knees relaxed.", "GOOD", 0, "Open"
        if self._armed:
            self._count()
            self._armed = False
        return "Bring feet together and arms down, then open smoothly.", "GOOD", 0, "Closed"


# Shared session used by the Flask routes (the app drives a single local webcam).
session = ExerciseSession()


# ----------------------------------------------------------------------
# Camera streaming (lazy OpenCV / MediaPipe)
# ----------------------------------------------------------------------
_stream_lock = threading.Lock()
_stream_generation = 0


def backend_status():
    """Return ``(available, reason)`` for the OpenCV + MediaPipe backend."""
    try:
        import cv2  # noqa: F401
    except Exception as exc:  # ImportError, or missing OpenGL libs on servers
        return False, f"OpenCV is not available ({exc.__class__.__name__}). Install requirements-camera.txt."
    try:
        import mediapipe as mp
    except Exception as exc:
        return False, f"MediaPipe is not available ({exc.__class__.__name__}). Install requirements-camera.txt."
    if not hasattr(mp, "solutions"):
        return False, ("This MediaPipe version has no 'solutions' API. "
                       "Install the pinned version: pip install mediapipe==0.10.21")
    return True, ""


def _open_camera(cv2):
    if os.name == "nt":
        candidates = [(0, cv2.CAP_DSHOW), (0, cv2.CAP_ANY), (1, cv2.CAP_DSHOW), (1, cv2.CAP_ANY)]
    else:
        candidates = [(0, cv2.CAP_ANY), (1, cv2.CAP_ANY)]
    for index, backend in candidates:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap
        cap.release()
    return None


def _jpeg_part(cv2, frame):
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return None
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"


def generate_frames():
    """Yield annotated MJPEG frames for the selected exercise.

    Only one stream is active at a time: starting a new one makes any previous
    generator stop and release the webcam. MediaPipe's Pose object is created
    per stream (it is not thread-safe) and closed when the stream ends.
    """
    global _stream_generation
    available, reason = backend_status()
    if not available:
        session.set_status(reason)
        return

    import cv2
    import mediapipe as mp

    with _stream_lock:
        _stream_generation += 1
        generation = _stream_generation

    camera = _open_camera(cv2)
    if camera is None:
        session.set_status("Camera unavailable. Check camera permissions, close other camera apps, then retry.")
        import numpy as np
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "WEBCAM NOT AVAILABLE", (35, 145), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(frame, "Check camera permissions / close other apps", (28, 195),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 220, 210), 1)
        part = _jpeg_part(cv2, frame)
        if part:
            yield part
        return

    mp_pose, mp_drawing = mp.solutions.pose, mp.solutions.drawing_utils
    try:
        with mp_pose.Pose(
            static_image_mode=False, model_complexity=1, smooth_landmarks=True,
            enable_segmentation=False, min_detection_confidence=0.55,
            min_tracking_confidence=0.55,
        ) as pose:
            while generation == _stream_generation:
                ok, frame = camera.read()
                if not ok:
                    session.set_status("Could not read the camera frame.")
                    break
                frame = cv2.flip(frame, 1)
                results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if results.pose_landmarks:
                    mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                    feedback, form, _angle, stage = session.analyse(results.pose_landmarks.landmark)
                    snap = session.snapshot()
                    color = (0, 190, 0) if form == "GOOD" else (0, 0, 255)
                    cv2.putText(frame, f"{EXERCISES[snap['exercise']]['label']}: {snap['reps']}",
                                (18, 34), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
                    cv2.putText(frame, f"Form: {form} | Stage: {stage}", (18, 66),
                                cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2)
                    cv2.putText(frame, feedback[:54], (18, frame.shape[0] - 22),
                                cv2.FONT_HERSHEY_SIMPLEX, .52, color, 2)
                else:
                    session.set_status("No person detected - move back until your body is visible.")
                    cv2.putText(frame, "No person detected", (18, 35),
                                cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
                part = _jpeg_part(cv2, frame)
                if part:
                    yield part
    finally:
        camera.release()
