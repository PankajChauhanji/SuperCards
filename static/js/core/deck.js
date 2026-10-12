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
    // data-deck-fixed: the Settings sheet's previews, which show each deck as
    // itself and must not follow the player's choice.
    document.querySelectorAll('img[src*="/static/img/cards"]:not([data-deck-fixed])').forEach((img) => {
      const m = (img.getAttribute("src") || "")
        .match(/^(.*)\/static\/img\/cards(?:_v2)?\/(.+)$/);
      if (m && m[2]) img.setAttribute("src", m[1] + "/static/img/" + target + "/" + m[2]);
    });
  }

  // Fetch every face of the chosen deck once the page has settled, so a card
  // dealt or picked up for the first time is already in the browser's cache.
  // Without it a slow phone showed such a card as an empty box for a moment —
  // most visibly when a Bluff pile full of unseen cards landed in a hand.
  // Table pages only (they have a #hand); poker's own preload is the same idea.
  const warmed = new Set();
  function preload() {
    if (!document.getElementById("hand")) return;
    const faces = ["back"];
    ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"].forEach((r) =>
      ["S", "H", "D", "C"].forEach((s) => faces.push(r + s)));
    faces.forEach((face) => {
      const src = cardSrc(face);
      if (warmed.has(src)) return;
      warmed.add(src);
      const img = new Image();
      img.decoding = "async";
      img.src = src;
    });
  }

  SS.deck = { get, set, dir, repaint, preload };
  SS.cardSrc = cardSrc;

  // The server renders the deck back with the default path; correct it before
  // first paint if this player prefers the other deck.
  repaint();
  if (document.readyState === "complete") setTimeout(preload, 300);
  else window.addEventListener("load", () => setTimeout(preload, 300));

  // ---- the selector (a section of the Settings sheet) ----
  const opts = Array.from(document.querySelectorAll("#deck-dropdown .deck-opt[data-deck]"));
  if (!opts.length) return;

  function mark(name) {
    opts.forEach((opt) => {
      const on = opt.dataset.deck === name;
      opt.classList.toggle("selected", on);
      opt.setAttribute("aria-checked", on ? "true" : "false");
    });
  }
  mark(get());

  opts.forEach((opt) => {
    opt.addEventListener("click", () => {
      const name = opt.dataset.deck;
      if (name === get()) return;
      set(name);
      mark(name);
      repaint();
      preload();
      // Re-render as well: the hand fan's geometry is measured in JS, and on a
      // real phone a src swap alone left the layout untouched until a reload.
      if (window.SS.repaintUI) window.SS.repaintUI();
    });
  });
})();
