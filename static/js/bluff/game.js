// Game page controller. Holds the client's view of the room and routes server
// events to either the lobby or the table renderer. Actions (throw/draw/stop)
// arrive in later phases; Phase 1 deals and renders only.
(function () {
  const { socket, showToast } = window.SS;

  const code = window.SS_ROOM_CODE;
  const youId = window.Identity.userId();

  // Single source of truth for what this client is showing.
  const view = {
    you: youId,
    hostId: null,
    state: "LOBBY",
    players: [],
    currentTurn: null,
    turnOrder: [],
    deckCount: 0,
    center: [],
    hand: [],
    roundNumber: 0,
    awaitingDraw: false,
    lastWasCombo: false,
    matchRequiresDraw: true,
    firstOrbitComplete: false,
    secondsLeft: null,
    pickSecondsLeft: null,
    justDrawnId: null,
    settings: null,
    // User ids in the order they shed their last card — the game's only ranking.
    finishOrder: [],
  };
  window.SS.view = view; // selection.js reads this live reference

  const nameOf = (uid) => {
    const p = view.players.find((x) => x.user_id === uid);
    return p ? p.name : "Someone";
  };

  // Every Table.render() can change the felt's height (hand size, opponent
  // count) which shifts where its bottom-right corner is — reposition the
  // reaction dock after each one rather than chasing every call site below.
  const _renderTable = Table.render;
  Table.render = function (v) {
    _renderTable(v);
    if (window.SS.positionReactionDock) window.SS.positionReactionDock();
  };

  // Resolve a player's stable colour index (for colouring names in the feed).
  function colorIndexOf(uid) {
    const p = view.players.find((x) => x.user_id === uid);
    return p ? p.color : -1;
  }

  let prevTurn = null;   // for the your-turn sound cue
  let drawnTimer = null; // clears the just-drawn highlight

  const lobbyView = document.getElementById("lobby-view");
  const tableView = document.getElementById("table-view");
  const codeEl = document.getElementById("room-code");
  const rosterEl = document.getElementById("roster");
  const metaEl = document.getElementById("lobby-meta");
  const startRow = document.getElementById("start-row");

  codeEl.textContent = code;

  // ---- attach / reconnect ----
  function enter() {
    socket.emit("enter_room", { code, name: window.Identity.name(), user_id: youId });
  }
  socket.on("connect", enter);
  // Returning to the foreground must re-attach too: a zombie socket fires no
  // `connect`, so this is what clears the "player is absent" state.
  if (window.SS.onResync) window.SS.onResync(enter);
  // Repaint from state we already hold (deck swap, hand-view change, a viewport
  // that resized while the page was frozen in the background).
  if (window.SS.onRepaint) window.SS.onRepaint(() => Table.render(view));
  if (socket.connected) enter();

  // ---- server events ----
  socket.on("room_joined", (data) => {
    view.hostId = data.host_id;
    view.state = data.state;
    view.players = data.players;
    if (data.settings) view.settings = data.settings;
    view.tableTheme = data.table_theme || "casino";
    syncTableTheme();
    sync();
  });

  socket.on("player_list", (data) => {
    view.hostId = data.host_id;
    view.players = data.players;
    sync();
  });

  socket.on("room_reset", (data) => {
    view.state = "LOBBY";
    view.hostId = data.host_id;
    view.players = data.players;
    if (data.settings) view.settings = data.settings;
    view.tableTheme = data.table_theme || "casino";
    syncTableTheme();
    view.hand = [];
    view.justDrawnId = null;
    view.secondsLeft = null;
    /* A rematch is a fresh race — otherwise last game's places would suppress
       the announcements for this one. */
    view.finishOrder = [];
    if (window.SS.hideWinnerScreen) window.SS.hideWinnerScreen();
    prevTurn = null;
    document.getElementById("roundend-modal").classList.remove("open");
    if (window.SS.hideWinnerScreen) window.SS.hideWinnerScreen();
    sync();
    showToast("New game — back to the lobby");
  });

  socket.on("round_start", (data) => {
    view.state = "IN_TURN";
    // A fresh deal (or a resync) sets the baseline for noticing shuffles; it is
    // not itself a shuffle to announce.
    view.seatShuffles = null;
    applyTable(data);
    document.getElementById("roundend-modal").classList.remove("open");
    if (window.SS.hideWinnerScreen) window.SS.hideWinnerScreen();
    if (window.Selection) window.Selection.reset();
    if (window.ActionLog) { window.ActionLog.clear(); window.ActionLog.push("Round " + (view.roundNumber || 1) + " started. Cards dealt!", "system"); }
    sync();
  });

  socket.on("table_state", (data) => {
    applyTable(data);
    if (view.state === "IN_TURN") {
      Table.render(view);
      if (window.Selection) window.Selection.refresh();
    }
    syncPickTimer();
  });

  function applyTable(data) {
    if (data.state) view.state = data.state;
    view.players = data.players;
    if (data.host_id) view.hostId = data.host_id;
    if (data.settings) view.settings = data.settings;
    if (data.table_theme) view.tableTheme = data.table_theme;
    view.currentTurn = data.current_turn;
    view.turnOrder = data.turn_order;
    view.deckCount = data.deck_count;
    view.center = data.center;
    view.centerCount = data.center_count;
    view.targetRank = data.target_rank;
    view.lastPlay = data.last_play;
    view.roundNumber = data.round_number;
    if (typeof data.turn_seconds_left === "number") view.secondsLeft = data.turn_seconds_left;
    applyFinishOrder(data.finish_order);
    applySeatShuffle(data);


    // Sound cue when the turn becomes mine.
    if (view.state === "IN_TURN" && view.currentTurn === youId && prevTurn !== youId) {
      if (window.SS.sound) window.SS.sound.turnPing();
    }
    prevTurn = view.currentTurn;
  }

  socket.on("your_hand", (data) => {
    view.hand = data.cards || [];
    // If the server tells us whether a draw is owed, apply it immediately.
    // Prevents stale awaitingDraw=true flash between your_hand and table_state
    // (e.g. after a Match with MATCH_REQUIRES_DRAW=false).
    if (typeof data.owes_draw === "boolean") {
      view.awaitingDraw = data.owes_draw;
    }
    if (data.drawn) {
      view.justDrawnId = data.drawn;
      clearTimeout(drawnTimer);
      // Found via live instrumentation on Super Seven (same code shape
      // here): this used to call Table.render(view) — a full destructive
      // rebuild of the whole hand — just to clear one card's highlight
      // outline. The 5s timer fires on its own clock from whenever YOU
      // drew, unrelated to anything else going on, so it can land within a
      // second of an opponent's throw and read as "my cards got thrown
      // again". Removing the one class directly gives the same visual
      // result (the gold outline disappears) with no rebuild.
      drawnTimer = setTimeout(() => {
        view.justDrawnId = null;
        const slot = document.querySelector('.card-slot.just-drawn');
        if (slot) slot.classList.remove("just-drawn");
      }, 5000);
    } else {
      view.justDrawnId = null;
    }
    if (window.Selection) window.Selection.reset();
    if (view.state === "IN_TURN") {
      Table.render(view);
    }
  });

  socket.on("cards_played", (data) => {
    const p = view.players.find((x) => x.user_id === data.by);
    const who = p ? p.name : (data.by === youId ? "You" : "Someone");
    const msg = `${who} threw ${data.count} card(s) as ${data.declared_rank}`;
    if (window.ActionLog) window.ActionLog.push(msg, "play", { actor: who, colorIndex: p ? p.color : -1 });
    if (data.by !== youId) showToast(msg);
  });

  socket.on("player_passed", (data) => {
    const p = view.players.find((x) => x.user_id === data.by);
    const who = p ? p.name : "Someone";
    const msg = `${who} passed`;
    if (window.ActionLog) window.ActionLog.push(msg, "pass", { actor: who, colorIndex: p ? p.color : -1 });
    showToast(msg);
  });

  socket.on("bluff_show_result", (data) => {
    const challenger = view.players.find(p => p.user_id === data.challenger);
    const defender = view.players.find(p => p.user_id === data.defender);
    const chName = challenger ? challenger.name : "Someone";
    const defName = defender ? defender.name : "Someone";
    
    // Visually reveal the cards on the table
    if (window.Table && window.Table.showRevealed) {
      window.Table.showRevealed(data.revealed_cards);
    }
    
    // Also use the play-status label if available
    const label = document.getElementById("play-status");
    
    if (window.ActionLog) window.ActionLog.push(`${chName} called Show on ${defName}!`, "challenge");
    
    if (data.is_bluff) {
      const msg = `${chName} caught ${defName}'s bluff! ${defName} takes the pile!`;
      showToast(msg);
      if (window.ActionLog) window.ActionLog.push(msg, "challenge");
      if (label) {
        label.textContent = msg;
        label.className = "play-label bad";
      }
    } else {
      const msg = `${defName} told the truth! ${chName} was wrong and takes the pile!`;
      showToast(msg);
      if (window.ActionLog) window.ActionLog.push(msg, "challenge");
      if (label) {
        label.textContent = msg;
        label.className = "play-label bad";
      }
    }
  });

  socket.on("auto_picked", (data) => {
    if (data.user_id === youId) showToast("Auto-picked a card for you");
    else showToast(data.name + " was dealt a card");
  });

  socket.on("deck_reshuffled", () => showToast("Deck reshuffled"));

  socket.on("player_timed_out", (data) => {
    if (data.removed) return; // an elimination toast follows
    showToast(data.name + " ran out of time");
  });

  socket.on("player_eliminated", (data) => {
    showToast(data.name + " is out of the game");
  });

  socket.on("kicked", () => {
    alert("You have been removed from the room by the host.");
    window.location.href = "/";
  });

  socket.on("settings_updated", (data) => {
    if (data.settings) view.settings = data.settings;
    if (view.state !== "IN_TURN") window.SS.Lobby.render(view);
    showToast("Host updated the game settings");
  });

  socket.on("round_end", (data) => {
    view.state = "ROUND_END";
    view.secondsLeft = null;
    if (data.host_id) view.hostId = data.host_id;
    if (data.players) view.players = data.players;
    if (tableView.style.display !== "none") Table.render(view);
    if (window.Selection) window.Selection.refresh();
    if (data.game_over) {
      showGameOver(data.winner, gameOverRows(data.results));
    } else {
      showRoundEnd(data);
    }
  });

  socket.on("game_end", (data) => {
    view.state = "GAME_END";
    view.secondsLeft = null;
    if (data.host_id) view.hostId = data.host_id;
    if (data.players) view.players = data.players;
    const wp = view.players.find(p => p.user_id === data.winner);
    if (window.ActionLog) window.ActionLog.push(`🎉 ${wp ? wp.name : "Someone"} wins the game!`, "win");
    showGameOver(data.winner, data.standings);
  });

  // ---- turn timer countdown ----
  // The countdown itself now lives on the active seat's ring (Table.tick),
  // not a separate topbar chip.
  function syncPickTimer() {
    const el = document.getElementById("pick-timer");
    if (!el) return;
    const mine = view.currentTurn === youId;
    if (view.state === "IN_TURN" && view.awaitingDraw && mine && view.pickSecondsLeft != null) {
      el.style.display = "block";
      el.textContent = Math.max(0, view.pickSecondsLeft);
    } else {
      el.style.display = "none";
    }
  }

  setInterval(() => {
    if (view.state === "IN_TURN" && typeof view.secondsLeft === "number" && view.secondsLeft > 0) {
      view.secondsLeft -= 1;
      if (tableView.style.display !== "none") Table.tick(view);
    }
    if (view.state === "IN_TURN" && view.awaitingDraw &&
        typeof view.pickSecondsLeft === "number" && view.pickSecondsLeft > 0) {
      view.pickSecondsLeft -= 1;
    }
    syncPickTimer();
  }, 1000);

  // ---- view switching ----
  function sync() {
    renderShuffle();
    const inRound = view.state === "IN_TURN";
    lobbyView.style.display = inRound ? "none" : "block";
    tableView.style.display = inRound ? "flex" : "none";
    const dock = document.getElementById("reaction-dock");
    if (dock) dock.style.display = inRound ? "flex" : "none";

    syncThemeSelectorVisibility();
    syncTableTheme();

    if (inRound) {
      Table.render(view);
    } else {
      window.SS.Lobby.render(view);
    }
  }

  // ---- lobby (shared renderer: static/js/core/lobby.js) ----
  window.SS.Lobby.init({
    youId,
    fields: [
      { key: "turn_timer", label: "Turn timer (s)", min: 15, max: 180 },
      { key: "timeout_limit", label: "Timeouts allowed", min: 1, max: 10 },
      { key: "num_decks", label: "Number of decks", min: 1, max: 5 },
    ],
  });

  function makeBadge(text, kind) {
    const b = document.createElement("span");
    b.className = "badge " + kind;
    b.textContent = text;
    b.style.marginLeft = "0.4rem";
    return b;
  }

  // ---- round-end reveal ----
  function showRoundEnd(data) {
    const modal = document.getElementById("roundend-modal");
    const title = document.getElementById("roundend-title");
    const sub = document.getElementById("roundend-sub");
    const body = document.getElementById("roundend-body");

    const byId = {};
    view.players.forEach((p) => (byId[p.user_id] = p));
    const callerName = data.caller ? (byId[data.caller] || {}).name || "Someone" : null;

    if (!data.caller) {
      title.textContent = "Round over";
      sub.textContent = "Everyone emptied their hand.";
    } else if (data.caught) {
      title.textContent = callerName + " got caught";
      sub.textContent = "Someone matched or beat the call — penalty applied.";
    } else {
      title.textContent = callerName + " called it";
      sub.textContent = "Lowest at the table — the call paid off.";
    }

    // Lowest round score first.
    const rows = data.results.slice().sort((a, b) => a.round_score - b.round_score);
    body.innerHTML = "";
    rows.forEach((r) => {
      const row = document.createElement("div");
      row.className = "re-row";
      if (r.user_id === data.caller) row.classList.add("caller");

      const head = document.createElement("div");
      head.className = "re-head";
      const name = document.createElement("span");
      name.className = "re-name";
      name.textContent = r.name;
      if (r.user_id === data.caller) name.appendChild(makeBadge("Caller", "host"));
      const score = document.createElement("span");
      score.className = "re-score";
      score.textContent = "+" + r.round_score + "  \u2192  " + r.total_score;
      head.appendChild(name);
      head.appendChild(score);

      const cards = document.createElement("div");
      cards.className = "re-cards";
      if (r.hand.length === 0) {
        const none = document.createElement("span");
        none.className = "re-empty";
        none.textContent = "empty hand";
        cards.appendChild(none);
      } else {
        r.hand.forEach((c) => {
          const img = document.createElement("img");
          img.className = "card re-card";
          img.src = window.SS.cardSrc(c.face);
          img.alt = c.code + c.suit;
          cards.appendChild(img);
        });
        const tot = document.createElement("span");
        tot.className = "re-total";
        tot.textContent = r.hand_total + " pts";
        cards.appendChild(tot);
      }

      row.appendChild(head);
      row.appendChild(cards);
      body.appendChild(row);
    });

    // Footer: host advances the game; others wait.
    const footer = document.getElementById("roundend-footer");
    footer.innerHTML = "";
    if (youId === view.hostId) {
      const btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.textContent = "Next round";
      btn.addEventListener("click", () => {
        btn.disabled = true;
        socket.emit("bluff_next_round", { code, user_id: youId });
      });
      footer.appendChild(btn);
    } else {
      const wait = document.createElement("p");
      wait.className = "waiting";
      wait.style.margin = "0";
      wait.textContent = "Waiting for the host to deal the next round\u2026";
      footer.appendChild(wait);
    }

    modal.classList.add("open");
  }

  // Build standings rows from a round_end results array (for a game-over reveal).
  function gameOverRows(resultRows) {
    return resultRows
      .map((r) => ({
        user_id: r.user_id, name: r.name,
        total_score: r.total_score, eliminated: r.eliminated,
      }))
      .sort((a, b) => (a.eliminated - b.eliminated) || (a.total_score - b.total_score));
  }

  // ---- host's "Shuffle seats" ------------------------------------------------
  // Driven by state, not a one-shot event: shuffle_pending says one is queued,
  // and seat_shuffles rising says one was applied — so a client that missed a
  // broadcast still catches up on its next sync (see sockets/sync.py).
  const shuffleBtn = document.getElementById("bluff-shuffle-btn");
  const shuffleNote = document.getElementById("bluff-shuffle-note");

  function applySeatShuffle(data) {
    view.shufflePending = !!data.shuffle_pending;
    if (typeof data.seat_shuffles === "number") {
      if (typeof view.seatShuffles === "number" && data.seat_shuffles > view.seatShuffles) {
        announceShuffle();
      }
      view.seatShuffles = data.seat_shuffles;
    }
    renderShuffle();
  }

  function announceShuffle() {
    const order = (view.turnOrder || []).filter((uid) => {
      const p = view.players.find((x) => x.user_id === uid);
      return p && !p.eliminated && (view.finishOrder || []).indexOf(uid) === -1;
    });
    const names = order.map((uid) => (uid === youId ? "You" : nameOf(uid)));
    const leader = view.currentTurn === youId ? "You lead" : nameOf(view.currentTurn) + " leads";
    showToast("\uD83D\uDD00 Seats shuffled \u2014 " + leader, 2600);
    if (window.ActionLog && names.length) {
      window.ActionLog.push("\uD83D\uDD00 Seats shuffled: " + names.join(" \u2192 "), "system");
    }
  }

  function renderShuffle() {
    if (!shuffleBtn || !shuffleNote) return;
    const live = view.state === "IN_TURN";
    const host = view.hostId === youId;
    shuffleBtn.hidden = !(live && host);
    shuffleBtn.classList.toggle("pending", !!view.shufflePending);
    // Queued: the note beside it already says what will happen, so the
    // button only has to offer the undo.
    shuffleBtn.textContent = view.shufflePending ? "Cancel" : "\uD83D\uDD00 Shuffle seats";
    shuffleNote.hidden = !(live && view.shufflePending);
    const row = document.getElementById("bluff-shuffle-row");
    if (row) row.hidden = shuffleBtn.hidden && shuffleNote.hidden;
  }

  if (shuffleBtn) {
    shuffleBtn.addEventListener("click", () => {
      socket.emit("bluff_shuffle_seats", { code, user_id: youId });
    });
  }

  // ---- finishing places -------------------------------------------------
  // Bluff no longer stops at the first player to shed their hand: play runs on
  // until the podium is settled, so "who is out, and in which place" is live
  // information the table needs while the game continues.
  //
  // Driven off the server's finish_order in every state payload rather than a
  // one-shot "player is out" event: a client that missed the event would keep
  // showing a finished player as still in the race until it reloaded, whereas
  // state is re-sent on every resync (see sockets/sync.py).
  const ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th"];

  function ordinal(place) {
    return ORDINALS[place - 1] || place + "th";
  }

  function applyFinishOrder(order) {
    if (!Array.isArray(order)) return;
    const known = view.finishOrder || [];
    order.slice(known.length).forEach((uid, i) => {
      const place = known.length + i + 1;
      const who = uid === youId ? "You" : nameOf(uid);
      const verb = uid === youId ? "are" : "is";
      const msg = `${who} ${verb} out — ${ordinal(place)} place!`;
      if (window.ActionLog) window.ActionLog.push(msg, "win");
      showToast(msg, 2600);
    });
    view.finishOrder = order.slice();
  }

  function showGameOver(winnerId, rows) {
    const mine = (rows || []).find((r) => r.user_id === youId);
    window.SS.showWinnerScreen({
      winnerId,
      rows,
      youId,
      isHost: youId === view.hostId,
      onRematch: () => socket.emit("rematch", { code, user_id: youId }),
      subtitle: winnerId === youId
        ? "You shed your last card first."
        : (mine && mine.finished
            ? `You finished ${ordinal(mine.place)}.`
            : "First to shed every card takes the game."),
      // Bluff keeps no score. A player who went out is ranked by when, and
      // everyone still holding cards by how many are left — so that is what the
      // podium says, instead of points the game never counted.
      scoreText: (row) => (row.finished
        ? ordinal(row.place)
        : row.cards_left + (row.cards_left === 1 ? " card left" : " cards left")),
    });
  }

  // ---- reactions ---- (shared: static/js/core/reactions.js)

  // ---- selection / actions ----
  if (window.Selection) {
    window.Selection.init({ socket, code, you: youId });
  }

  // ---- rules modal, mute, copy, spectator admit ----
  // All shared now: static/js/core/{rules_modal,chrome}.js

  // ---- table theme (shared impl: static/js/core/themes.js) ----
  function syncThemeSelectorVisibility() {
    if (window.SS.themes) window.SS.themes.syncVisibility(view.hostId === youId);
  }
  function syncTableTheme() {
    if (window.SS.themes) window.SS.themes.apply(view.tableTheme || "casino");
  }
  socket.on("table_theme_updated", (data) => {
    view.tableTheme = data.theme;
    syncTableTheme();
  });
})();
