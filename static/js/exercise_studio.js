/* Smart Fitness Monitor - dashboard: weekly chart + exercise studio (pose coach UI).
   Talks to the Flask endpoints: /set_exercise, /exercise_data, /reset_exercise, /video_feed. */
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$("sfExercise")) return; // not on the dashboard

  /* ---------- today's date ---------- */
  $("sfToday").textContent = new Date().toLocaleDateString(undefined, {
    weekday: "short", day: "2-digit", month: "short", year: "numeric",
  });

  /* ---------- weekly calories chart (real data from logged activities) ---------- */
  const dataEl = $("sfWeeklyData");
  if (window.Chart && dataEl) {
    let weekly = { labels: [], values: [] };
    try { weekly = JSON.parse(dataEl.textContent); } catch (e) { console.error(e); }
    const canvas = $("sfWeeklyChart");
    const ctx = canvas.getContext("2d");
    const area = ctx.createLinearGradient(0, 0, 0, 260);
    area.addColorStop(0, "rgba(127,112,244,.30)");
    area.addColorStop(0.65, "rgba(127,112,244,.09)");
    area.addColorStop(1, "rgba(127,112,244,0)");
    new Chart(canvas, {
      type: "line",
      data: {
        labels: weekly.labels,
        datasets: [{
          label: "Calories burned", data: weekly.values, borderColor: "#7f70f4",
          backgroundColor: area, fill: true, tension: 0.42, cubicInterpolationMode: "monotone",
          borderWidth: 3, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: "#7f70f4",
          pointBorderColor: "#fff", pointBorderWidth: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#292544", titleColor: "#fff", bodyColor: "#eeeaff",
            padding: 12, displayColors: false,
            callbacks: { label: (c) => " " + Number(c.parsed.y).toLocaleString() + " kcal" },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#8985a0" } },
          y: {
            beginAtZero: true, grid: { color: "rgba(137,133,160,.13)" },
            ticks: { color: "#8985a0", callback: (v) => Number(v).toLocaleString() },
          },
        },
      },
    });
  }

  /* ---------- exercise studio ---------- */
  const info = {
    squat: ["Total squats", "squat", "Keep feet stable, knees tracking with toes, chest controlled."],
    pushup: ["Total push-ups", "push up", "Keep your body straight and lower with control."],
    pullup: ["Total pull-ups", "pull up", "Avoid swinging and control the descent."],
    lunge: ["Total lunges", "lunge", "Take a stable step and keep the front knee aligned."],
    jumping_jack: ["Total jumping jacks", "jumping jack", "Land softly and keep arms and feet visible."],
    bicep_curl: ["Total curls", "bicep curl", "Keep elbows close and avoid swinging."],
    shoulder_press: ["Total presses", "shoulder press", "Brace your core and avoid excessive back arch."],
  };
  let poll = null, clock = null, startedAt = 0;

  function setForm(kind, title, detail) {
    $("sfFormStatus").className = "sf-status " + kind;
    $("sfFormStatus").textContent = "● " + title;
    $("sfFormDetail").textContent = detail;
  }
  function setTutorialAlert(on) {
    const panel = document.querySelector(".sf-tutorial");
    if (panel) panel.classList.toggle("sf-tutorial-alert", on);
  }

  function choose() {
    const key = $("sfExercise").value;
    const v = info[key] || info.squat;
    fetch("/set_exercise", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exercise: key }),
    }).catch(() => {});
    $("sfTutorialSelect").value = key;
    $("sfRepLabel").textContent = v[0];
    $("sfReps").textContent = "0";
    $("sfAngle").textContent = "—";
    $("sfStage").textContent = "Ready";
    $("sfTutorialText").textContent = v[2];
    $("sfTutorialLink").href =
      "https://www.youtube.com/results?search_query=" + encodeURIComponent(v[1] + " proper form tutorial");
    $("sfTutorialLink").textContent = "Watch " + v[1] + " tutorial ↗";
    $("sfMessage").textContent = "Selected " + v[1] + ". Start detection when ready.";
    setTutorialAlert(false);
    setForm("", "WAITING FOR POSE", "Form feedback appears here once the pose detector sees you.");
  }

  async function pollData() {
    try {
      const r = await fetch("/exercise_data?_=" + Date.now(), { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      $("sfReps").textContent = Number(d.reps) || 0;
      $("sfAngle").textContent = d.angle ? Math.round(Number(d.angle)) + "°" : "—";
      $("sfStage").textContent = d.stage || "Ready";
      if (d.tutorial_url) $("sfTutorialLink").href = d.tutorial_url;
      const feedback = d.feedback || "";
      if (d.form === "WRONG") {
        setForm("bad", "FORM NEEDS ADJUSTMENT", feedback || "Adjust your posture and review the tutorial.");
        setTutorialAlert(true);
        $("sfMessage").textContent = "Form issue flagged - check the tutorial below.";
      } else if (d.form === "GOOD") {
        setForm("good", "FORM LOOKS GOOD", feedback || "The pose rules indicate acceptable form.");
        setTutorialAlert(false);
        $("sfMessage").textContent = "Pose status connected.";
      } else {
        setForm("", "WAITING FOR POSE", feedback || "Move into frame and keep joints visible.");
        setTutorialAlert(false);
        $("sfMessage").textContent = feedback || "Waiting for the pose detector.";
      }
    } catch (e) {
      $("sfMessage").textContent = "Cannot read /exercise_data (" + e.message + "). Check the Flask terminal.";
    }
  }

  $("sfStart").addEventListener("click", () => {
    const feed = $("sfCameraFeed"), placeholder = $("sfCameraPlaceholder");
    $("sfMessage").textContent = "Connecting to camera…";
    $("sfCameraBadge").className = "sf-status";
    $("sfCameraBadge").textContent = "● CONNECTING";
    feed.onload = () => {
      feed.style.display = "block";
      placeholder.style.display = "none";
      $("sfCameraBadge").className = "sf-status good";
      $("sfCameraBadge").textContent = "● CAMERA ACTIVE";
    };
    feed.onerror = () => {
      feed.style.display = "none";
      placeholder.style.display = "flex";
      placeholder.querySelector("strong").textContent = "Camera feed unavailable";
      $("sfCameraBadge").className = "sf-status bad";
      $("sfCameraBadge").textContent = "● CAMERA UNAVAILABLE";
      $("sfMessage").textContent = "Could not load /video_feed; check the camera backend.";
    };
    feed.src = "/video_feed?ts=" + Date.now();
    clearInterval(poll);
    poll = setInterval(pollData, 800);
    pollData();
    startedAt = Date.now();
    clearInterval(clock);
    clock = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt) / 1000);
      $("sfTimer").textContent =
        String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }, 1000);
  });

  $("sfStop").addEventListener("click", () => {
    clearInterval(poll);
    clearInterval(clock);
    const feed = $("sfCameraFeed");
    feed.onload = feed.onerror = null;
    feed.removeAttribute("src"); // closes the stream; the server then releases the webcam
    feed.style.display = "none";
    $("sfCameraPlaceholder").style.display = "flex";
    $("sfCameraPlaceholder").querySelector("strong").textContent = "Camera stopped";
    $("sfCameraBadge").className = "sf-status";
    $("sfCameraBadge").textContent = "● CAMERA STOPPED";
    $("sfMessage").textContent = "Camera stopped.";
  });

  $("sfReset").addEventListener("click", async () => {
    try { await fetch("/reset_exercise", { method: "POST" }); } catch (e) { /* ignore */ }
    $("sfReps").textContent = "0";
    $("sfStage").textContent = "Ready";
    $("sfMessage").textContent = "Counter reset.";
    setTutorialAlert(false);
    setForm("", "WAITING FOR POSE", "Counter reset. Start when ready.");
  });

  $("sfExercise").addEventListener("change", choose);
  $("sfTutorialSelect").addEventListener("change", () => {
    $("sfExercise").value = $("sfTutorialSelect").value;
    choose();
  });
  choose();
})();
