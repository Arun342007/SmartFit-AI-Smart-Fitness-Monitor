# ---------------------------------------------------------------------
# Dockerfile - AI-Powered Smart Fitness Tracking & Health Monitoring System
#
# The image contains the web app, the demo ML model and the nutrition
# journal. The live webcam coach needs a physical webcam plus OpenCV /
# MediaPipe (requirements-camera.txt) and is meant to run locally; inside
# the container /video_feed shows a "camera unavailable" placeholder.
# ---------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SMARTFIT_INSTANCE_DIR=/app/instance

WORKDIR /app

# Install Python dependencies first (better Docker layer caching).
# All dependencies ship binary wheels, so no compiler is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application and drop root privileges.
COPY . .
RUN useradd --create-home appuser \
    && mkdir -p /app/instance \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health-check')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "app:app"]
