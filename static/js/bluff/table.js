(function () {
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  function colorOf(p) { return PALETTE[(p && typeof p.color === "number" ? p.color : 0) % PALETTE.length]; }
  function swatch(p) { const s = document.createElement("span"); s.className = "swatch"; s.style.background = colorOf(p); return s; }

  // Turn-timer info for whichever seat (opponent or you) is currently
  // active — feeds core/seats.js's ring, which shows this instead of the
  // (Bluff has no) score ring while running.
  function timerInfo(state, isTurn) {
    if (!isTurn || state.state !== "IN_TURN" || typeof state.secondsLeft !== "number") return null;
    const total = (state.settings && state.settings.turn_timer) || 40;
    const remaining = Math.max(0, state.secondsLeft);
    return {
      pct: Math.max(0, Math.min(1, remaining / total)),
      // "left" is redundant next to a depleting ring; seconds lets the
      // seat go semibold under 5s (core/seats.js).
      label: remaining + "s",
      seconds: remaining,
    };
  }
  
  function cardImg(card, className) {
    const img = document.createElement("img");
    img.className = "card " + (className || "");
    img.src = window.SS.cardSrc(card.face);
    img.alt = card.code + " " + card.suit;
    img.draggable = false;
    return img;
  }
  
  function backImg(className) {
    const img = document.createElement("img");
    img.className = "card " + (className || "");
    img.src = window.SS.cardSrc("back");
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

  const ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th"];

  function renderScoreboard(state) {
    const list = document.getElementById("score-list");
    list.innerHTML = "";
    const activePlayers = state.players.filter(p => !p.is_spectator);
    // Bluff's standing is its finishing order, then fewest cards left — the same
    // ranking the podium uses, so the panel and the final screen agree.
    const finished = state.finishOrder || [];
    const placeOf = (p) => finished.indexOf(p.user_id);
    const ordered = activePlayers.slice().sort((a, b) => {
      const pa = placeOf(a), pb = placeOf(b);
      if (pa !== -1 || pb !== -1) {
        if (pa === -1) return 1;
        if (pb === -1) return -1;
        return pa - pb;
      }
      return (a.eliminated - b.eliminated) || ((a.card_count || 0) - (b.card_count || 0));
    });

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
        crown.textContent = "\u265B";
        left.appendChild(crown);
      }

      const text = document.createElement("span");
      text.className = "sb-text";
      text.textContent = window.SS.shortName(p.name);
      left.appendChild(text);
      if (p.user_id === state.you) { const y = document.createElement("span"); y.className = "sb-you"; y.textContent = "you"; left.appendChild(y); }

      li.appendChild(left);
      // Right-hand column: the place if they are out, otherwise how close they
      // are to being out. Without this the panel showed names and nothing else,
      // which said nothing about who was winning.
      const place = placeOf(p);
      const right = document.createElement("span");
      right.className = "sb-score" + (place !== -1 ? " sb-place" : " sb-cards");
      // Written out rather than drawn with a card glyph: the deck rewrite (§15)
      // found that Unicode playing-card characters resolve to whatever font the
      // viewer happens to have, or to a colour emoji, or to a tofu box.
      right.textContent = place !== -1
        ? (ORDINALS[place] || (place + 1) + "th")
        : (p.card_count || 0) + (p.card_count === 1 ? " card" : " cards");
      li.appendChild(right);
      list.appendChild(li);
    });
  }

  function renderOpponents(state) {
    const wrap = document.getElementById("opponents");
    const raw = state.turnOrder && state.turnOrder.length ? state.turnOrder : state.players.map((p) => p.user_id);

    // Rotate so the sequence starts right after "you", wrapping around — the
    // arc then reads left-to-right as the actual turn order from whoever is
    // viewing it, like sitting at a table and turns passing clockwise.
    const youIdx = raw.indexOf(state.you);
    const order = youIdx === -1
      ? raw
      : raw.slice(youIdx + 1).concat(raw.slice(0, youIdx + 1));

    const byId = {};
    state.players.forEach((p) => (byId[p.user_id] = p));

    // Bluff has no numeric elimination cap (players are only removed by
    // finishing their hand), so seats render with ringPct null -> a plain
    // bordered avatar (core/seats.js), no progress ring.
    const seats = order.filter((uid) => uid !== state.you && byId[uid]).map((uid) => {
      const p = byId[uid];
      const isTurn = p.user_id === state.currentTurn;
      const timer = timerInfo(state, isTurn);
      return {
        name: window.SS.shortName(p.name),
        color: colorOf(p),
        cardCount: p.card_count || 0,
        ringPct: null,
        timerPct: timer ? timer.pct : null,
        timerLabel: timer ? timer.label : null,
          timerSeconds: timer ? timer.seconds : null,
        active: isTurn,
        connected: p.connected,
        eliminated: p.eliminated,
      };
    });

    window.SS.renderOpponentSeats(wrap, seats);
  }

  function renderCenter(state) {
    const discard = document.getElementById("center-pile");
    const empty = document.getElementById("center-empty");
    const countSpan = document.getElementById("center-count");
    const badgeCount = document.getElementById("center-badge-count");
    
    const count = state.centerCount || 0;
    countSpan.textContent = count;

    empty.style.display = count ? "none" : "block";
    if (badgeCount) {
      badgeCount.style.display = count ? "block" : "none";
      badgeCount.textContent = count;
    }
    // table_state fires on plenty of changes that don't touch the center
    // pile — rebuilding these <img> elements every time anyway causes a
    // visible flicker (tear down + recreate the same card backs), which
    // reads as "thrown twice". Skip the rebuild when the count hasn't
    // actually changed (Bluff only ever shows backs/count, never faces, so
    // the count alone is a complete signature).
    const sig = String(count);
    if (discard.dataset.sig !== sig) {
      discard.dataset.sig = sig;
      discard.querySelectorAll(".card").forEach((el) => el.remove());
      for(let i = 0; i < Math.min(count, 10); i++) {
        const img = backImg("center-card");
        img.style.marginLeft = i === 0 ? "0" : "-34px";
        discard.appendChild(img);
      }
    }
    
    const trDisp = document.getElementById("target-rank-display");
    const trVal = document.getElementById("target-rank-value");
    const lpDisp = document.getElementById("last-play-display");
    
    if (state.targetRank) {
      trDisp.style.display = "block";
      trVal.textContent = state.targetRank;
      
      if (state.lastPlay) {
        const p = state.players.find(x => x.user_id === state.lastPlay.user_id);
        const name = p ? p.name : "Someone";
        lpDisp.textContent = `${name} claimed ${state.lastPlay.count} card(s)`;
      } else {
        lpDisp.textContent = "";
      }
    } else {
      trDisp.style.display = "none";
    }
  }

  function renderMySeat(state) {
    const wrap = document.getElementById("myseat");
    const me = state.players.find((p) => p.user_id === state.you);
    if (!me) { window.SS.renderMySeat(wrap, null); return; }

    const isTurn = state.you === state.currentTurn;
    const timer = timerInfo(state, isTurn);

    window.SS.renderMySeat(wrap, {
      name: window.SS.shortName(me.name),
      color: colorOf(me),
      cardCount: me.card_count || 0,
      ringPct: null,
      timerPct: timer ? timer.pct : null,
      timerLabel: timer ? timer.label : null,
          timerSeconds: timer ? timer.seconds : null,
      active: isTurn,
      connected: me.connected,
      eliminated: me.eliminated,
    });
  }

  function renderHand(state) {
    const hand = document.getElementById("hand");

    // Sort hand in descending order of rank
    const sortedHand = (state.hand || []).slice().sort((a, b) => {
      if (a.rank !== b.rank) return b.rank - a.rank;
      const suitOrder = { S: 0, H: 1, D: 2, C: 3 };
      return (suitOrder[a.suit] || 0) - (suitOrder[b.suit] || 0);
    });
    const boxView = !window.SS.viewMode || window.SS.viewMode.get("bluff") === "box";
    // table_state fires on every opponent's move too, and this player's own
    // hand hasn't changed on most of those - rebuilding all the card <img>
    // elements anyway causes a visible flicker of your OWN hand, reading as
    // "my cards got thrown again". Skip the rebuild when nothing changed.
    const sig = sortedHand.map((c) => c.id).join(",") + "|" + (boxView ? "box" : "fan");
    if (hand.dataset.sig === sig) {
      if (window.Selection) window.Selection.refresh();
      return;
    }
    hand.dataset.sig = sig;

    hand.innerHTML = "";
    const slots = sortedHand.map((card) => {
      const slot = document.createElement("div");
      slot.className = "card-slot";
      slot.dataset.id = card.id;
      slot.appendChild(cardImg(card, "hand-card"));
      const tick = document.createElement("span");
      tick.className = "tick";
      tick.textContent = "\u2713";
      slot.appendChild(tick);
      hand.appendChild(slot);
      return slot;
    });
    // Fan/overlap math (core/seats.js) needs the slots already in the DOM
    // to measure real card width, so it runs after the loop above. Which
    // layout runs is a per-player preference (core/view_mode.js), not tied
    // to screen width \u2014 a Bluff hand can run to 50+ cards for one player in
    // a 2-player game, which squeezed into one fanned row becomes a 1px
    // sliver per card and untappable at ANY width, not just mobile. Box
    // view (flat wrapping grid in a scrollable box) is the default here.
    hand.classList.toggle("hand-flat-scroll", boxView);
    if (boxView) {
      window.SS.layoutHandGrid(hand, slots);
    } else {
      window.SS.layoutHandFan(hand, slots);
    }
    if (window.Selection) window.Selection.refresh();
  }

  window.Table = {
    render(state) {
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
    showRevealed(cards) {
      const discard = document.getElementById("center-pile");
      const empty = document.getElementById("center-empty");
      const badgeCount = document.getElementById("center-badge-count");
      
      discard.querySelectorAll(".card").forEach((el) => el.remove());
      if (empty) empty.style.display = "none";
      if (badgeCount) badgeCount.style.display = "none";
      
      (cards || []).forEach((card, i) => {
        const img = cardImg(card, "center-card");
        img.style.marginLeft = i === 0 ? "0" : "-34px";
        img.style.zIndex = i;
        discard.appendChild(img);
      });
    },
  };
})();
