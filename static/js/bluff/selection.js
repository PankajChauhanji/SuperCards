(function () {
  const selected = new Set();
  let socket, code, you;

  function view() {
    return window.SS.view || {};
  }

  function selectedCards() {
    const hand = view().hand || [];
    return hand.filter((c) => selected.has(c.id));
  }

  function myTurn() {
    return view().you === view().currentTurn;
  }

  function reset() {
    selected.clear();
    const rs = document.getElementById("rank-selector");
    if (rs) rs.value = "";
    refresh();
  }

  function refresh() {
    const v = view();
    const label = document.getElementById("play-label");
    const throwBtn = document.getElementById("throw-btn");
    const passBtn = document.getElementById("pass-btn");
    const showBtn = document.getElementById("show-btn");
    const rankSelector = document.getElementById("rank-selector");
    if (!label || !throwBtn || !passBtn || !showBtn || !rankSelector) return;

    const inTurn = v.state === "IN_TURN";
    const mine = inTurn && myTurn();

    document.querySelectorAll("#hand .card-slot").forEach((slot) => {
      slot.classList.toggle("selected", selected.has(slot.dataset.id));
      slot.classList.toggle("locked", !mine);
    });

    if (!inTurn) {
      label.textContent = "";
      throwBtn.disabled = true;
      passBtn.disabled = true;
      showBtn.disabled = true;
      rankSelector.style.display = "none";
      return;
    }

    // Show button is enabled if it's my turn AND there is a last_play (from the immediate previous player).
    // Actually, in our logic, anyone can call show? No, the rules say:
    // "Only the immediate next active player has the power to call Show"
    // Since turn has advanced to ME, I am the immediate next active player.
    showBtn.disabled = !(mine && v.lastPlay);

    if (!mine) {
      const them = (v.players || []).find((p) => p.user_id === v.currentTurn);
      label.textContent = them ? "Waiting for " + them.name + "\u2026" : "Waiting\u2026";
      label.className = "play-label muted";
      throwBtn.disabled = true;
      passBtn.disabled = true;
      rankSelector.style.display = "none";
      return;
    }

    passBtn.disabled = false;

    const cards = selectedCards();
    const n = cards.length;
    
    // Rank selector is shown if I have selected cards, AND targetRank is not set.
    // Wait, it's easier to just show it when targetRank is not set.
    if (v.targetRank) {
      rankSelector.style.display = "none";
    } else {
      rankSelector.style.display = "inline-block";
    }

    if (n === 0) {
      label.textContent = v.targetRank ? `Target is ${v.targetRank}. Select cards.` : "Select cards and a rank to start.";
      label.className = "play-label muted";
      throwBtn.disabled = true;
      return;
    }
    if (n > 4) {
      label.textContent = "Max 4 cards.";
      label.className = "play-label bad";
      throwBtn.disabled = true;
      return;
    }

    let declaredRank = v.targetRank;
    if (!declaredRank) {
      declaredRank = rankSelector.value;
    }

    if (declaredRank) {
      label.textContent = `Throw ${n} card(s) as ${declaredRank}s`;
      label.className = "play-label ok";
      throwBtn.disabled = false;
    } else {
      label.textContent = "Select a rank from the dropdown.";
      label.className = "play-label muted";
      throwBtn.disabled = true;
    }
  }

  function toggle(id) {
    if (view().state !== "IN_TURN" || !myTurn()) return;
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    refresh();
  }

  function doThrow() {
    if (view().state !== "IN_TURN" || !myTurn()) return;
    const ids = [...selected];
    if (!ids.length) return;
    
    let declaredRank = view().targetRank;
    if (!declaredRank) {
      declaredRank = document.getElementById("rank-selector").value;
    }

    socket.emit("bluff_play", { code, user_id: you, card_ids: ids, declared_rank: declaredRank });
  }

  function doPass() {
    if (view().state === "IN_TURN" && myTurn()) {
      socket.emit("bluff_pass", { code, user_id: you });
    }
  }

  function doShow() {
    if (view().state === "IN_TURN" && myTurn() && view().lastPlay) {
      socket.emit("bluff_show", { code, user_id: you });
    }
  }

  window.Selection = {
    init(opts) {
      socket = opts.socket;
      code = opts.code;
      you = opts.you;

      document.getElementById("hand").addEventListener("click", (e) => {
        const slot = e.target.closest(".card-slot");
        if (slot) toggle(slot.dataset.id);
      });
      document.getElementById("throw-btn").addEventListener("click", doThrow);
      document.getElementById("pass-btn").addEventListener("click", doPass);
      document.getElementById("show-btn").addEventListener("click", doShow);
      
      const rs = document.getElementById("rank-selector");
      if (rs) rs.addEventListener("change", refresh);
    },
    refresh,
    reset,
  };
})();
