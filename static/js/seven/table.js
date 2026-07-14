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
      text.textContent = p.name + (p.user_id === state.you ? " (you)" : "");
      left.appendChild(text);

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
          text.textContent = p.name + (p.user_id === state.you ? " (you)" : "");
          left.appendChild(text);
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
    wrap.innerHTML = "";

    // Find next turn
    let nextTurnId = null;
    if (state.turnOrder && state.turnOrder.length > 0 && state.currentTurn) {
      const idx = state.turnOrder.indexOf(state.currentTurn);
      if (idx !== -1) {
        nextTurnId = state.turnOrder[(idx + 1) % state.turnOrder.length];
      }
    }

    // Opponents in seating order, starting after "you" for a stable layout.
    const order = state.turnOrder && state.turnOrder.length
      ? state.turnOrder
      : state.players.map((p) => p.user_id);
    const byId = {};
    state.players.forEach((p) => (byId[p.user_id] = p));

    order
      .filter((uid) => uid !== state.you && byId[uid])
      .forEach((uid) => {
        const p = byId[uid];
        const seat = document.createElement("div");
        seat.className = "seat";
        seat.style.setProperty("--seat-color", colorOf(p));
        if (p.user_id === state.currentTurn) seat.classList.add("active");
        if (p.user_id === nextTurnId) seat.classList.add("next");
        if (!p.connected) seat.classList.add("offline");
        if (p.eliminated) seat.classList.add("out");

        const stack = document.createElement("div");
        stack.className = "mini-stack";
        if (p.is_safe) {
          stack.appendChild(badge("SAFE 0", "safe"));
        } else {
          stack.appendChild(backImg("mini"));
          const count = document.createElement("span");
          count.className = "count";
          count.textContent = "\u00d7" + p.card_count; // ×N
          stack.appendChild(count);
        }

        const meta = document.createElement("div");
        meta.className = "seat-meta";
        const name = document.createElement("span");
        name.className = "seat-name";
        name.textContent = p.name;
        
        // Next/Active turn status indicator
        const statusRow = document.createElement("div");
        statusRow.style.display = "flex";
        statusRow.style.alignItems = "center";
        statusRow.style.gap = "0.3rem";
        statusRow.style.marginTop = "0.15rem";
        if (p.user_id === state.currentTurn) {
          statusRow.appendChild(badge("TURN", "turn-now"));
        } else if (p.user_id === nextTurnId) {
          statusRow.appendChild(badge("NEXT", "next-turn"));
        }

        const score = document.createElement("span");
        score.className = "seat-score";
        score.textContent = p.score + " pts";
        
        meta.appendChild(name);
        meta.appendChild(score);
        meta.appendChild(statusRow);

        seat.appendChild(stack);
        seat.appendChild(meta);
        wrap.appendChild(seat);
      });
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
    const seat = document.getElementById("myseat");
    seat.className = "myseat";
    
    // Find next turn
    let nextTurnId = null;
    if (state.turnOrder && state.turnOrder.length > 0 && state.currentTurn) {
      const idx = state.turnOrder.indexOf(state.currentTurn);
      if (idx !== -1) {
        nextTurnId = state.turnOrder[(idx + 1) % state.turnOrder.length];
      }
    }

    if (state.you === state.currentTurn) {
      seat.classList.add("active");
    } else if (state.you === nextTurnId) {
      seat.classList.add("next");
    }
    
    seat.innerHTML = "";

    const me = state.players.find((p) => p.user_id === state.you);
    const name = document.createElement("span");
    name.className = "seat-name";
    name.textContent = (me ? me.name : "You") + " (you)";
    
    const tag = document.createElement("span");
    tag.className = "turn-tag";
    if (state.you === state.currentTurn) {
      tag.textContent = "Your turn";
    } else if (state.you === nextTurnId) {
      tag.textContent = "Up Next \u2794";
    } else {
      tag.textContent = "Waiting";
    }
    
    seat.appendChild(name);
    seat.appendChild(tag);
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
    sortedHand(state.hand).forEach((card) => {
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
    });
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
  };
})();
