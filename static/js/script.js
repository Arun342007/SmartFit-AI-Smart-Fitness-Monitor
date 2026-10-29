// Smart Fitness Monitor - small site-wide client-side helpers.
// (The exercise-coach UI lives in exercise_studio.js and is loaded by the dashboard only.)
document.addEventListener("DOMContentLoaded", function () {
  // Auto-dismiss success alerts after a few seconds
  document.querySelectorAll(".alert-success").forEach(function (el) {
    setTimeout(function () {
      el.classList.add("fade");
      el.style.opacity = "0";
    }, 4000);
  });
});
