// Selection + actions. Owns which cards the player has picked, mirrors the
// server's action inference to show a live label, and wires Throw + deck-draw.
// The server remains authoritative; this is only UX feedback.
(function () {
  const selected = new Set();
  let socket, code, you;

  function view() {
    return window.SS.view || {};
  }

  // ---- client-side mirror of game/rules.py (for the live label only) ----
  function infer(cards, centerRanks) {
    const ranks = cards.map((c) => c.rank).sort((a, b) => a - b);
    const n = ranks.length;
    if (n === 0) return null;
    if (n === 1) {
      // Single card matching the centre is a Match, not a plain Single.
      if (centerRanks && centerRanks.size && centerRanks.has(ranks[0])) return "match";
      return "single";
    }
    const allSame = ranks.every((r) => r === ranks[0]);
    if ((n === 3 || n === 4) && allSame) return "set";
    if (n >= 3) {
      const distinct = new Set(ranks).size === n;
      let consecutive = true;
      for (let i = 1; i < n; i++) if (ranks[i] !== ranks[i - 1] + 1) consecutive = false;
      if (distinct && consecutive) return "sequence";
    }
    // Match takes priority over pair when the rank is in the centre (free play).
    if (centerRanks && centerRanks.size && cards.every((c) => centerRanks.has(c.rank))) return "match";
    if (n === 2 && allSame) return "pair";
    return null;
  }

  const LABELS = {
    single: "Discard 1 \u00b7 draw 1",
    pair: "Pair \u00b7 draw 1",
    set: "Set \u00b7 no draw",
    sequence: "Sequence \u00b7 no draw",
  };

  function matchLabel() {
    return view().matchRequiresDraw === false ? "Match \u00b7 no draw" : "Match \u00b7 draw 1";
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
    refresh();
  }

  function meRow() {
    return (view().players || []).find((p) => p.user_id === view().you);
  }

  function refresh() {
    const v = view();
    const label = document.getElementById("play-label");
    const throwBtn = document.getElementById("throw-btn");
    const stopBtn = document.getElementById("stop-btn");
    if (!label || !throwBtn || !stopBtn) return;

    const inTurn = v.state === "IN_TURN";
    const mine = inTurn && myTurn();
    const me = meRow();
    const iAmSafe = !!(me && me.is_safe);

    // Re-apply selected styling to whatever slots are in the DOM.
    document.querySelectorAll("#hand .card-slot").forEach((slot) => {
      slot.classList.toggle("selected", selected.has(slot.dataset.id));
      slot.classList.toggle("locked", !mine || v.awaitingDraw);
    });

    // Stop: only at the clean start of your turn, after the first orbit,
    // and never when you're already safe.
    stopBtn.disabled = !(mine && !v.awaitingDraw && v.firstOrbitComplete && !iAmSafe);

    if (!inTurn) {
      label.textContent = "";
      throwBtn.disabled = true;
      return;
    }
    if (!mine) {
      const them = (v.players || []).find((p) => p.user_id === v.currentTurn);
      label.textContent = them ? "Waiting for " + them.name + "\u2026" : "Waiting\u2026";
      label.className = "play-label muted";
      throwBtn.disabled = true;
      return;
    }
    if (v.awaitingDraw) {
      label.textContent = "Click the deck to draw a card";
      label.className = "play-label draw";
      throwBtn.disabled = true;
      return;
    }

    const cards = selectedCards();
    if (cards.length === 0) {
      label.textContent = "Select cards to play";
      label.className = "play-label muted";
      throwBtn.disabled = true;
      return;
    }
    const centerRanks = new Set((v.center || []).map((c) => c.rank));
    const action = infer(cards, centerRanks);
    if (action) {
      label.textContent = action === "match" ? matchLabel() : LABELS[action];
      label.className = "play-label ok";
      throwBtn.disabled = false;
    } else {
      label.textContent = "Not a legal play";
      label.className = "play-label bad";
      throwBtn.disabled = true;
    }
  }

  function toggle(id) {
    if (view().state !== "IN_TURN" || !myTurn() || view().awaitingDraw) return;
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    refresh();
  }

  function doThrow() {
    if (view().state !== "IN_TURN" || !myTurn() || view().awaitingDraw) return;
    const ids = [...selected];
    if (!ids.length) return;
    socket.emit("play_cards", { code, user_id: you, card_ids: ids });
    // Selection clears when the resulting your_hand arrives (hand changed).
  }

  function doDraw() {
    if (view().state === "IN_TURN" && myTurn() && view().awaitingDraw) {
      socket.emit("draw_card", { code, user_id: you });
    }
  }

  function doStop() {
    const v = view();
    const me = meRow();
    if (v.state === "IN_TURN" && myTurn() && !v.awaitingDraw &&
        v.firstOrbitComplete && !(me && me.is_safe)) {
      socket.emit("call_stop", { code, user_id: you });
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
      document.getElementById("deck").addEventListener("click", doDraw);
      document.getElementById("throw-btn").addEventListener("click", doThrow);
      document.getElementById("stop-btn").addEventListener("click", doStop);
    },
    refresh,
    reset,
  };
})();
