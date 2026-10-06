// Hand-rankings card — a reference for the player, opened from the 🃏 button.
//
// The card is static and the same for every player, and this file never talks
// to the server. Its one dynamic touch is the host's "Hand hints" setting: when
// it is on, game.js calls SS.pokerRanks.mark() with the hand the server privately
// told this player they hold, and that row lights up (with the hand also shown in
// the card's header, and a gold dot on the button while the card is closed). With
// hints off the server sends no hand name at all, so there is nothing to light.
//
// Layout, chosen after the first play-test: the card used to sit inside the Coins
// card, where a scroll box inside a scroll box made it hard to scroll and the
// shared phone sheet squeezed it to ~120px. Now it is its own panel with exactly
// one scroll area — docked to the right edge of the felt on desktop (sized so all
// ten hands fit without scrolling), a bottom sheet on a phone. It stays open until
// the player closes it; nothing closes it on their behalf, not even their turn —
// with one exception on a phone, where it steps aside for the round summary.
(function () {
  const SS = window.SS || (window.SS = {});
  const $ = (id) => document.getElementById(id);
  const btn = $("pk-hands-btn");
  const panel = $("pk-hands");
  const list = $("pk-ranks-list");
  if (!btn || !panel || !list) return;
  const backdrop = $("pk-hands-backdrop");
  const closeBtn = $("pk-hands-close");
  const note = $("pk-ranks-note");
  const chip = $("pk-ranks-mine");
  const dot = $("pk-hands-dot");
  const PHONE = window.matchMedia ? window.matchMedia("(max-width: 720px)") : { matches: false };

  // [name, what it is, example faces, how many leading cards make the hand]
  const HANDS = [
    ["Royal Flush", "A K Q J 10, all one suit", ["AS", "KS", "QS", "JS", "10S"], 5],
    ["Straight Flush", "Five in a row, one suit", ["9H", "8H", "7H", "6H", "5H"], 5],
    ["Four of a Kind", "Four cards of one rank", ["QC", "QD", "QH", "QS", "4D"], 4],
    ["Full House", "Three of a rank + a pair", ["8S", "8D", "8H", "KC", "KS"], 5],
    ["Flush", "Any five of one suit", ["AD", "JD", "9D", "6D", "2D"], 5],
    ["Straight", "Five in a row, mixed suits", ["10C", "9D", "8S", "7H", "6C"], 5],
    ["Three of a Kind", "Three cards of one rank", ["7C", "7D", "7S", "KH", "2D"], 3],
    ["Two Pair", "Two different pairs", ["JH", "JC", "4S", "4D", "AC"], 4],
    ["One Pair", "Two cards of one rank", ["10S", "10H", "KD", "6C", "3S"], 2],
    ["High Card", "Nothing else: highest card plays", ["AC", "QD", "8S", "5H", "3C"], 1],
  ];

  // What the player may currently be shown — set by game.js via mark().
  let hintState = { hints: false, row: null, name: null };
  let built = false;

  function build() {
    if (built) return;
    built = true;
    HANDS.forEach(([name, hint, faces, makes], i) => {
      const li = document.createElement("li");
      li.className = "pk-rank";
      const num = document.createElement("span");
      num.className = "pk-rank-n";
      num.textContent = String(i + 1);
      // Two lines: number, name and hint across the top; the five cards, large,
      // across the full width underneath — where the card art can actually be read.
      const top = document.createElement("div");
      top.className = "pk-rank-top";
      const title = document.createElement("span");
      title.className = "pk-rank-name";
      title.textContent = name;
      const you = document.createElement("span");
      you.className = "pk-rank-you";
      you.textContent = "you";
      you.hidden = true;
      const sub = document.createElement("span");
      sub.className = "pk-rank-hint";
      sub.textContent = hint;
      sub.title = hint;
      top.append(num, title, you, sub);
      const cards = document.createElement("div");
      cards.className = "pk-rank-cards";
      faces.forEach((face, j) => {
        const img = document.createElement("img");
        img.className = "card pk-rank-card" + (j < makes ? "" : " kicker");
        img.src = SS.cardSrc ? SS.cardSrc(face) : "";
        img.alt = face;
        img.draggable = false;
        cards.appendChild(img);
      });
      li.append(top, cards);
      list.appendChild(li);
    });
    applyMark();
  }

  function applyMark() {
    const { hints, row, name } = hintState;
    const holding = hints && name != null;
    chip.hidden = !holding;
    chip.textContent = name || "";
    // A dot on the closed button says "the card has something for you".
    dot.hidden = !(holding && panel.hidden);
    btn.title = holding ? "Hand rankings — you have " + name : "Hand rankings";
    note.textContent = !hints
      ? "Reference card. The host can switch on hand hints in the lobby settings."
      : holding
        ? "Hand hints are on — your hand is highlighted."
        : "Hand hints are on — your hand lights up here while you hold one.";
    if (!built) return;
    list.querySelectorAll(".pk-rank").forEach((li, i) => {
      const mine = hints && row === i;
      li.classList.toggle("mine", mine);
      li.querySelector(".pk-rank-you").hidden = !mine;
    });
  }

  // Bring your own row into view inside the panel (its only scroll area).
  function showMine() {
    const mine = list.querySelector(".pk-rank.mine");
    if (!mine || panel.scrollHeight <= panel.clientHeight) return;
    const delta = mine.getBoundingClientRect().top - panel.getBoundingClientRect().top;
    panel.scrollTop += delta - panel.clientHeight / 3;
  }

  function syncBackdrop() {
    backdrop.hidden = panel.hidden || !PHONE.matches;
  }

  function open() {
    build();
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    btn.classList.add("on");
    syncBackdrop();
    applyMark();
    panel.scrollTop = 0;
    // After layout; instant rather than smooth, which a busy tab can drop.
    setTimeout(showMine, 0);
  }

  function close() {
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    btn.classList.remove("on");
    syncBackdrop();
    applyMark();
  }

  btn.addEventListener("click", () => (panel.hidden ? open() : close()));
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !panel.hidden) close();
  });
  if (PHONE.addEventListener) PHONE.addEventListener("change", syncBackdrop);

  SS.pokerRanks = {
    // hints: the host's setting; row/name: your hand, or null when you hold none.
    mark(hints, row, name) {
      hintState = { hints: !!hints, row: typeof row === "number" ? row : null, name: name || null };
      applyMark();
    },
    // The round summary / podium is about to open. On a phone the card is a
    // full-width sheet above the page, so it would bury that screen and the
    // host's Start-next-round button; the hand is over anyway, so step aside.
    // On desktop the card sits inside the felt, below any modal: leave it be.
    yieldToOverlay() {
      if (!panel.hidden && PHONE.matches) close();
    },
  };
  applyMark();
})();
