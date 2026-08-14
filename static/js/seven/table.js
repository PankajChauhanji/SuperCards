// Table renderer. Pure view layer: given the current state it paints the
// scoreboard, opponent seats (counts only), the deck/center piles, and the
// player's own face-up hand. No game actions live here (those arrive Phase 2).
(function () {
  const CARD_PATH = "/static/img/cards/";

  // Stable per-player identity colours (indexed by player.color).
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  function colorOf(p) {
    return PALETTE[(p && typeof p.color === "number" ? p.color : 0) % PALETTE.length];
  }
  function swatch(p) {
    const s = document.createElement("span");
    s.className = "swatch";
    s.style.background = colorOf(p);
    return s;
  }

  // Turn-timer info for whichever seat (opponent or you) is currently
  // active — feeds core/seats.js's ring, which shows this instead of the
  // score ring while running. Only one seat is ever active at a time, so
  // this only returns non-null for that one.
  function timerInfo(state, isTurn) {
    if (!isTurn || state.state !== "IN_TURN" || typeof state.secondsLeft !== "number") return null;
    const total = (state.settings && state.settings.turn_timer) || 40;
    const remaining = Math.max(0, state.secondsLeft);
    return { pct: Math.max(0, Math.min(1, remaining / total)), label: remaining + "s left" };
  }

  function cardImg(card, className) {
    const img = document.createElement("img");
    img.className = "card " + (className || "");
    img.src = CARD_PATH + card.face + ".svg";
    img.alt = card.code + " " + card.suit;
    img.draggable = false;
    return img;
  }

  function backImg(className) {
    const img = document.createElement("img");
    img.className = "card " + (className || "");
    img.src = CARD_PATH + "back.svg";
    img.alt = "card";
    img.draggable = false;
    return img;
  }

  function badge(text, kind) {
    const b = document.createElement("span");
    b.className = "badge " + (kind || "");
    b.textContent = text;
    return b;
  }

  function renderScoreboard(state) {
    const list = document.getElementById("score-list");
    const specList = document.getElementById("spectator-list");
    const specHeading = document.getElementById("spectators-heading");
    
    list.innerHTML = "";
    if (specList) specList.innerHTML = "";

    // Order by standing: lowest cumulative score leads; eliminated sink.
    const activePlayers = state.players.filter(p => !p.is_spectator);
    const ordered = activePlayers.slice().sort(
      (a, b) => (a.eliminated - b.eliminated) || (a.score - b.score)
    );
    // Max score cap comes from room settings broadcast in table_state.
    const maxScore = (state.settings && state.settings.max_score) || 100;

    ordered.forEach((p) => {
      const li = document.createElement("li");
      if (p.user_id === state.currentTurn) li.classList.add("turn");
      if (p.eliminated) li.classList.add("out");

      const left = document.createElement("span");
      left.className = "sb-name";
      left.appendChild(swatch(p));
      const dot = document.createElement("span");
      dot.className = "dot" + (p.connected ? " on" : "");
      left.appendChild(dot);

      if (p.user_id === state.hostId) {
        const crown = document.createElement("span");
        crown.className = "host-crown";
        crown.textContent = "\u265B";   // chess-queen glyph reads as a crown
        crown.title = "Host";
        left.appendChild(crown);
      }

      // Calculate nextTurnId
      let nextTurnId = null;
      if (state.turnOrder && state.turnOrder.length > 0 && state.currentTurn) {
        const idx = state.turnOrder.indexOf(state.currentTurn);
        if (idx !== -1) {
          nextTurnId = state.turnOrder[(idx + 1) % state.turnOrder.length];
        }
      }

      if (p.user_id === state.currentTurn) {
        left.appendChild(badge("TURN", "turn-now"));
      } else if (p.user_id === nextTurnId) {
        left.appendChild(badge("NEXT", "next-turn"));
      }

      const text = document.createElement("span");
      text.className = "sb-text";
      text.textContent = window.SS.shortName(p.name);
      left.appendChild(text);
      if (p.user_id === state.you) { const y = document.createElement("span"); y.className = "sb-you"; y.textContent = "you"; left.appendChild(y); }

      const score = document.createElement("span");
      score.className = "sb-score";
      score.textContent = p.score;

      li.appendChild(left);
      li.appendChild(score);

      // Progress strip: green -> yellow -> orange -> red based on score / max.
      const pct = Math.min(1, (p.score || 0) / maxScore);
      const bar = document.createElement("div");
      bar.className = "sb-bar";
      const fill = document.createElement("div");
      fill.className = "sb-bar-fill";
      fill.style.setProperty("--bar-pct", (pct * 100).toFixed(1) + "%");
      fill.style.setProperty("--bar-raw", pct.toFixed(4));
      bar.appendChild(fill);
      li.appendChild(bar);

      list.appendChild(li);
    });

    const spectators = state.players.filter(p => p.is_spectator);
    if (specList && specHeading) {
      if (spectators.length > 0) {
        specHeading.style.display = "block";
        spectators.forEach(p => {
          const li = document.createElement("li");
          li.style.display = "flex";
          li.style.justifyContent = "space-between";
          li.style.alignItems = "center";
          li.style.background = "rgba(0,0,0,0.2)";
          li.style.padding = "0.4rem 0.6rem";
          li.style.borderRadius = "4px";

          const left = document.createElement("span");
          left.className = "sb-name";
          left.appendChild(swatch(p));
          const dot = document.createElement("span");
          dot.className = "dot" + (p.connected ? " on" : "");
          left.appendChild(dot);
          
          const text = document.createElement("span");
          text.className = "sb-text";
          text.textContent = window.SS.shortName(p.name);
          left.appendChild(text);
          if (p.user_id === state.you) { const y = document.createElement("span"); y.className = "sb-you"; y.textContent = "you"; left.appendChild(y); }
          li.appendChild(left);

          if (p.pending_join) {
            const tag = document.createElement("span");
            tag.className = "badge turn-now";
            tag.style.fontSize = "0.7em";
            tag.textContent = "Joining next";
            li.appendChild(tag);
          } else if (state.hostId === state.you) {
            const btn = document.createElement("button");
            btn.className = "icon-btn";
            btn.innerHTML = "+";
            btn.title = "Admit to next round";
            btn.style.width = "24px";
            btn.style.height = "24px";
            btn.style.fontSize = "18px";
            btn.style.lineHeight = "1";
            btn.style.padding = "0";
            btn.style.display = "flex";
            btn.style.alignItems = "center";
            btn.style.justifyContent = "center";
            btn.style.background = "rgba(255,255,255,0.15)";
            btn.style.border = "none";
            btn.style.borderRadius = "4px";
            btn.style.cursor = "pointer";
            btn.addEventListener("click", () => {
              if (window.SS && window.SS.openSpectatorModal) {
                window.SS.openSpectatorModal(p.user_id, p.name);
              }
            });
            li.appendChild(btn);
          }
          
          specList.appendChild(li);
        });
      } else {
        specHeading.style.display = "none";
      }
    }
  }

  function renderOpponents(state) {
    const wrap = document.getElementById("opponents");

    const raw = state.turnOrder && state.turnOrder.length
      ? state.turnOrder
      : state.players.map((p) => p.user_id);

    // Rotate so the sequence starts right after "you", wrapping around — the
    // arc then reads left-to-right as the actual turn order from whoever is
    // viewing it, like sitting at a table and turns passing clockwise. Every
    // player computes this from their own state.you, so it's correct for
    // each viewer independently.
    const youIdx = raw.indexOf(state.you);
    const order = youIdx === -1
      ? raw
      : raw.slice(youIdx + 1).concat(raw.slice(0, youIdx + 1));

    const byId = {};
    state.players.forEach((p) => (byId[p.user_id] = p));

    // Ring shows how close the player is to the elimination cap (matches the
    // Scores panel's own sb-bar-fill: score / max_score).
    const maxScore = (state.settings && state.settings.max_score) || 100;

    const seats = order
      .filter((uid) => uid !== state.you && byId[uid])
      .map((uid) => {
        const p = byId[uid];
        const isTurn = p.user_id === state.currentTurn;
        const timer = timerInfo(state, isTurn);
        return {
          name: window.SS.shortName(p.name),
          color: colorOf(p),
          cardCount: p.card_count,
          score: p.score,
          safe: p.is_safe,
          ringPct: p.is_safe ? 0 : Math.min(1, (p.score || 0) / maxScore),
          timerPct: timer ? timer.pct : null,
          timerLabel: timer ? timer.label : null,
          active: isTurn,
          connected: p.connected,
          eliminated: p.eliminated,
        };
      });

    window.SS.renderOpponentSeats(wrap, seats);
  }

  function renderCenter(state) {
    document.getElementById("deck-count").textContent = state.deckCount;

    const deck = document.getElementById("deck");
    const myDraw = state.you === state.currentTurn && state.awaitingDraw;
    deck.classList.toggle("clickable", !!myDraw);

    const discard = document.getElementById("discard");
    const empty = document.getElementById("discard-empty");
    // Clear previously rendered center cards (keep label + empty marker).
    discard.querySelectorAll(".card").forEach((el) => el.remove());

    const center = state.center || [];
    empty.style.display = center.length ? "none" : "block";
    center.forEach((card, i) => {
      const img = cardImg(card, "center-card");
      img.style.marginLeft = i === 0 ? "0" : "-34px";
      discard.appendChild(img);
    });
  }

  function renderMySeat(state) {
    const wrap = document.getElementById("myseat");
    const me = state.players.find((p) => p.user_id === state.you);
    if (!me) { window.SS.renderMySeat(wrap, null); return; }

    const isTurn = state.you === state.currentTurn;
    const timer = timerInfo(state, isTurn);
    const maxScore = (state.settings && state.settings.max_score) || 100;

    window.SS.renderMySeat(wrap, {
      name: window.SS.shortName(me.name) + " (you)",
      color: colorOf(me),
      cardCount: me.card_count,
      score: me.score,
      safe: me.is_safe,
      ringPct: me.is_safe ? 0 : Math.min(1, (me.score || 0) / maxScore),
      timerPct: timer ? timer.pct : null,
      timerLabel: timer ? timer.label : null,
      active: isTurn,
      connected: me.connected,
      eliminated: me.eliminated,
    });
  }

  // Stable display order for a hand: by rank, then by suit.
  const SUIT_ORDER = { S: 0, H: 1, D: 2, C: 3 };
  function sortedHand(cards) {
    return (cards || []).slice().sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return (SUIT_ORDER[a.suit] || 0) - (SUIT_ORDER[b.suit] || 0);
    });
  }

  function renderHand(state) {
    const hand = document.getElementById("hand");
    hand.innerHTML = "";
    const cards = sortedHand(state.hand);
    const slots = cards.map((card) => {
      const slot = document.createElement("div");
      slot.className = "card-slot";
      slot.dataset.id = card.id;
      if (card.id === state.justDrawnId) slot.classList.add("just-drawn");
      slot.appendChild(cardImg(card, "hand-card"));
      const tick = document.createElement("span");
      tick.className = "tick";
      tick.textContent = "\u2713";
      slot.appendChild(tick);
      hand.appendChild(slot);
      return slot;
    });
    // Fan/overlap math (core/seats.js) needs the slots already in the DOM
    // to measure real card width, so it runs after the loop above.
    window.SS.layoutHandFan(hand, slots);
    if (window.Selection) window.Selection.refresh();
  }

  window.Table = {
    render(state) {
      document.getElementById("round-chip").style.display = "inline-block";
      document.getElementById("round-chip").textContent = "Round " + (state.roundNumber || 1);
      renderScoreboard(state);
      renderOpponents(state);
      renderCenter(state);
      renderMySeat(state);
      renderHand(state);
    },
    // Lightweight per-second refresh for the turn-timer ring — only the
    // seat badges (a handful of small elements), not the whole hand/felt.
    tick(state) {
      renderOpponents(state);
      renderMySeat(state);
    },
  };
})();
