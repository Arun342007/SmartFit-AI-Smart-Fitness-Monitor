# AI-Powered Smart Fitness Tracking and Personalized Health Monitoring System

An academic **Software Configuration Management (SCM)** project that pairs a Flask +
AI/ML fitness and health-monitoring web app with a complete Git → GitHub → Jenkins →
Docker CI/CD pipeline.

> **Disclaimer:** This project is for educational purposes only. The health-risk
> predictions, alerts and exercise-form feedback are demo features (a small synthetic
> dataset and simple pose-angle rules). **This is NOT a medical diagnosis or a
> coaching/safety system.** Consult a qualified professional for real health concerns.

---

## 1. Abstract

The system simulates an intelligent fitness/health-monitoring application. It logs
activities, estimates a demo health-risk category with a scikit-learn model, produces
rule-based recommendations and threshold alerts, keeps a nutrition journal, and offers a
webcam **exercise coach** that counts reps and flags form issues using MediaPipe pose
landmarks. The **primary academic goal** is to demonstrate SCM and DevOps practices:
version control, branching, pull requests, CI pipelines and containerised deployment.

## 2. Features

- Home page, Dashboard, Activity logging, Health-risk prediction, Recommendations, Alerts
- **Nutrition & Diet journal**: log meals/macros, daily totals, 7-day calorie chart
- **Exercise studio** (webcam): squat, push-up, pull-up, lunge, jumping jack, bicep curl,
  shoulder press, with rep counting, live form cues and tutorial links
- Dashboard "Weekly calories burned" chart built from the activities you log
- SQLite persistence (users, health_records, activities, recommendations, alerts, nutrition_meals)
- RandomForest demo model on a synthetic dataset (balanced classes, cross-validated accuracy)
- Automated test suite (unit + route tests; no camera needed)
- Docker / docker-compose deployment and a Jenkins declarative pipeline

## 3. Technology Stack

| Layer      | Technology                                         |
|------------|----------------------------------------------------|
| Frontend   | HTML, CSS, JavaScript, Bootstrap 5, Chart.js       |
| Backend    | Python, Flask                                      |
| Database   | SQLite                                             |
| AI/ML      | scikit-learn, pandas, numpy; OpenCV + MediaPipe (webcam coach, optional) |
| SCM/DevOps | Git, GitHub, Jenkins, Docker                       |

## 4. Project Structure

```
smartfitness_multi_exercise_coach/
├── app.py                    # Flask app: routes, DB, validation, alerts/recommendations
├── nutrition_feature.py      # Nutrition journal blueprint (page + REST API)
├── camera/
│   └── coach.py              # Pose coach: rep/form logic (pure Python) + lazy camera streaming
├── models/health_model.py    # Demo scikit-learn risk model
├── data/sample_health_data.csv   # Synthetic training data (300 rows)
├── templates/                # Jinja2 pages (base, index, dashboard, activity, prediction,
│                             #   recommendations, alerts, nutrition)
├── static/
│   ├── css/style.css
│   ├── js/script.js              # site-wide helpers
│   ├── js/exercise_studio.js     # dashboard chart + exercise studio UI
│   └── img/camera-unavailable.png
├── tests/                    # test_app, test_nutrition, test_coach, test_model
├── requirements.txt          # core dependencies (web app, ML, tests) - used by Docker/Jenkins
├── requirements-camera.txt   # + OpenCV and MediaPipe for the live webcam coach
├── Dockerfile, docker-compose.yml, .dockerignore
├── Jenkinsfile
├── pytest.ini, .gitignore
└── instance/                 # created at run time: SQLite databases (git-ignored)
```

## 5. Quick Start (Windows / VS Code, with webcam coach)

Use **Python 3.10 - 3.12 (64-bit)**. Open the folder that contains `app.py` in VS Code:

```powershell
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-camera.txt
python app.py
```

Open `http://127.0.0.1:5000/dashboard` and keep the terminal open.
If PowerShell blocks activation, use Command Prompt and `venv\Scripts\activate.bat`.

**No webcam / just the web app?** Install `requirements.txt` instead of
`requirements-camera.txt`. Everything works except the live camera, which then shows a
"camera unavailable" placeholder with an explanation.

> Keep `mediapipe==0.10.21` and `opencv-contrib-python==4.11.0.86` as pinned. Newer
> MediaPipe releases removed the `mp.solutions` API this project uses; the app detects that
> and tells you instead of crashing.

### Configuration (optional environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SMARTFIT_INSTANCE_DIR` | `./instance` | Where the SQLite databases are stored |
| `SECRET_KEY` | dev value | Flask secret (set your own outside local demos) |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Dev-server bind address |
| `FLASK_DEBUG` | off | Set to `1` to enable debug mode (never on a shared network) |

## 6. Exercise coach notes

Select an exercise on the dashboard, press **Start detection**, and follow the status
panel. When a form rule triggers, the panel turns red, shows the cue and highlights the
tutorial link.

- Grant camera permission and close other apps that use the webcam.
- Use good lighting; keep the needed joints in frame (hips/knees/ankles for squats and
  lunges; shoulders/elbows/wrists for arm exercises; arms and feet for jumping jacks).
- Side-on view works best for push-ups and pull-ups. With a side view, the better-seen arm
  is used for the angle.
- The coach drives **one local webcam** and keeps its state in the server process, so run it
  as a single local process (`python app.py`), not behind several workers or users.
- Rules are heuristic angle thresholds and can miscount or miss unsafe form. They are not
  a substitute for a qualified coach or clinician.

## 7. Running with Docker

```powershell
docker build -t smart-fitness-health .
docker run -d -p 5000:5000 -e SECRET_KEY=change-me -v fitness-data:/app/instance --name smart-fitness-health-container smart-fitness-health
```

or `docker compose up --build`, then visit `http://localhost:5000`.

The image contains the web app, model and nutrition journal and runs as a non-root user
under gunicorn. Databases live in the `fitness-data` volume (`/app/instance`). The live
webcam coach is **not** available inside Docker (no webcam access, camera libraries not
installed); run it locally as in section 5.

## 8. Testing

```powershell
pytest
```

(or `python -m unittest discover -s tests -t .`). Tests use a throw-away database folder,
so they never touch your real data, and need no camera or MediaPipe. They cover pages,
input validation, activity logging, prediction + alerts, recommendations, the nutrition
API, the ML model, angle maths and rep counting/form cues with synthetic landmarks.

## 9. Architecture

**Application flow:**
```
User -> Web UI (HTML/CSS/JS + Bootstrap) -> Flask (app.py)
     -> SQLite (instance/*.db)  |  ML model (models/health_model.py)
     -> Recommendations / Alerts (rules)  |  Pose coach (camera/coach.py, local webcam)
     -> Dashboard
```

**SCM / CI-CD flow:**
```
Developer -> Git -> GitHub (PRs) -> Jenkins -> pytest -> Docker build -> container health check
```

## 10. Git, Branching and GitHub

```bash
git init
git add .
git commit -m "Initial project setup"
git branch develop
git remote add origin https://github.com/<your-username>/smart-fitness-health-monitor.git
git push -u origin main
```

Branching: `main` (stable, tagged releases such as `v1.0.0`) ← `develop` (integration) ←
`feature/*` (one per feature, merged by pull request).

```bash
git checkout develop
git checkout -b feature/dashboard
git add . && git commit -m "Add fitness dashboard"
git push -u origin feature/dashboard     # open a PR: feature/dashboard -> develop
git tag -a v1.0.0 -m "First stable release" && git push origin v1.0.0
```

If Git reports a merge conflict, resolve the `<<<<<<<` / `=======` / `>>>>>>>` markers,
then `git add <file>` and `git commit`. The `.gitignore` keeps `venv/`, caches and the
`instance/` databases out of the repository.

## 11. Jenkins CI/CD

1. Install Jenkins with the *Pipeline* and *Git* plugins (Docker available on the agent).
2. **New Item → Pipeline → Pipeline script from SCM**, Git, your repo URL, script path `Jenkinsfile`.
3. Click **Build with Parameters**. Tick `PUSH_TO_DOCKERHUB` only if you want to push; that
   needs a *Username with password* credential with ID `dockerhub-credentials` and the
   `DOCKERHUB_REPO` value in the Jenkinsfile updated. Without it the pipeline runs fine.

Stages: **Checkout → Install Dependencies** (core `requirements.txt`) **→ Run Tests**
(JUnit report) **→ Build Docker Image → Run/Validate Container** (health check inside the
container, no host port needed) **→ Push to Docker Hub** (optional).

## 12. Limitations

- Synthetic training data; the model is illustrative, not clinically validated.
- No authentication: everything is stored for a single demo user.
- Alert thresholds are fixed demo values.
- Exercise form rules are heuristics; the webcam coach is single-user and local-only.
- Bootstrap and Chart.js load from a CDN, so the pages need internet access for styling/charts.

## 13. Future Enhancements

Real wearable/IoT integration, user accounts, richer ML on ethically sourced data,
notifications, a browser-based (client-side) pose detector so the coach also works when
deployed, and automatic deployment (CD).

## 14. Disclaimer

This project is an **academic SCM/DevOps demonstration**. Predictions, alerts,
recommendations, nutrition information and form feedback are for **educational purposes
only** and do **not** constitute medical, dietetic or training advice.
