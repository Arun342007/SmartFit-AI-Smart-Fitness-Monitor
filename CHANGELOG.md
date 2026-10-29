# Changelog - cleanup and bug-fix release

## Packaging
- Removed the 912 MB `venv/`, `__pycache__/`, compiled files and the runtime `.db` files
  from the project (the databases are re-created on first run in `instance/`).
- Added `.dockerignore`, `pytest.ini`; updated `.gitignore` (`instance/`, test output).
- Split dependencies: `requirements.txt` (core, used by Docker/Jenkins) and
  `requirements-camera.txt` (adds OpenCV + MediaPipe for the webcam coach).

## Crashes / reliability
- OpenCV and MediaPipe are now imported lazily, so the app, the tests, Docker and Jenkins
  no longer fail at import on machines without OpenGL libs or with a newer MediaPipe
  (>= 0.10.3x has no `mp.solutions`). The camera shows a clear message instead of crashing.
- `/activity` and `/recommendations` no longer return HTTP 500 on bad input; all form
  inputs are range-validated (also on `/predict`, which now shows an error message with HTTP 400).
- Activity logging uses Post/Redirect/Get (no duplicate entry on refresh) and shows flash messages.
- Camera state is lock-protected; starting a new stream stops the old one and releases the
  webcam; MediaPipe `Pose` is created per stream and closed afterwards.
- Nutrition API no longer leaks SQLite connections; meal type is validated; DB is initialised once.
- Debug mode is off by default and the dev server binds to 127.0.0.1 (set `FLASK_DEBUG=1` /
  `HOST` to change). Added `SECRET_KEY` support (needed for flash messages).
- Replaced deprecated `datetime.utcnow()`.

## Exercise coach
- Shoulder press no longer counts a free rep when you start with arms extended; all
  exercises now count a rep only after the "down/top" half was actually reached.
- Side-view handling: uses the better-visible arm and the better-visible torso side.
- Dashboard now shows the real coach feedback text (it was reading the wrong field) and
  highlights the tutorial panel when form is flagged.
- Jumping jack added to the dashboard selector (backend supported it, UI did not).
- Removed dead code: old camera UI in `script.js`, `camera/squat_detector.py`, duplicate globals.
- New endpoints `/exercise_data` and `/reset_exercise` (old `/squat_data`, `/reset_squats` still work).

## Data / ML
- Dashboard "Weekly progress" used hard-coded demo numbers; it now charts calories from
  logged activities. "Calories burned" shows today's logged total.
- Predictions now also save a health record, so the dashboard's heart rate / SpO2 / sleep /
  BMI reflect the latest reading (steps/calories carried over).
- Recommendations are no longer saved twice per day.
- Model: stratified split, `class_weight="balanced"`, 5-fold CV accuracy reported.

## UI
- Fixed broken CSS (`minmax(0,1fr)}` missing `)`) in the nutrition page; nutrition page moved
  to `templates/nutrition.html`; Chart.js pinned to 4.4.3; fixed an unclosed `<p>` on the dashboard.

## DevOps
- Dockerfile: no unnecessary compiler, non-root user, databases in a dedicated volume
  (`/app/instance`) so the training CSV is never hidden by the volume, 2 workers x 2 threads.
- docker-compose: removed obsolete `version:` key, `SECRET_KEY` env.
- Jenkinsfile: credentials only read in the optional push stage (pipeline no longer fails
  without them), real `PUSH_TO_DOCKERHUB` build parameter, container check without a host
  port and with a retry loop, timeout and build retention, pushes build-number tag too.

## Tests
- 14 -> 57 tests (routes, validation, nutrition API, ML model, angle maths, rep counting
  and form cues). Tests use a temporary database folder.
