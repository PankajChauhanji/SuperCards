// Shared table-theme selector.
//
// Owns the theme catalogue, applying the player's own theme to <body>, and the
// picker in the Settings sheet. Game bundles still call SS.themes.apply(theme)
// and SS.themes.syncVisibility(isHost) from when the theme was host-picked;
// both now just apply this player's choice (see below).
(function () {
  const SS = window.SS || (window.SS = {});

  // Casino is the baseline look — every room starts here, no picking
  // required. The first 5 are palette variants sharing the Classic frame;
  // the rest are fully self-contained signature designs (own background,
  // border and ornaments baked in — no separate shape picker). Each one's
  // swatch colours live with its button in partials/theme_selector.html.
  const THEME_MAP = {
    casino: { name: "Casino Felt" },
    marble: { name: "Marble Luxury" },
    red_casino: { name: "Red Casino" },
    ocean_glow: { name: "Ocean Glow" },
    sunset_mirage: { name: "Sunset Mirage" },
    poker: { name: "Poker Table" },
    royal: { name: "Royal" },
    hacker: { name: "Hacker" },
    horror: { name: "Horror" },
    pirate: { name: "Pirate Treasure" },
    space: { name: "Space Galaxy" },
    egyptian: { name: "Egyptian Pharaoh" },
    wildwest: { name: "Wild West Saloon" },
    forest: { name: "Enchanted Forest" },
    imperial: { name: "Imperial Dragon" },
    maharaja: { name: "Maharaja Durbar" },
    deco: { name: "Gatsby Deco" },
  };

  // The table theme is a personal, per-device choice, like the card deck and
  // the hand view: each player sees the felt they picked, and nobody's choice
  // changes anyone else's screen. (It used to be host-picked and broadcast to
  // the table.) Game bundles still call apply() with the room's theme on every
  // state update; the room's value is ignored and the player's own is applied,
  // so no game had to change.
  const STORAGE_KEY = "super_cards_theme";
  const DEFAULT = "casino";

  function mine() {
    try {
      const t = localStorage.getItem(STORAGE_KEY);
      if (t && THEME_MAP[t]) return t;
    } catch (e) { /* storage unavailable: fall back to the default */ }
    return DEFAULT;
  }

  // The picker is a section of the Settings sheet (partials/theme_selector.html):
  // one swatch per theme, the current one marked.
  const opts = Array.from(document.querySelectorAll("#theme-dropdown .theme-opt[data-t]"));

  function apply() {
    const theme = mine();
    Object.keys(THEME_MAP).forEach((t) => document.body.classList.remove("theme-" + t));
    document.body.classList.add("theme-" + theme);
    opts.forEach((opt) => {
      const on = opt.dataset.t === theme;
      opt.classList.toggle("selected", on);
      opt.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  // Kept for the game bundles that still call it; every player can pick now.
  function syncVisibility() {}

  opts.forEach((opt) => {
    opt.addEventListener("click", () => {
      try { localStorage.setItem(STORAGE_KEY, opt.dataset.t); } catch (e) {}
      apply();
    });
  });

  apply();

  SS.themes = { apply, syncVisibility };
})();
