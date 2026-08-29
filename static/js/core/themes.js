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

  // Casino is the baseline look — every room starts here, no picking
  // required. The first 5 are palette variants sharing the Classic frame;
  // the rest are fully self-contained signature designs (own background,
  // border and ornaments baked in — no separate shape picker).
  const THEME_MAP = {
    casino: { icon: "🎰", name: "Casino Felt" },
    marble: { icon: "🏛️", name: "Marble Luxury" },
    red_casino: { icon: "🍒", name: "Red Casino" },
    ocean_glow: { icon: "🌊", name: "Ocean Glow" },
    sunset_mirage: { icon: "🌅", name: "Sunset Mirage" },
    poker: { icon: "🃏", name: "Poker Table" },
    royal: { icon: "👑", name: "Royal" },
    hacker: { icon: "🖥️", name: "Hacker" },
    horror: { icon: "🩸", name: "Horror" },
    pirate: { icon: "☠️", name: "Pirate Treasure" },
    space: { icon: "🌌", name: "Space Galaxy" },
    egyptian: { icon: "🏺", name: "Egyptian Pharaoh" },
    wildwest: { icon: "🤠", name: "Wild West Saloon" },
    forest: { icon: "🌲", name: "Enchanted Forest" },
    imperial: { icon: "🐉", name: "Imperial Dragon" },
    maharaja: { icon: "🦚", name: "Maharaja Durbar" },
    deco: { icon: "🥂", name: "Gatsby Deco" },
  };

  function apply(theme) {
    theme = theme || "casino";
    Object.keys(THEME_MAP).forEach((t) => document.body.classList.remove("theme-" + t));
    document.body.classList.add("theme-" + theme);
    const icon = document.getElementById("current-theme-icon");
    const name = document.getElementById("current-theme-name");
    if (icon && name) {
      const active = THEME_MAP[theme] || THEME_MAP.casino;
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
