// Shared rules modal — per-game rule content with an EN/HI language toggle.
//
// Fully self-contained: opens/closes the modal and fetches the rule page for the
// current game from /static/rules/<GAME_TYPE>/<lang>.html, caching each language.
// No game coupling beyond window.GAME_TYPE.
(function () {
  const modal = document.getElementById("rules-modal");
  const container = document.getElementById("rules-content-container");
  const title = document.getElementById("rules-title");
  const openBtn = document.getElementById("rules-btn");
  const closeBtn = document.getElementById("rules-close");
  const langBtns = document.querySelectorAll(".lang-btn");
  if (!modal || !container) return;

  const gameType = window.GAME_TYPE || "super_seven";
  const cache = {};

  function loadRules(lang) {
    langBtns.forEach((b) => {
      const on = b.dataset.lang === lang;
      b.style.background = on ? "#6706ce" : "transparent";
      b.style.color = on ? "white" : "inherit";
    });
    if (title) title.innerText = lang === "hi" ? "📖 नियम पुस्तिका" : "📖 Rule Book";
    if (cache[lang]) { container.innerHTML = cache[lang]; return; }
    container.innerHTML = "<p>Loading rules…</p>";
    fetch(`/static/rules/${gameType}/${lang}.html`)
      .then((res) => { if (!res.ok) throw new Error("not ok"); return res.text(); })
      .then((html) => { cache[lang] = html; container.innerHTML = html; })
      .catch(() => { container.innerHTML = "<p>Rules coming soon.</p>"; });
  }

  if (openBtn) openBtn.addEventListener("click", () => { modal.classList.add("open"); loadRules("en"); });
  if (closeBtn) closeBtn.addEventListener("click", () => modal.classList.remove("open"));
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("open"); });
  langBtns.forEach((b) => b.addEventListener("click", (e) => loadRules(e.target.dataset.lang)));
})();
