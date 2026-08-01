// Shared rules modal — per-game rule content with an EN/HI language toggle.
//
// Fully self-contained: opens/closes the modal and fetches the rule page for the
// current game from /static/rules/<GAME_TYPE>/<lang>.html, caching each language.
// No game coupling beyond window.GAME_TYPE.
(function () {
  const rulesModal = document.getElementById("rules-modal");
  const rulesContainer = document.getElementById("rules-content-container");
  const rulesTitle = document.getElementById("rules-title");
  const openRulesBtn = document.getElementById("rules-btn");
  const closeRulesBtn = document.getElementById("rules-close");
  const langBtns = document.querySelectorAll(".lang-btn");

  const installModal = document.getElementById("install-modal");
  const installContent = document.getElementById("install-content-container");
  const openInstallBtn = document.getElementById("install-help-link");
  const closeInstallBtn = document.getElementById("install-close");

  if (rulesModal && rulesContainer) {
    const gameType = window.GAME_TYPE || "super_seven";
    const cache = {};

    function loadRules(lang) {
      langBtns.forEach((b) => {
        const on = b.dataset.lang === lang;
        b.style.background = on ? "#6706ce" : "transparent";
        b.style.color = on ? "white" : "inherit";
      });
      if (rulesTitle) rulesTitle.innerText = lang === "hi" ? "📖 नियम पुस्तिका" : "📖 Rule Book";
      if (cache[lang]) { rulesContainer.innerHTML = cache[lang]; return; }
      rulesContainer.innerHTML = "<p>Loading rules…</p>";
      fetch(`/static/rules/${gameType}/${lang}.html`)
        .then((res) => { if (!res.ok) throw new Error("not ok"); return res.text(); })
        .then((html) => { cache[lang] = html; rulesContainer.innerHTML = html; })
        .catch(() => { rulesContainer.innerHTML = "<p>Rules coming soon.</p>"; });
    }

    if (openRulesBtn) openRulesBtn.addEventListener("click", () => { rulesModal.classList.add("open"); loadRules("en"); });
    if (closeRulesBtn) closeRulesBtn.addEventListener("click", () => rulesModal.classList.remove("open"));
    rulesModal.addEventListener("click", (e) => { if (e.target === rulesModal) rulesModal.classList.remove("open"); });
    langBtns.forEach((b) => b.addEventListener("click", (e) => loadRules(e.target.dataset.lang)));
  }

  if (installModal && installContent) {
    const closeInstall = () => installModal.classList.remove("open");
    const openInstall = () => {
      installModal.classList.add("open");
      if (!installContent.dataset.loaded) {
        installContent.innerHTML = "<p>Loading instructions…</p>";
        fetch("/static/rules/install.html")
          .then((res) => { if (!res.ok) throw new Error("not ok"); return res.text(); })
          .then((html) => {
            installContent.innerHTML = html;
            installContent.dataset.loaded = "true";
          })
          .catch(() => {
            installContent.innerHTML = "<p>Install instructions coming soon.</p>";
          });
      }
    };

    if (openInstallBtn) {
      openInstallBtn.addEventListener("click", (e) => {
        e.preventDefault();
        openInstall();
      });
    }

    if (closeInstallBtn) closeInstallBtn.addEventListener("click", closeInstall);
    installModal.addEventListener("click", (e) => { if (e.target === installModal) closeInstall(); });
  }
})();
