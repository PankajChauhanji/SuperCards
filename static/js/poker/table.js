// Poker table rendering — board, pot, seats, hole cards, scores panel — plus
// the table's motion: coins flying to the pot and back to the winner.
//
// Built on the shared pieces rather than beside them: seats come from
// core/seats.js (SS.renderOpponentSeats / SS.renderMySeat) and are then dressed
// for poker. The seat's liquid gauge (the same one Super Seven uses for
// elimination) here shows the player's stack against what they started with:
// full at the start, draining as coins leave, with the amount written in the
// circle. The card-count badge becomes a money pouch, and two small face-down
// cards sit beside anyone still in the hand. Card art goes through SS.cardSrc
// (core/deck.js), so the Royal / Standard deck choice applies here too.
(function () {
  const SS = window.SS || (window.SS = {});
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  function colorOf(p) { return PALETTE[(p && typeof p.color === "number" ? p.color : 0) % PALETTE.length]; }
  const reducedMotion = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- coin amounts: compact on the table, full on hover (docs/poker_ui.md) ----
  function trim(num, digits) {
    return num.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
  }
  // The unit is chosen from the ROUNDED value, so 999,999 reads "1M", never "1000K".
  const UNITS = [[1e3, "K", 1], [1e6, "M", 2], [1e9, "B", 2]];   // divisor, suffix, decimals under 100
  function chips(n) {
    n = Number(n) || 0;
    const sign = n < 0 ? "−" : "";
    const a = Math.abs(n);
    if (a < 1000) return sign + String(a);
    for (let i = 0; i < UNITS.length; i++) {
      const [div, suffix, decimals] = UNITS[i];
      const v = a / div;
      const text = trim(v, v < 100 ? decimals : 0);
      if (parseFloat(text) < 1000 || i === UNITS.length - 1) return sign + text + suffix;
    }
    return sign + String(a);
  }
  function full(n) { return (Number(n) || 0).toLocaleString("en-US"); }
  function signed(n) { return (n > 0 ? "+" : "") + chips(n); }
  SS.pokerChips = { chips, full, signed };

  const STREET_NAMES = { preflop: "Pre-flop", flop: "Flop", turn: "Turn", river: "River" };

  // ---- card images: preloaded, so a freshly dealt card is never a blank box ----
  const FACES = [];
  ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"].forEach((r) =>
    ["S", "H", "D", "C"].forEach((s) => FACES.push(r + s)));
  FACES.push("back");
  const preloaded = new Set();
  function preloadDeck() {
    FACES.forEach((face) => {
      const src = SS.cardSrc(face);
      if (preloaded.has(src)) return;
      preloaded.add(src);
      const img = new Image();
      img.decoding = "async";
      img.src = src;
    });
  }

  function cardImg(card, cls) {
    const img = document.createElement("img");
    img.className = "card " + (cls || "");
    img.src = SS.cardSrc(card ? card.face : "back");
    img.alt = card ? card.code + " " + card.suit : "card";
    img.draggable = false;
    if (card) img.dataset.id = card.id;
    return img;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ---- sound: a short chip clink, synthesized (no asset files, like core/sound.js) ----
  let audio = null;
  function clink(count) {
    if (SS.sound && SS.sound.muted && SS.sound.muted()) return;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      audio = audio || new AC();
      if (audio.state === "suspended") audio.resume();
      const n = Math.max(1, Math.min(5, count || 2));
      for (let i = 0; i < n; i++) {
        const t = audio.currentTime + i * 0.055 + Math.random() * 0.02;
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(2300 + Math.random() * 900, t);
        osc.frequency.exponentialRampToValueAtTime(1500, t + 0.07);
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.07, t + 0.004);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
        osc.connect(gain);
        gain.connect(audio.destination);
        osc.start(t);
        osc.stop(t + 0.1);
      }
    } catch (e) { /* sound is decoration; never let it break the table */ }
  }

  // ---- flying coins ----
  function centerOf(node) {
    if (!node) return null;
    const r = node.getBoundingClientRect();
    if (!r.width && !r.height) return null;
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  function seatNode(uid) {
    return document.querySelector('[data-uid="' + uid + '"] .opp-ring-outer');
  }
  function potNode() {
    return document.getElementById("pk-coins") || document.getElementById("pk-pot");
  }
  // How many coins a movement of `amount` is worth drawing: grows slowly, so a
  // huge all-in looks bigger than a call without burying the table.
  function coinsFor(amount, bb) {
    if (!amount || amount <= 0) return 0;
    return Math.max(3, Math.min(10, Math.round(Math.log2(amount / Math.max(1, bb || 1) + 1) * 2)));
  }
  function fly(from, to, n, delay) {
    if (!from || !to || !n || reducedMotion()) return 0;
    for (let i = 0; i < n; i++) {
      const coin = el("div", "pk-fly-coin");
      coin.style.left = from.x + "px";
      coin.style.top = from.y + "px";
      document.body.appendChild(coin);
      const dx = to.x - from.x + (Math.random() * 18 - 9);
      const dy = to.y - from.y + (Math.random() * 10 - 5);
      const lift = -Math.min(70, 24 + Math.abs(dx) * 0.15);
      const anim = coin.animate([
        { transform: "translate(-50%, -50%) scale(0.9)", opacity: 0.0 },
        { transform: "translate(calc(-50% + " + dx * 0.5 + "px), calc(-50% + " + (dy * 0.5 + lift) + "px)) scale(1.05)", opacity: 1, offset: 0.5 },
        { transform: "translate(calc(-50% + " + dx + "px), calc(-50% + " + dy + "px)) scale(0.85)", opacity: 0.9 },
      ], { duration: 620, delay: (delay || 0) + i * 55, easing: "cubic-bezier(.3,.7,.4,1)", fill: "both" });
      anim.onfinish = () => coin.remove();
      anim.oncancel = () => coin.remove();
    }
    return (delay || 0) + n * 55 + 620;
  }

  SS.pokerFx = {
    preload: preloadDeck,
    clink,
    // A player's coins travel from their seat into the pot.
    toPot(uid, amount, bb) {
      const n = coinsFor(amount, bb);
      if (!n) return;
      fly(centerOf(seatNode(uid)), centerOf(potNode()), n, 0);
      setTimeout(() => clink(Math.ceil(n / 2)), 420);
    },
    // The pot travels to a winner's seat.
    toSeat(uid, amount, bb, delay) {
      const n = Math.min(12, coinsFor(amount, bb) + 3);
      const done = fly(centerOf(potNode()), centerOf(seatNode(uid)), n, delay || 0);
      setTimeout(() => clink(4), (delay || 0) + 500);
      return done;
    },
  };

  function timerInfo(state, isTurn) {
    if (!isTurn || state.state !== "IN_TURN" || typeof state.secondsLeft !== "number") return null;
    const total = (state.settings && state.settings.turn_timer) || 30;
    const remaining = Math.max(0, state.secondsLeft);
    return { pct: Math.max(0, Math.min(1, remaining / total)), label: remaining + "s", seconds: remaining };
  }

  function byId(state) {
    const m = {};
    (state.players || []).forEach((p) => (m[p.user_id] = p));
    return m;
  }

  // Seats in table order, rotated so the arc reads clockwise from you.
  function seatOrder(state) {
    const raw = (state.seats && state.seats.length) ? state.seats
      : (state.players || []).filter((p) => !p.is_spectator).map((p) => p.user_id);
    const i = raw.indexOf(state.you);
    return i === -1 ? raw : raw.slice(i + 1).concat(raw.slice(0, i + 1));
  }

  // The gauge is "how much of your stake is left": 0 = full, 1 = empty.
  function drainOf(p) {
    if (p.eliminated) return 1;
    if (!p.received) return 0;
    return 1 - Math.max(0, Math.min(1, (p.chips || 0) / p.received));
  }

  function seatDescriptor(state, p) {
    const isTurn = p.user_id === state.currentTurn;
    const t = timerInfo(state, isTurn);
    return {
      name: SS.shortName(p.name),
      color: colorOf(p),
      cardCount: null,          // the badge slot becomes the money pouch below
      ringPct: state.state === "LOBBY" ? null : drainOf(p),
      timerPct: t ? t.pct : null,
      timerLabel: t ? t.label : null,
      timerSeconds: t ? t.seconds : null,
      active: isTurn,
      connected: p.connected,
      eliminated: p.eliminated,
    };
  }

  // A drawn money pouch (geometry, not a font glyph — see todos §15).
  const POUCH_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path class="pk-pouch-tie" d="M8.6 2.8h6.8l-1.9 3.4h-3z"/>' +
    '<path class="pk-pouch-body" d="M10.2 6.6h3.6c3.9 2.2 6.4 5.9 6.4 9.4 0 3.8-3.6 5.8-8.2 5.8S3.8 19.8 3.8 16c0-3.5 2.5-7.2 6.4-9.4z"/>' +
    '<path class="pk-pouch-cord" d="M9.4 6.6h5.2"/>' +
    '<circle class="pk-pouch-coin" cx="12" cy="15.2" r="3.1"/>' +
    "</svg>";

  // The poker-only line under a shared seat badge: dealer / blind marker, this
  // stage's bet, and the player's status.
  function chipLine(state, p) {
    const line = el("div", "pk-seat-info");
    const uid = p.user_id;
    const marker = uid === state.button ? "D" : uid === state.sbId ? "SB" : uid === state.bbId ? "BB" : null;
    if (marker && state.state !== "LOBBY") {
      const m = el("span", "pk-marker pk-m-" + marker.toLowerCase(), marker);
      m.title = marker === "D" ? "Dealer" : marker === "SB" ? "Small blind" : "Big blind";
      line.appendChild(m);
    }
    if (p.bet > 0 && state.state === "IN_TURN") {
      const bet = el("span", "pk-bet");
      bet.appendChild(el("span", "pk-bet-coin"));
      bet.appendChild(document.createTextNode(chips(p.bet)));
      bet.title = "Bet this stage: " + full(p.bet);
      line.appendChild(bet);
    }
    let tag = null;
    if (p.eliminated) tag = ["pk-tag out", "Out"];
    else if (p.all_in) tag = ["pk-tag allin", "All-in"];
    else if (p.folded && p.in_hand) tag = ["pk-tag folded", "Folded"];
    else if (p.sitting_out) tag = ["pk-tag away", "Sat out"];
    if (tag) line.appendChild(el("span", tag[0], tag[1]));
    return line;
  }

  function revealedCards(state, uid) {
    const shown = state.revealed && state.revealed[uid];
    if (!shown || !shown.length) return null;
    const wrap = el("div", "pk-reveal");
    const best = state.winBest || null;
    shown.forEach((c) => {
      const img = cardImg(c, "pk-reveal-card");
      if (best && best.has(c.id)) img.classList.add("pk-win");
      wrap.appendChild(img);
    });
    return wrap;
  }

  function decorate(seatEl, state, p, own) {
    if (!seatEl || !p) return;
    seatEl.dataset.uid = p.user_id;
    if (p.folded && p.in_hand) seatEl.classList.add("pk-folded");
    if (state.state !== "LOBBY" && p.net > 0 && !p.eliminated) seatEl.classList.add("pk-up");
    if (state.winners && state.winners.has(p.user_id)) seatEl.classList.add("pk-winner");

    // The stack, written in the circle over its own gauge.
    const ini = seatEl.querySelector(".av-ini");
    if (ini && state.state !== "LOBBY") {
      ini.textContent = p.eliminated ? "Out" : chips(p.chips || 0);
      ini.classList.add("pk-amt");
      ini.title = full(p.chips || 0) + " coins left";
    }

    // Money pouch in place of the card count: gold and full when up on the
    // game, flat when down, gone once the player is out of coins.
    const badge = seatEl.querySelector(".opp-count");
    if (badge) {
      if (p.eliminated || state.state === "LOBBY") {
        badge.remove();
      } else {
        badge.className = "opp-count pk-pouch" + (p.net > 0 ? " up" : p.net < 0 ? " down" : "");
        badge.innerHTML = POUCH_SVG;
        badge.title = p.net > 0 ? "Up " + full(p.net) + " this game"
          : p.net < 0 ? "Down " + full(-p.net) + " this game" : "Even this game";
      }
    }

    // Two small face-down cards beside anyone still holding a hand.
    const ring = seatEl.querySelector(".opp-ring-outer");
    const shown = state.revealed && state.revealed[p.user_id];
    if (!own && ring && p.in_hand && !p.folded && !(shown && shown.length) && state.state === "IN_TURN") {
      const held = el("span", "pk-holding");
      held.appendChild(cardImg(null, "pk-mini"));
      held.appendChild(cardImg(null, "pk-mini"));
      ring.appendChild(held);
    }

    seatEl.appendChild(chipLine(state, p));
    const reveal = own ? null : revealedCards(state, p.user_id);
    if (reveal) seatEl.appendChild(reveal);
  }

  function renderOpponents(state) {
    const wrap = document.getElementById("opponents");
    const players = byId(state);
    const order = seatOrder(state).filter((uid) => uid !== state.you && players[uid] && !players[uid].is_spectator);
    SS.renderOpponentSeats(wrap, order.map((uid) => seatDescriptor(state, players[uid])));
    const seatEls = wrap.querySelectorAll(".opp-seat");
    order.forEach((uid, i) => decorate(seatEls[i], state, players[uid], false));
  }

  function renderMySeat(state) {
    const wrap = document.getElementById("myseat");
    const me = byId(state)[state.you];
    if (!me || me.is_spectator) { SS.renderMySeat(wrap, null); return; }
    SS.renderMySeat(wrap, seatDescriptor(state, me));
    decorate(wrap.querySelector(".my-seat"), state, me, true);
  }

  function deckKey() { return SS.deck && SS.deck.get ? SS.deck.get() : ""; }

  function renderBoard(state) {
    const board = document.getElementById("pk-board");
    const cards = state.board || [];
    const best = state.winBest || null;
    const sig = cards.map((c) => c.id).join(",") + "|" + deckKey() + "|" + (best ? [...best].join(",") : "");
    if (board.dataset.sig === sig) return;
    const before = Number(board.dataset.count || 0);
    board.dataset.sig = sig;
    board.innerHTML = "";
    for (let i = 0; i < 5; i++) {
      if (cards[i]) {
        const img = cardImg(cards[i], "pk-board-card");
        if (i >= before && cards.length > before) {
          img.classList.add("pk-dealt");
          img.style.animationDelay = (i - before) * 120 + "ms";
        }
        if (best) img.classList.add(best.has(cards[i].id) ? "pk-win" : "pk-dim");
        board.appendChild(img);
      } else {
        board.appendChild(el("span", "pk-slot"));
      }
    }
    board.dataset.count = String(cards.length);
  }

  // ---- the pot: a pile of gold coins that grows with the money in it ----
  function coinTotal(total, bb) {
    if (!total) return 0;
    return Math.max(1, Math.min(30, Math.round(Math.log2(total / Math.max(1, bb) + 1) * 3)));
  }

  function renderPot(state) {
    const pot = document.getElementById("pk-pot");
    const total = state.potTotal || 0;
    const bb = (state.blinds && state.blinds.bb) || 1;
    // The pile stays on the table after the round ends until the payout
    // animation has carried it to the winner (game.js sets potSwept).
    const showing = state.state === "IN_TURN" || (state.state !== "LOBBY" && !state.potSwept);
    const n = showing ? coinTotal(total, bb) : 0;
    let coins = document.getElementById("pk-coins");
    if (!coins) {
      pot.innerHTML = "";
      coins = el("div", "pk-coins");
      coins.id = "pk-coins";
      coins.setAttribute("aria-hidden", "true");
      pot.appendChild(coins);
      pot.appendChild(el("div", "pk-pot-labels"));
    }
    // Up to five stacks, filled left to right; only coins that are new this
    // render drop in, so the pile visibly grows instead of being redrawn.
    const have = Number(coins.dataset.n || 0);
    if (n !== have) {
      coins.innerHTML = "";
      const stacks = Math.min(5, Math.max(1, Math.ceil(n / 6)));
      const cols = [];
      for (let s = 0; s < stacks; s++) {
        const col = el("div", "pk-stack-col");
        col.style.setProperty("--tilt", ((s - (stacks - 1) / 2) * 2) + "deg");
        cols.push(col);
        coins.appendChild(col);
      }
      for (let i = 0; i < n; i++) {
        const coin = el("span", "pk-coin");
        if (i >= have && have > 0) {
          coin.classList.add("pk-coin-new");
          coin.style.animationDelay = (i - have) * 40 + "ms";
        }
        cols[i % stacks].appendChild(coin);
      }
      coins.dataset.n = String(n);
    }

    const labels = pot.querySelector(".pk-pot-labels");
    labels.innerHTML = "";
    if (!total || !showing) return;
    const main = el("span", "pk-pot-main", "Pot " + chips(total));
    main.title = full(total) + " coins";
    labels.appendChild(main);
    const pots = state.pots || [];
    if (pots.length > 1) {
      pots.forEach((p, i) => {
        const side = el("span", "pk-pot-side", (i === 0 ? "Main " : "Side ") + chips(p.amount));
        side.title = full(p.amount) + " coins";
        labels.appendChild(side);
      });
    }
  }

  function renderInfo(state) {
    const info = document.getElementById("pk-info");
    const parts = [];
    if (state.phase === "runout") parts.push("All-in — running it out");
    else if (state.street) parts.push(STREET_NAMES[state.street] || state.street);
    if (state.blinds) parts.push("Blinds " + chips(state.blinds.sb) + " / " + chips(state.blinds.bb));
    if (state.roundNumber) parts.push("Round " + state.roundNumber + " of " + (state.roundsTotal || "?"));
    info.textContent = parts.join(" · ");
  }

  // Your two cards. Dealt face down the moment a round starts and turned up
  // when the server's private deal lands — with the face image decoded first,
  // so the flip never reveals an empty box.
  function renderHand(state) {
    const hand = document.getElementById("hand");
    const label = document.getElementById("pk-hand-name");
    const me = byId(state)[state.you];
    const cards = state.hand || [];
    const inHand = !!(me && me.in_hand && state.state !== "LOBBY");
    const folded = !!(me && me.folded && me.in_hand);
    const facedown = !cards.length && inHand && state.state === "IN_TURN";
    const best = state.winBest || null;
    const sig = (facedown ? "backs" : cards.map((c) => c.id).join(",")) + "|" + folded + "|" + deckKey() +
      "|" + (best ? [...best].join(",") : "");

    if (label) {
      const name = !folded && state.handName && cards.length ? state.handName : "";
      label.textContent = name ? "Your hand: " + name : "";
      label.hidden = !name;
    }
    if (hand.dataset.sig === sig) return;
    const wasBacks = hand.dataset.backs === "1";
    hand.dataset.sig = sig;
    hand.classList.toggle("pk-hand-folded", folded);

    if (facedown) {
      hand.innerHTML = "";
      hand.dataset.backs = "1";
      [0, 1].forEach((i) => {
        const back = cardImg(null, "hand-card pk-hole pk-deal");
        back.style.animationDelay = i * 140 + "ms";
        hand.appendChild(back);
      });
      return;
    }
    hand.dataset.backs = "0";
    const imgs = cards.map((c) => {
      const img = cardImg(c, "hand-card pk-hole" + (wasBacks ? " pk-flip" : ""));
      if (best && best.has(c.id)) img.classList.add("pk-win");
      return img;
    });
    const show = () => {
      if (hand.dataset.sig !== sig) return;     // a newer render won the race
      hand.innerHTML = "";
      imgs.forEach((img, i) => { img.style.animationDelay = i * 110 + "ms"; hand.appendChild(img); });
    };
    Promise.all(imgs.map((img) => (img.decode ? img.decode().catch(() => {}) : Promise.resolve())))
      .then(show);
  }

  function renderScoreboard(state) {
    const list = document.getElementById("score-list");
    list.innerHTML = "";
    const seated = (state.players || []).filter((p) => !p.is_spectator)
      .sort((a, b) => (a.eliminated - b.eliminated) || ((b.chips || 0) - (a.chips || 0)));
    seated.forEach((p) => {
      const li = document.createElement("li");
      if (p.user_id === state.currentTurn) li.classList.add("turn");
      if (p.eliminated) li.classList.add("out");
      const left = el("span", "sb-name");
      const sw = el("span", "swatch");
      sw.style.background = colorOf(p);
      left.appendChild(sw);
      left.appendChild(el("span", "dot" + (p.connected ? " on" : "")));
      if (p.user_id === state.hostId) left.appendChild(el("span", "host-crown", "♛"));
      left.appendChild(el("span", "sb-text", SS.shortName(p.name)));
      if (p.user_id === state.you) left.appendChild(el("span", "sb-you", "you"));
      li.appendChild(left);

      const right = el("span", "sb-score pk-sb");
      right.textContent = p.eliminated ? "Out" : chips(p.chips || 0);
      right.title = full(p.chips || 0) + " coins";
      if (!p.eliminated && p.net) {
        const net = el("span", "pk-net " + (p.net > 0 ? "up" : "down"), signed(p.net));
        net.title = (p.net > 0 ? "+" : "") + full(p.net) + " this game";
        right.appendChild(net);
      }
      li.appendChild(right);
      list.appendChild(li);
    });

    // Spectators, with the shared admit dialog for the host (core/chrome.js).
    const specList = document.getElementById("spectator-list");
    const specHeading = document.getElementById("spectators-heading");
    if (!specList || !specHeading) return;
    specList.innerHTML = "";
    const spectators = (state.players || []).filter((p) => p.is_spectator);
    specHeading.style.display = spectators.length ? "block" : "none";
    spectators.forEach((p) => {
      const li = el("li", "pk-spec");
      const left = el("span", "sb-name");
      left.appendChild(el("span", "dot" + (p.connected ? " on" : "")));
      left.appendChild(el("span", "sb-text", SS.shortName(p.name)));
      if (p.user_id === state.you) left.appendChild(el("span", "sb-you", "you"));
      li.appendChild(left);
      if (p.pending_join) {
        li.appendChild(el("span", "badge turn-now pk-spec-tag", "Joining next"));
      } else if (state.hostId === state.you && SS.openSpectatorModal) {
        const btn = el("button", "icon-btn", "+");
        btn.title = "Admit to the next round";
        btn.addEventListener("click", () => SS.openSpectatorModal(p.user_id, p.name));
        li.appendChild(btn);
      }
      specList.appendChild(li);
    });
  }

  window.Table = {
    render(state) {
      renderScoreboard(state);
      renderOpponents(state);
      renderBoard(state);
      renderPot(state);
      renderInfo(state);
      renderMySeat(state);
      renderHand(state);
      if (SS.positionReactionDock) SS.positionReactionDock();
    },
    // Per-second refresh for the turn ring only.
    tick(state) {
      renderOpponents(state);
      renderMySeat(state);
    },
  };

  preloadDeck();
})();
