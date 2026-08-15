// Shared "Standard view / Box view" hand-display preference.
//
// Unlike the table theme, this is a personal, per-device choice — not
// host-controlled, not synced over the socket. Standard is the fanned,
// held-like-real-cards layout; Box is a flat, non-overlapping, scrollable
// grid (core/seats.js layoutHandGrid) for hands too big to fan on any
// screen size (Bluff can run to 50+ cards for one player in a 2-player
// game). Super Seven defaults to Standard (always exactly 7 cards); Bluff
// defaults to Box. Super Four has only one hand layout and never shows
// this control at all.
//
// Reuses the theme-selector's dropdown markup/CSS (.theme-select-wrap,
// .theme-dropdown, .theme-opt) rather than inventing new chrome for what
// is structurally the same "pick one of a few options" control.
(function () {
  const SS = window.SS || (window.SS = {});
  const STORAGE_PREFIX = "super_cards_view_mode_";
  const DEFAULTS = { super_seven: "standard", bluff: "box" };

  function get(gameType) {
    try {
      const stored = localStorage.getItem(STORAGE_PREFIX + gameType);
      if (stored === "standard" || stored === "box") return stored;
    } catch (e) {
      /* localStorage unavailable (private mode etc.) — fall through to default */
    }
    return DEFAULTS[gameType] || "standard";
  }

  function set(gameType, mode) {
    try { localStorage.setItem(STORAGE_PREFIX + gameType, mode); } catch (e) {}
  }

  SS.viewMode = { get, set };

  const gameType = window.GAME_TYPE;
  const wrap = document.getElementById("view-mode-wrap");
  if (!wrap || gameType === "super_four") return;

  wrap.style.display = "inline-flex";

  const LABELS = {
    standard: { icon: "🃏", name: "Standard view" },
    box: { icon: "🗃️", name: "Box view" },
  };
  const iconEl = document.getElementById("current-view-icon");
  const nameEl = document.getElementById("current-view-name");
  function applyLabel(mode) {
    const l = LABELS[mode] || LABELS.standard;
    if (iconEl) iconEl.textContent = l.icon;
    if (nameEl) nameEl.textContent = l.name;
  }
  applyLabel(get(gameType));

  const btn = document.getElementById("view-mode-btn");
  const dropdown = document.getElementById("view-mode-dropdown");
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
        const mode = opt.dataset.mode;
        set(gameType, mode);
        applyLabel(mode);
        dropdown.setAttribute("hidden", "");
        dropdown.setAttribute("aria-hidden", "true");
        // Reflect immediately rather than waiting for the next server event.
        if (window.Table && window.SS.view && window.SS.view.state === "IN_TURN") {
          window.Table.render(window.SS.view);
        }
      });
    });
    document.addEventListener("click", () => {
      dropdown.setAttribute("hidden", "");
      dropdown.setAttribute("aria-hidden", "true");
    });
  }
})();
