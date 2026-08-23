document.addEventListener("submit", function (event) {
  const form = event.target.closest("form[data-confirm]");
  if (!form) return;
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
});

document.addEventListener("click", async function (event) {
  const button = event.target.closest("[data-copy-target]");
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  const text = "value" in target ? target.value : target.textContent;
  try {
    await navigator.clipboard.writeText(text || "");
    const original = button.textContent;
    button.textContent = "Скопировано";
    window.setTimeout(() => { button.textContent = original; }, 1600);
  } catch (_error) {
    if (target.select) {
      target.select();
      document.execCommand("copy");
      window.getSelection()?.removeAllRanges();
    }
  }
});

(function watchReleaseJob() {
  const block = document.querySelector("[data-release-job-url]");
  if (!block) return;
  const url = block.dataset.releaseJobUrl;
  const poll = async () => {
    try {
      const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json();
      if (payload.status === "ready" || payload.status === "error") {
        window.location.reload();
        return;
      }
    } catch (_error) {
      // Временная ошибка сети не должна ломать страницу.
    }
    window.setTimeout(poll, 3000);
  };
  window.setTimeout(poll, 1800);
})();
