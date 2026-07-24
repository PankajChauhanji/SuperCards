// Shared table-theme selector.
//
// Owns the heavy lifting: the theme catalogue, applying a theme to <body>, the
// dropdown wiring, and the host-only visibility toggle. Each game bundle keeps
// `view.tableTheme` as its source of truth and drives this module through
// SS.themes.apply(theme) / SS.themes.syncVisibility(isHost); the live
// `table_theme_updated` socket event is still handled by the variant (so its
// view stays in sync), which then calls apply().
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const code = window.SS_ROOM_CODE;
  const youId = window.Identity ? window.Identity.userId() : null;

  const THEME_MAP = {
    default: { icon: "🟢", name: "Default" },
    casino: { icon: "🎰", name: "Casino Felt" },
    cyberpunk: { icon: "👾", name: "Cyberpunk" },
    marble: { icon: "🏛️", name: "Marble Luxury" },
    red_casino: { icon: "🍒", name: "Red Casino" },
  };

  function apply(theme) {
    theme = theme || "default";
    Object.keys(THEME_MAP).forEach((t) => document.body.classList.remove("theme-" + t));
    if (theme !== "default") document.body.classList.add("theme-" + theme);
    const icon = document.getElementById("current-theme-icon");
    const name = document.getElementById("current-theme-name");
    if (icon && name) {
      const active = THEME_MAP[theme] || THEME_MAP.default;
      icon.textContent = active.icon;
      name.textContent = active.name;
    }
  }

  function syncVisibility(isHost) {
    const wrap = document.getElementById("theme-select-wrap");
    if (wrap) wrap.style.display = isHost ? "inline-flex" : "none";
  }

  const btn = document.getElementById("theme-select-btn");
  const dropdown = document.getElementById("theme-dropdown");
  if (btn && dropdown) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (dropdown.hasAttribute("hidden")) {
        dropdown.removeAttribute("hidden");
        dropdown.setAttribute("aria-hidden", "false");
      } else {
        dropdown.setAttribute("hidden", "");
        dropdown.setAttribute("aria-hidden", "true");
      }
    });
    dropdown.querySelectorAll(".theme-opt").forEach((opt) => {
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        if (socket) socket.emit("change_table_theme", { code, user_id: youId, theme: opt.dataset.t });
        dropdown.setAttribute("hidden", "");
        dropdown.setAttribute("aria-hidden", "true");
      });
    });
    document.addEventListener("click", () => {
      dropdown.setAttribute("hidden", "");
      dropdown.setAttribute("aria-hidden", "true");
    });
  }

  SS.themes = { apply, syncVisibility };
})();
