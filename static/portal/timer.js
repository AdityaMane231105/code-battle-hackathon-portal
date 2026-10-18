document.addEventListener("DOMContentLoaded", () => {
  const timer = document.querySelector("[data-countdown]");
  const display = document.querySelector("#countdown");
  const form = document.querySelector("#challenge-form");
  if (!timer || !display || !form) return;

  let remaining = Math.max(0, Number(timer.dataset.countdown) || 0);
  const render = () => {
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    display.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    if (remaining <= 60) timer.classList.add("urgent");
  };
  render();
  if (remaining === 0) {
    form.querySelectorAll("input, textarea, button").forEach((field) => { field.disabled = true; });
    return;
  }

  const interval = window.setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    render();
    if (remaining === 0) {
      window.clearInterval(interval);
      form.querySelectorAll("input, textarea").forEach((field) => { field.disabled = true; });
      const submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Time expired — reload to close attempt";
      }
      window.location.reload();
    }
  }, 1000);
});
