(function () {
  const CARD_PATH = "/static/img/cards/";
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  function colorOf(p) { return PALETTE[(p && typeof p.color === "number" ? p.color : 0) % PALETTE.length]; }
  function swatch(p) { const s = document.createElement("span"); s.className = "swatch"; s.style.background = colorOf(p); return s; }
  
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
    list.innerHTML = "";
    const activePlayers = state.players.filter(p => !p.is_spectator);
    const ordered = activePlayers.slice().sort((a, b) => (a.eliminated - b.eliminated));

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
      text.textContent = p.name + (p.user_id === state.you ? " (you)" : "");
      left.appendChild(text);

      li.appendChild(left);
      list.appendChild(li);
    });
  }

  function renderOpponents(state) {
    const wrap = document.getElementById("opponents");
    wrap.innerHTML = "";
    const order = state.turnOrder && state.turnOrder.length ? state.turnOrder : state.players.map((p) => p.user_id);
    const byId = {};
    state.players.forEach((p) => (byId[p.user_id] = p));

    order.filter((uid) => uid !== state.you && byId[uid]).forEach((uid) => {
        const p = byId[uid];
        const seat = document.createElement("div");
        seat.className = "seat";
        seat.style.setProperty("--seat-color", colorOf(p));
        if (p.user_id === state.currentTurn) seat.classList.add("active");
        if (!p.connected) seat.classList.add("offline");
        if (p.eliminated) seat.classList.add("out");

        const stack = document.createElement("div");
        stack.className = "mini-stack";
        stack.appendChild(backImg("mini"));
        const count = document.createElement("span");
        count.className = "count";
        count.textContent = "\u00d7" + (p.card_count || 0);
        stack.appendChild(count);

        const meta = document.createElement("div");
        meta.className = "seat-meta";
        const name = document.createElement("span");
        name.className = "seat-name";
        name.textContent = p.name;
        meta.appendChild(name);

        seat.appendChild(stack);
        seat.appendChild(meta);
        wrap.appendChild(seat);
      });
  }

  function renderCenter(state) {
    const discard = document.getElementById("center-pile");
    const empty = document.getElementById("center-empty");
    const countSpan = document.getElementById("center-count");
    const badgeCount = document.getElementById("center-badge-count");
    
    const count = state.centerCount || 0;
    countSpan.textContent = count;
    
    discard.querySelectorAll(".card").forEach((el) => el.remove());

    empty.style.display = count ? "none" : "block";
    if (badgeCount) {
      badgeCount.style.display = count ? "block" : "none";
      badgeCount.textContent = count;
    }
    for(let i = 0; i < Math.min(count, 10); i++) {
      const img = backImg("center-card");
      img.style.marginLeft = i === 0 ? "0" : "-34px";
      discard.appendChild(img);
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
    const seat = document.getElementById("myseat");
    seat.className = "myseat";
    if (state.you === state.currentTurn) seat.classList.add("active");
    seat.innerHTML = "";

    const me = state.players.find((p) => p.user_id === state.you);
    const name = document.createElement("span");
    name.className = "seat-name";
    name.textContent = (me ? me.name : "You") + " (you)";
    seat.appendChild(name);
  }

  function renderHand(state) {
    const hand = document.getElementById("hand");
    hand.innerHTML = "";
    
    // Sort hand in descending order of rank
    const sortedHand = (state.hand || []).slice().sort((a, b) => {
      if (a.rank !== b.rank) return b.rank - a.rank;
      const suitOrder = { S: 0, H: 1, D: 2, C: 3 };
      return (suitOrder[a.suit] || 0) - (suitOrder[b.suit] || 0);
    });

    sortedHand.forEach((card) => {
      const slot = document.createElement("div");
      slot.className = "card-slot";
      slot.dataset.id = card.id;
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
      renderScoreboard(state);
      renderOpponents(state);
      renderCenter(state);
      renderMySeat(state);
      renderHand(state);
    },
  };
})();
