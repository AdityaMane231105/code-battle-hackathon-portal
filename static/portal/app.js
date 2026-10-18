document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector("#mobile-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      toggle.setAttribute("aria-label", expanded ? "Open navigation" : "Close navigation");
      nav.hidden = expanded;
    });
  }

  document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  document.querySelectorAll("[data-confirm-submit]").forEach((button) => {
    button.addEventListener("click", (event) => {
      if (!window.confirm("Submit your answers now? You cannot edit them afterwards.")) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("[data-confirm-publish]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Change whether final results are visible to participants?")) {
        event.preventDefault();
      }
    });
  });

  const challengeForm = document.querySelector("#challenge-form");
  const progress = document.querySelector("#challenge-progress");
  if (challengeForm && progress) {
    const updateProgress = () => {
      const fields = challengeForm.querySelectorAll("textarea, input[type=radio]");
      const questionIds = new Set(Array.from(fields, (field) => field.name));
      let answered = 0;
      questionIds.forEach((name) => {
        const group = challengeForm.querySelectorAll(`[name="${CSS.escape(name)}"]`);
        if (Array.from(group).some((field) => field.type === "radio" ? field.checked : field.value.trim().length > 0)) {
          answered += 1;
        }
      });
      progress.style.width = `${questionIds.size ? Math.round((answered / questionIds.size) * 100) : 0}%`;
      challengeForm.setAttribute("aria-label", `${answered} of ${questionIds.size} challenges answered`);
    };
    challengeForm.addEventListener("input", updateProgress);
    challengeForm.addEventListener("change", updateProgress);
    updateProgress();
  }
});
