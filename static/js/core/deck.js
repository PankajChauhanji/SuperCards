// Shared "Royal / Standard" card-deck preference.
//
// Like the hand-view control and unlike the table theme, this is a personal,
// per-device choice: not host-controlled and not synced over the socket, so two
// players at the same table can each see the deck they prefer. Nothing about a
// card's identity changes — only which set of SVGs is loaded — so a deck swap can
// never affect gameplay or desync anything.
//
//   Royal    -> static/img/cards_v2/  (four-colour suits, figurative courts)
//   Standard -> static/img/cards/     (traditional two-colour, clean courts)
//
// Royal is the default because it is the more distinctive deck; Standard is there
// for players who want the plain two-colour look, and for anyone who finds the
// four-colour scheme unfamiliar.
//
// Every card path in the app goes through SS.cardSrc() so this stays the single
// place that knows where card art lives. `repaint()` additionally rewrites cards
// already in the DOM — including the two deck backs rendered server-side into the
// table templates — so switching is instant instead of waiting for the next
// server event to re-render the table.
//
// Reuses the theme selector's dropdown markup and CSS rather than inventing new
// chrome for what is structurally the same "pick one of a few options" control.
(function () {
  const SS = window.SS || (window.SS = {});
  const STORAGE_KEY = "super_cards_deck";
  const DIRS = { royal: "cards_v2", standard: "cards" };
  const DEFAULT = "royal";

  function get() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && DIRS[stored]) return stored;
    } catch (e) {
      /* localStorage unavailable (private mode etc.) — fall through to default */
    }
    return DEFAULT;
  }

  function set(name) {
    if (!DIRS[name]) return;
    try { localStorage.setItem(STORAGE_KEY, name); } catch (e) {}
  }

  function dir() {
    return DIRS[get()] || DIRS[DEFAULT];
  }

  // The one function that builds a card URL. `face` is Card.face from the
  // server ("7H", "10C", "AS"), or "back".
  function cardSrc(face) {
    return "/static/img/" + dir() + "/" + face + ".svg";
  }

  // Rewrite every card image already on the page. Matching on the directory
  // segment means this also catches the deck backs that the table templates
  // render server-side, and any future site, without those needing to know
  // about deck switching.
  function repaint() {
    const target = dir();
    document.querySelectorAll('img[src*="/static/img/cards"]').forEach((img) => {
      const m = (img.getAttribute("src") || "")
        .match(/^(.*)\/static\/img\/cards(?:_v2)?\/(.+)$/);
      if (m && m[2]) img.setAttribute("src", m[1] + "/static/img/" + target + "/" + m[2]);
    });
  }

  SS.deck = { get, set, dir, repaint };
  SS.cardSrc = cardSrc;

  // The server renders the deck back with the default path; correct it before
  // first paint if this player prefers the other deck.
  repaint();

  // ---- the selector ----
  const wrap = document.getElementById("deck-select-wrap");
  if (!wrap) return;
  wrap.style.display = "inline-flex";

  const LABELS = {
    royal: { icon: "👑", name: "Royal deck" },       // crown
    standard: { icon: "🃏", name: "Standard deck" },  // joker card
  };
  const iconEl = document.getElementById("current-deck-icon");
  const nameEl = document.getElementById("current-deck-name");

  function applyLabel(name) {
    const l = LABELS[name] || LABELS[DEFAULT];
    if (iconEl) iconEl.textContent = l.icon;
    if (nameEl) nameEl.textContent = l.name;
  }
  applyLabel(get());

  const btn = document.getElementById("deck-select-btn");
  const dropdown = document.getElementById("deck-dropdown");
  if (!btn || !dropdown) return;

  function close() {
    dropdown.setAttribute("hidden", "");
    dropdown.setAttribute("aria-hidden", "true");
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (dropdown.hasAttribute("hidden")) {
      dropdown.removeAttribute("hidden");
      dropdown.setAttribute("aria-hidden", "false");
    } else {
      close();
    }
  });

  dropdown.querySelectorAll(".theme-opt").forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.stopPropagation();
      const name = opt.dataset.deck;
      set(name);
      applyLabel(name);
      close();
      repaint();
    });
  });

  document.addEventListener("click", close);
})();
