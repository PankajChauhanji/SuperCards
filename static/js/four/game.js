// Super 4 game controller: renders the 4-slot memory table and routes actions.
// Reuses the shared shell chrome (lobby, rules modal, reactions, round-end).
(function () {
  const { socket, showToast } = window.SS;
  const code = window.SS_ROOM_CODE;
  const gameType = window.GAME_TYPE || "super_four";
  const youId = window.Identity.userId();

  const view = {
    you: youId, hostId: null, state: "LOBBY", players: [],
    currentTurn: null, turnOrder: [], deckCount: 0,
    drawn: null, drawnBy: null, center: null, phase: "draw",
    pendingPower: null, match: null, firstOrbitComplete: false, stopCaller: null,
    roundNumber: 0, settings: null, secondsLeft: null, tableTheme: "default",
    known: {},          // "owner:slot" -> card dict (only what I may see)
    flashes: {},        // "owner:slot" -> {card, until} : briefly-shown (peeks)
    previewLeft: 0,     // seconds left in the initial preview window
    interaction: null,  // { mode, firstPick }
    kingLook: null,     // [{owner,slot,card}, ...] awaiting swap decision
    _sig: "",
  };
  const PREVIEW_SLOTS = [0, 1];
  const FLASH_MS = 5000;
  let prevTurn = null;

  // ---- DOM ----
  const $ = (id) => document.getElementById(id);
  const lobbyView = $("lobby-view"), tableView = $("table-view");
  const rosterEl = $("roster"), metaEl = $("lobby-meta"), startRow = $("start-row");
  const lobbySettings = $("lobby-settings"), roundChip = $("round-chip");
  const oppEl = $("s4-opponents"), deckCountEl = $("s4-deck-count");
  const centerEl = $("s4-center"), centerEmpty = $("s4-center-empty"), drawnEl = $("s4-drawn");
  const mySlotsEl = $("s4-my-slots"), myNameEl = $("s4-myname");
  const instrEl = $("s4-instr"), btnsEl = $("s4-btns"), scoreList = $("score-list");
  if ($("room-code")) $("room-code").textContent = code;

  const SUIT = { H: "♥", D: "♦", S: "♠", C: "♣" };
  const cardImg = (face) => `/static/img/cards/${face}.svg`;
  const kkey = (o, s) => o + ":" + s;
  const nameOf = (uid) => { const p = view.players.find((x) => x.user_id === uid); return p ? p.name : "Someone"; };

  // ---- attach / reconnect ----
  function enter() { socket.emit("enter_room", { code, name: window.Identity.name(), user_id: youId }); }
  socket.on("connect", enter);
  if (socket.connected) enter();

  // ---- lobby / roster events (shared shape) ----
  socket.on("room_joined", (d) => {
    view.hostId = d.host_id; view.state = d.state; view.players = d.players;
    if (d.settings) view.settings = d.settings;
    view.tableTheme = d.table_theme || "default";
    syncTableTheme();
    sync();
  });
  socket.on("player_list", (d) => {
    const before = new Set(view.players.map((p) => p.user_id));
    view.hostId = d.host_id; view.players = d.players;
    // Mid-game joiners arrive as spectators: tell the table about them.
    if (before.size) {
      d.players.forEach((p) => {
        if (!before.has(p.user_id) && p.is_spectator) {
          showToast(p.name + " is watching — spectators can join from the next round");
        }
      });
    }
    if (view.state === "IN_TURN") renderTable(); else window.SS.Lobby.render(view);
    syncThemeSelectorVisibility();
  });
  socket.on("room_reset", (d) => {
    view.state = "LOBBY"; view.hostId = d.host_id; view.players = d.players;
    if (d.settings) view.settings = d.settings;
    if (d.table_theme) { view.tableTheme = d.table_theme; syncTableTheme(); }
    view.known = {}; view.interaction = null; view.kingLook = null;
    closeModal("roundend-modal"); sync(); showToast("New game — back to the lobby");
  });
  socket.on("settings_updated", (d) => {
    if (d.settings) view.settings = d.settings;
    if (view.state !== "IN_TURN") window.SS.Lobby.render(view);
  });
  socket.on("kicked", () => { alert("You were removed by the host."); window.location.href = "/"; });

  // ---- gameplay events ----
  socket.on("round_start", (d) => {
    applyState(d); closeModal("roundend-modal");
    view.interaction = null; view.kingLook = null;
    if (window.ActionLog) { window.ActionLog.clear(); window.ActionLog.push("Round " + (view.roundNumber || 1) + " started!", "system"); }
    sync();
  });
  socket.on("s4_state", (d) => {
    applyState(d);
    if (view.state === "IN_TURN") renderTable();
    syncTimer(); syncRoundChip();
  });
  socket.on("your_view", (d) => {
    view.known = {};
    (d.known || []).forEach((k) => { view.known[kkey(k.owner, k.slot)] = k.card; });
    // Only the player who drew receives this card in their private payload.
    view.drawn = d.drawn || null;
    if (view.state === "IN_TURN") renderTable();
  });
  socket.on("s4_peek", (d) => {
    _flash(d.owner, d.slot, d.card);       // shown briefly, then you must remember
    renderTable();
    const who = d.owner === youId ? "your card" : nameOf(d.owner) + "'s card";
    const msg = `Peeked ${who}: ${d.card.code}${SUIT[d.card.suit] || ""}`;
    if (window.ActionLog) window.ActionLog.push(msg, "info");
    showToast(msg);
  });
  socket.on("s4_king_look", (d) => {
    view.kingLook = d.looked || [];
    (d.looked || []).forEach((k) => _flash(k.owner, k.slot, k.card));
    renderTable();
  });
  socket.on("s4_round_end", (d) => {
    view.state = "ROUND_END"; view.secondsLeft = null;
    if (d.players) view.players = d.players;
    syncTimer(); showRoundEnd(d);
  });
  socket.on("s4_timeout", (d) => {
    // Room-wide announcements come from the server; this is your personal note.
    if (d.user_id !== youId) return;
    const msg = d.removed
      ? "You missed too many turns — you're spectating now. Ask the host to admit you back."
      : "You ran out of time — your turn was auto-played";
    if (window.ActionLog) window.ActionLog.push(msg, "system");
    showToast(msg, 3200);
  });
  socket.on("toast", (d) => {
    if (window.ActionLog) window.ActionLog.push(d.message, "info");
    showToast(d.message, d.ms);
  });

  function applyState(d) {
    if (d.state) view.state = d.state;
    if (d.players) view.players = d.players;
    if (d.host_id) view.hostId = d.host_id;
    if (d.settings) view.settings = d.settings;
    if (d.table_theme && d.table_theme !== view.tableTheme) {
      view.tableTheme = d.table_theme; syncTableTheme();
    }
    view.currentTurn = d.current_turn;
    view.turnOrder = d.turn_order || [];
    view.deckCount = d.deck_count;
    // Public state deliberately never carries the drawn face.
    if (!d.draw_pending) view.drawn = null;
    view.drawnBy = d.drawn_by;
    view.center = d.center; view.phase = d.phase;
    view.pendingPower = d.pending_power;
    view.match = d.match || null;
    view.transientReveals = d.transient_reveals || [];
    view.firstOrbitComplete = !!d.first_orbit_complete;
    view.stopCaller = d.stop_caller;
    view.roundNumber = d.round_number;
    if (typeof d.turn_seconds_left === "number") view.secondsLeft = d.turn_seconds_left;
    if (typeof d.preview_seconds_left === "number") view.previewLeft = d.preview_seconds_left;

    if (view.state === "IN_TURN" && view.currentTurn === youId && prevTurn !== youId) {
      if (window.SS.sound && window.SS.sound.turnPing) window.SS.sound.turnPing();
    }
    prevTurn = view.currentTurn;

    // Reset a stale interaction when the turn/phase/power changes.
    const sig = `${view.phase}|${view.currentTurn}|${view.pendingPower ? view.pendingPower.rank : ""}`;
    if (sig !== view._sig) { view.interaction = null; view._sig = sig; }
    // Clear a King look once it's no longer my pending power.
    const myPower = view.phase === "power" && view.pendingPower && view.pendingPower.by === youId;
    if (!myPower) view.kingLook = null;
  }

  // ---- view switching ----
  function sync() {
    const inRound = view.state === "IN_TURN";
    lobbyView.style.display = inRound ? "none" : "block";
    tableView.style.display = inRound ? "flex" : "none";
    const dock = $("reaction-dock");
    if (dock) dock.style.display = inRound ? "flex" : "none";
    if (inRound) renderTable(); else window.SS.Lobby.render(view);
    syncRoundChip();
    syncThemeSelectorVisibility();
  }

  // ================= lobby =================
  // Shared renderer (roster + settings tabs + start): static/js/core/lobby.js
  window.SS.Lobby.init({
    youId,
    fields: [
      { key: "turn_timer", label: "Turn time (s)", min: 15, max: 180 },
      { key: "match_window", label: "Match window (s)", min: 0, max: 10 },
      { key: "preview_seconds", label: "Preview (s)", min: 3, max: 30 },
      { key: "rounds", label: "Rounds", min: 1, max: 20 },
      { key: "exit_score", label: "Exit score (out)", min: 3, max: 100 },
      { key: "win_score", label: "Stop win (caller)", min: -20, max: 0 },
      { key: "stop_loss_score", label: "Others on won Stop", min: 0, max: 20 },
      { key: "loss_score", label: "Loss (other rounds)", min: 0, max: 20 },
      { key: "penalty_score", label: "Caught-Stop penalty", min: 0, max: 40 },
      { key: "timeout_limit", label: "Missed turns (out)", min: 1, max: 10 },
    ],
  });

  // ================= table =================
  function canMatchNow() {
    return view.phase === "match" && view.match &&
      !(view.match.attempted || []).includes(youId);
  }

  function armAutoInteraction() {
    // During a match window I can attempt, arm the "match_center" targeting mode.
    // Never clobber an in-progress match flow (match_replacements is the second
    // step of the same attempt — resetting it would throw the selection away).
    if (canMatchNow()) {
      const m = view.interaction && view.interaction.mode;
      if (m !== "match_center" && m !== "match_replacements") {
        view.interaction = { mode: "match_center", targets: [] };
      }
      return;
    }
    // Powers auto-arm their targeting mode BEFORE slots render, so slots pick up
    // selectability in a single pass (no re-render loop).
    const myPower = view.phase === "power" && view.pendingPower && view.pendingPower.by === youId;
    if (myPower && !view.kingLook) {
      const rank = view.pendingPower.rank;
      const kind = rank === 7 || rank === 8 ? "peek_own"
        : rank === 9 || rank === 10 ? "peek_opp"
        : rank === 11 || rank === 12 ? "blind_swap" : "king";
      if (!view.interaction || view.interaction.mode !== kind) view.interaction = { mode: kind, firstPick: null };
    }
  }

  function renderTable() {
    armAutoInteraction();
    const me = view.players.find((p) => p.user_id === youId);
    myNameEl.textContent = (me ? window.SS.shortName(me.name) : "You") + (view.currentTurn === youId ? "  • your turn" : "");

    // opponents
    oppEl.innerHTML = "";
    view.players.filter((p) => p.user_id !== youId && !p.is_spectator).forEach((p) => {
      const seat = document.createElement("div");
      seat.className = "s4-seat" + (view.currentTurn === p.user_id ? " turn" : "");
      const head = document.createElement("div"); head.className = "seat-name";
      head.innerHTML = `<span>${escapeHtml(window.SS.shortName(p.name))}${p.user_id === view.stopCaller ? " ✋" : ""}</span>` +
        `<span class="seat-total">${p.score}</span>`;
      seat.appendChild(head);
      seat.appendChild(renderSlots(p.user_id, p.slots || [], false, true));
      oppEl.appendChild(seat);
    });

    // my slots
    mySlotsEl.innerHTML = "";
    mySlotsEl.appendChild(renderSlots(youId, (me && me.slots) || [], true, true));

    // center + deck + drawn
    deckCountEl.textContent = view.deckCount;
    if (view.center) {
      centerEl.style.backgroundImage = "";
      centerEmpty.style.display = "none";
      setPileCard(centerEl, view.center);
    } else {
      centerEmpty.style.display = "";
      clearPileCard(centerEl);
    }
    if (view.drawn) {
      drawnEl.style.visibility = "visible";
      drawnEl.classList.toggle("active", view.drawnBy === youId);
      setPileCard(drawnEl, view.drawn);
    } else {
      drawnEl.style.visibility = "hidden";
      clearPileCard(drawnEl);
    }

    renderScoreboard();
    renderActions();
  }

  function _flash(owner, slot, card) {
    view.flashes[kkey(owner, slot)] = { card: card, until: Date.now() + FLASH_MS };
  }

  function _visibleFace(owner, i) {
    // A public reveal (failed match) is shown to everyone.
    const reveal = (view.transientReveals || []).find((r) => r.owner === owner && r.slot === i);
    if (reveal) return reveal.card;
    // A peek/King look flashes briefly to the viewer, then hides (memory!).
    const fl = view.flashes[kkey(owner, i)];
    if (fl && fl.until > Date.now()) return fl.card;
    // The initial preview: your own first two cards, only while the window is open.
    if (owner === youId && PREVIEW_SLOTS.indexOf(i) !== -1 && view.previewLeft > 0) {
      return view.known[kkey(owner, i)] || null;
    }
    return null;
  }

  function renderSlots(owner, occ, isMine, attachClicks) {
    const wrap = document.createElement("div"); wrap.className = "s4-slots";
    const mode = view.interaction ? view.interaction.mode : null;
    occ.forEach((occupied, i) => {
      const slot = document.createElement("div");
      slot.className = "s4-slot" + (occupied ? "" : " empty");
      slot.dataset.owner = owner; slot.dataset.slot = i;
      // Index number on every card (1-4), yours and opponents'.
      const num = document.createElement("span"); num.className = "slot-num"; num.textContent = i + 1;
      slot.appendChild(num);
      const card = occupied ? _visibleFace(owner, i) : null;
      if (occupied && card) {
        const img = document.createElement("img"); img.src = cardImg(card.face); img.alt = card.code;
        slot.appendChild(img); slot.classList.add("known");
      } else if (occupied) {
        const img = document.createElement("img"); img.src = cardImg("back"); img.alt = "card"; slot.appendChild(img);
      }
      if (attachClicks && occupied && isSelectable(owner, i, isMine, mode)) {
        slot.classList.add("selectable");
        slot.addEventListener("click", () => onSlotClick(owner, i));
      }
      if (mode === "match_center" && (view.interaction.targets || []).some((t) => t.owner === owner && t.slot === i)) {
        slot.classList.add("selected");
      }
      wrap.appendChild(slot);
    });
    return wrap;
  }

  function isSelectable(owner, slot, isMine, mode) {
    if (view.currentTurn !== youId && !(view.pendingPower && view.pendingPower.by === youId)) {
      // powers/keep/match are always by the acting player
    }
    switch (mode) {
      case "keep":
      case "match":
      case "peek_own":
        return isMine;
      case "peek_opp":
        return !isMine;
      case "match_center":
        return true; // match your own OR an opponent's card
      case "match_replacements":
        return isMine && !(view.interaction.targets || []).some((t) => t.owner === owner && t.slot === slot);
      case "blind_swap":
      case "king":
        return view.interaction.firstPick == null ? isMine : !isMine;
      default:
        return false;
    }
  }

  function onSlotClick(owner, slot) {
    const it = view.interaction; if (!it) return;
    const base = { code, user_id: youId };
    if (it.mode === "keep") { socket.emit("s4_keep", { ...base, slot }); view.interaction = null; }
    else if (it.mode === "match") { socket.emit("s4_match_own", { ...base, slot }); view.interaction = null; }
    else if (it.mode === "match_center") {
      const targets = it.targets || (it.targets = []);
      const at = targets.findIndex((t) => t.owner === owner && t.slot === slot);
      if (at >= 0) targets.splice(at, 1); else targets.push({ owner, slot });
    }
    else if (it.mode === "match_replacements") {
      const needed = it.targets.filter((t) => t.owner !== youId);
      if ((it.replacements || []).some((r) => r.from_slot === slot)) return;
      it.replacements.push({
        target_owner: needed[it.replacements.length].owner,
        target_slot: needed[it.replacements.length].slot,
        from_slot: slot,
      });
      if (it.replacements.length === needed.length) {
        socket.emit("s4_react_match", { ...base, targets: it.targets, replacements: it.replacements });
        view.interaction = null;
      }
    }
    else if (it.mode === "peek_own") { socket.emit("s4_power_peek_own", { ...base, slot }); view.interaction = null; }
    else if (it.mode === "peek_opp") { socket.emit("s4_power_peek_opp", { ...base, opp: owner, slot }); view.interaction = null; }
    else if (it.mode === "blind_swap" || it.mode === "king") {
      if (it.firstPick == null) { it.firstPick = { slot }; renderTable(); return; }
      const payload = { ...base, own_slot: it.firstPick.slot, opp: owner, opp_slot: slot };
      socket.emit(it.mode === "blind_swap" ? "s4_power_blind_swap" : "s4_power_king_look", payload);
      view.interaction = null;
    }
    renderTable();
  }

  function renderActions() {
    instrEl.textContent = ""; btnsEl.innerHTML = "";
    const myTurn = view.currentTurn === youId;
    const myPower = view.phase === "power" && view.pendingPower && view.pendingPower.by === youId;

    // King decision after a look
    if (myPower && view.kingLook) {
      instrEl.textContent = "King: swap these two cards?";
      addBtn("Swap", () => socket.emit("s4_power_king_decide", { code, user_id: youId, swap: true }));
      addBtn("Keep", () => socket.emit("s4_power_king_decide", { code, user_id: youId, swap: false }), true);
      return;
    }
    if (myPower) {
      const kind = view.interaction ? view.interaction.mode : "";
      const firstDone = view.interaction && view.interaction.firstPick != null;
      instrEl.textContent = ({
        peek_own: "Power: tap one of YOUR cards to peek.",
        peek_opp: "Power: tap an OPPONENT's card to peek.",
        blind_swap: firstDone ? "Now tap an OPPONENT's card to swap." : "Blind swap: tap one of YOUR cards.",
        king: firstDone ? "Now tap an OPPONENT's card to look." : "King: tap one of YOUR cards.",
      }[kind] || "Use your power.") + " (optional)";
      addBtn("Skip power", () => {
        view.interaction = null;
        socket.emit("s4_power_skip", { code, user_id: youId });
      }, true);
      return;
    }

    if (view.phase === "match" && view.match) {
      const m = view.match;
      const card = m.card ? `${m.card.code}${SUIT[m.card.suit] || ""}` : "";
      const iAmNext = m.next_player === youId;
      if (canMatchNow()) {
        const it = view.interaction;
        if (it && it.mode === "match_replacements") {
          const left = it.targets.filter((t) => t.owner !== youId).length - it.replacements.length;
          instrEl.textContent = `Choose ${left} of your cards to give in exchange.`;
        } else if (it && it.mode === "match_center") {
          const count = (it.targets || []).length;
          instrEl.textContent = `Select every ${card} to throw (${count} selected), then confirm. (${m.seconds_left}s)`;
          if (count) addBtn("Throw selected", () => submitMatchTargets(it.targets));
        } else {
          instrEl.textContent = `Match the ${card}! Select any of your or opponents' cards. (${m.seconds_left}s)`;
          addBtn("Select cards", () => { view.interaction = { mode: "match_center", targets: [] }; renderTable(); });
        }
        addBtn("Pass", () => { view.interaction = null; socket.emit("s4_match_pass", { code, user_id: youId }); }, true);
      } else {
        instrEl.textContent = `${nameOf(m.discarder)} discarded ${card}. Matching window… (${m.seconds_left}s)`;
      }
      // The next player may start their turn early, which ends the window.
      // (Not the Stop caller — their "turn" is the reveal, handled server-side.)
      if (iAmNext && view.stopCaller !== youId) {
        addBtn("Draw — start my turn", () => socket.emit("s4_draw", { code, user_id: youId }));
        if (view.firstOrbitComplete && !view.stopCaller) {
          addBtn("Stop", () => socket.emit("s4_stop", { code, user_id: youId }), true);
        }
      }
      return;
    }

    if (view.phase === "preview") {
      instrEl.textContent = youId === view.hostId
        ? "Players are memorising their first two cards. Start whenever everyone is ready."
        : "Memorise your first two cards — the host can start early.";
      if (youId === view.hostId) addBtn("Start play", () => socket.emit("s4_begin_play", { code, user_id: youId }));
      return;
    }

    if (!myTurn) {
      instrEl.textContent = "Waiting for " + nameOf(view.currentTurn) + "…";
      return;
    }

    if (view.phase === "draw") {
      instrEl.textContent = "Your turn — draw a card" + (canStop() ? ", or call Stop." : ".");
      addBtn("Draw", () => socket.emit("s4_draw", { code, user_id: youId }));
      if (canStop()) addBtn("Stop", () => socket.emit("s4_stop", { code, user_id: youId }), true);
      return;
    }

    // Safety net: if my private drawn card ever goes missing (dropped event),
    // re-enter the room once to resync instead of leaving zero clickable options.
    if (view.phase === "decide" && view.drawnBy === youId && !view.drawn) {
      instrEl.textContent = "Syncing your card…";
      if (view._resyncSig !== view._sig) { view._resyncSig = view._sig; enter(); }
      return;
    }

    if (view.phase === "decide" && view.drawnBy === youId && view.drawn) {
      const d = view.drawn;
      const it = view.interaction;
      if (it && it.mode === "discard_confirm") {
        instrEl.textContent = `Do you also want to match your own card with ${d.code}?`;
        addBtn("Yes, match own card", () => { view.interaction = { mode: "match", firstPick: null }; renderTable(); });
        addBtn("No, just discard", () => socket.emit("s4_discard", { code, user_id: youId }));
        addBtn("Cancel", () => { view.interaction = null; renderTable(); }, true);
        return;
      }
      if (it && (it.mode === "keep" || it.mode === "match")) {
        instrEl.textContent = it.mode === "keep"
          ? `Keep ${d.code}${SUIT[d.suit] || ""} — tap a slot to place it.`
          : `Match — tap the slot you think holds a ${d.code}.`;
        addBtn("Cancel", () => { view.interaction = null; renderTable(); }, true);
        return;
      }
      const powerNote = (d.rank >= 7) ? " (discard triggers power)" : "";
      instrEl.textContent = `You drew ${d.code}${SUIT[d.suit] || ""}. Keep, or discard${powerNote}.`;
      addBtn("Keep", () => { view.interaction = { mode: "keep", firstPick: null }; renderTable(); });
      addBtn("Discard", () => { view.interaction = { mode: "discard_confirm" }; renderTable(); });
      return;
    }

    instrEl.textContent = "Your turn…";
  }

  function canStop() {
    return view.firstOrbitComplete && !view.stopCaller && view.phase === "draw" && view.currentTurn === youId;
  }
  function submitMatchTargets(targets) {
    const opponentTargets = targets.filter((t) => t.owner !== youId);
    if (!opponentTargets.length) {
      socket.emit("s4_react_match", { code, user_id: youId, targets, replacements: [] });
      view.interaction = null;
      return;
    }
    view.interaction = { mode: "match_replacements", targets, replacements: [] };
    renderTable();
  }
  function addBtn(label, fn, ghost) {
    const b = document.createElement("button"); b.textContent = label;
    if (ghost) b.className = "ghost"; b.addEventListener("click", fn); btnsEl.appendChild(b);
  }

  function renderScoreboard() {
    if (!scoreList) return;
    scoreList.innerHTML = "";
    const PAL = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
    const exit = (view.settings && view.settings.exit_score) || 10;
    const sorted = [...view.players].filter((p) => !p.is_spectator)
      .sort((a, b) => (a.eliminated - b.eliminated) || (a.score - b.score));
    sorted.forEach((p) => {
      const li = document.createElement("li");
      if (p.user_id === view.currentTurn) li.classList.add("turn");
      if (p.eliminated) li.classList.add("out");

      const left = document.createElement("span"); left.className = "sb-name";
      const sw = document.createElement("span"); sw.className = "swatch";
      sw.style.background = PAL[(p.color || 0) % PAL.length];
      left.appendChild(sw);
      const dot = document.createElement("span"); dot.className = "dot" + (p.connected ? " on" : "");
      left.appendChild(dot);
      if (p.user_id === view.hostId) {
        const c = document.createElement("span"); c.className = "host-crown"; c.textContent = "♛"; c.title = "Host";
        left.appendChild(c);
      }
      const text = document.createElement("span"); text.className = "sb-text";
      text.textContent = window.SS.shortName(p.name);
      left.appendChild(text);
      if (p.user_id === youId) { const y = document.createElement("span"); y.className = "sb-you"; y.textContent = "you"; left.appendChild(y); }

      const score = document.createElement("span"); score.className = "sb-score";
      score.textContent = p.score;

      li.appendChild(left); li.appendChild(score);

      // Progress toward exit_score (elimination). A negative score = doing well = empty bar.
      const pct = Math.max(0, Math.min(1, (p.score || 0) / exit));
      const bar = document.createElement("div"); bar.className = "sb-bar";
      const fill = document.createElement("div"); fill.className = "sb-bar-fill";
      fill.style.setProperty("--bar-pct", (pct * 100).toFixed(1) + "%");
      fill.style.setProperty("--bar-raw", pct.toFixed(4));
      bar.appendChild(fill); li.appendChild(bar);

      scoreList.appendChild(li);
    });

    // Spectators: visible to everyone; the host can admit them for next round.
    const specs = view.players.filter((p) => p.is_spectator);
    if (specs.length) {
      const head = document.createElement("li");
      head.textContent = "Watching";
      head.style.cssText = "margin-top:.6rem;opacity:.6;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em";
      scoreList.appendChild(head);
      specs.forEach((p) => {
        const li = document.createElement("li");
        li.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:.4rem";
        const nm = document.createElement("span");
        nm.textContent = "👁 " + window.SS.shortName(p.name) + (p.user_id === youId ? " (you)" : "");
        li.appendChild(nm);
        if (p.pending_join) {
          const tag = document.createElement("span");
          tag.textContent = "Joining next";
          tag.style.cssText = "font-size:.7rem;opacity:.8";
          li.appendChild(tag);
        } else if (youId === view.hostId) {
          const btn = document.createElement("button");
          btn.textContent = "+";
          btn.title = "Admit " + p.name + " to the next round";
          btn.style.cssText = "width:22px;height:22px;border:none;border-radius:4px;cursor:pointer;" +
            "background:rgba(255,255,255,.15);color:inherit;font-size:16px;line-height:1";
          btn.addEventListener("click", () => window.SS.openSpectatorModal(p.user_id, p.name));
          li.appendChild(btn);
        }
        scoreList.appendChild(li);
      });
    }
  }

  // ---- spectator admit modal (host) ---- (shared: static/js/core/chrome.js)

  function setPileCard(el, card) {
    let img = el.querySelector("img.pile-face");
    if (!img) { img = document.createElement("img"); img.className = "pile-face"; el.insertBefore(img, el.firstChild); }
    img.src = cardImg(card.face); img.alt = card.code;
  }
  function clearPileCard(el) { const img = el.querySelector("img.pile-face"); if (img) img.remove(); }

  // ================= round end =================
  function showRoundEnd(d) {
    const title = $("roundend-title"), sub = $("roundend-sub"), body = $("roundend-body"), footer = $("roundend-footer");
    const winners = d.winners || [];
    const winNames = winners.map(nameOf).join(", ");

    if (d.game_over) {
      title.textContent = d.winner ? "🏆 " + nameOf(d.winner) + " wins the game!" : "Game over — it's a tie!";
    } else if (d.caller && d.caller_won) {
      title.textContent = nameOf(d.caller) + " called Stop and won!";
    } else if (d.caller) {
      title.textContent = nameOf(d.caller) + " called Stop and got caught!";
    } else if (winners.length > 1) {
      title.textContent = winNames + " tie for the lowest hand";
    } else if (winners.length === 1) {
      title.textContent = winNames + " has the lowest hand";
    } else {
      title.textContent = "Round over";
    }

    let subtext = "";
    if (d.caller) {
      subtext = d.caller_won
        ? nameOf(d.caller) + " had the lowest hand — everyone else takes +" + stopLossPts() + "."
        : nameOf(d.caller) + " was caught (+" + penaltyPts() + ") — lowest hand: " + (winNames || "—") + ".";
    } else if (winners.length) {
      subtext = "No Stop call — only a winning Stop scores minus points.";
    }
    if ((d.newly_eliminated || []).length) {
      subtext += (subtext ? "  " : "") + "Out: " + d.newly_eliminated.map(nameOf).join(", ") + ".";
    }
    if (!d.game_over) subtext += (subtext ? "  " : "") + `Round ${d.round_number}/${d.rounds}.`;
    sub.textContent = subtext;

    // Table: name | revealed cards | hand total | round Δ | cumulative
    const totals = d.totals || {}, deltas = d.deltas || {};
    const cumById = {}; (d.players || []).forEach((p) => { cumById[p.user_id] = p.score; });
    let html = '<table style="width:100%;border-collapse:collapse;font-size:.85rem">';
    html += '<tr style="opacity:.6"><td>Player</td><td>Cards</td><td style="text-align:right">Hand</td>' +
            '<td style="text-align:right">Δ</td><td style="text-align:right">Total</td></tr>';
    Object.keys(d.reveal || {}).sort((a, b) => (totals[a] || 0) - (totals[b] || 0)).forEach((uid) => {
      const cards = (d.reveal[uid] || []).map((c) => c ? `${c.code}${SUIT[c.suit] || ""}` : "—").join(" ");
      const dv = deltas[uid];
      const dstr = dv == null ? "" : (dv > 0 ? "+" + dv : "" + dv);
      const win = winners.indexOf(uid) !== -1;
      html += `<tr${win ? ' style="font-weight:600;color:#8f6"' : ''}>` +
        `<td style="padding:.25rem .4rem">${escapeHtml(nameOf(uid))}</td>` +
        `<td style="padding:.25rem .4rem;opacity:.8">${cards}</td>` +
        `<td style="padding:.25rem .4rem;text-align:right">${totals[uid] != null ? totals[uid] : ""}</td>` +
        `<td style="padding:.25rem .4rem;text-align:right">${dstr}</td>` +
        `<td style="padding:.25rem .4rem;text-align:right">${cumById[uid] != null ? cumById[uid] : ""}</td></tr>`;
    });
    html += "</table>";
    body.innerHTML = html;

    footer.innerHTML = "";
    if (youId === view.hostId) {
      const b = document.createElement("button"); b.className = "btn-primary";
      if (d.game_over) {
        b.textContent = "New game";
        b.addEventListener("click", () => { socket.emit("rematch", { code, user_id: youId }); closeModal("roundend-modal"); });
      } else {
        b.textContent = "Next round";
        b.addEventListener("click", () => { socket.emit("s4_next_round", { code, user_id: youId }); closeModal("roundend-modal"); });
      }
      footer.appendChild(b);
    } else {
      const p = document.createElement("p"); p.className = "meta";
      p.textContent = d.game_over ? "Waiting for the host to start a new game…" : "Waiting for the host…";
      footer.appendChild(p);
    }
    if (d.game_over) {
      const home = document.createElement("button"); home.className = "btn-ghost";
      home.textContent = "Home";
      home.addEventListener("click", () => { window.location.href = "/"; });
      footer.appendChild(home);
    }
    openModal("roundend-modal");
  }

  function penaltyPts() {
    return (view.settings && view.settings.penalty_score != null) ? view.settings.penalty_score : 4;
  }
  function stopLossPts() {
    return (view.settings && view.settings.stop_loss_score != null) ? view.settings.stop_loss_score : 2;
  }

  // ================= chrome: timer, rules, reactions =================
  function syncTimer() {
    const el = $("turn-timer"); if (!el) return;
    if (view.state !== "IN_TURN") { el.style.display = "none"; return; }
    // During the preview window the chip counts down the memorize time.
    if (view.previewLeft > 0) {
      el.style.display = "inline-block";
      el.textContent = "👁 memorize " + view.previewLeft + "s";
      el.classList.add("low");
      return;
    }
    if (view.secondsLeft == null) { el.style.display = "none"; return; }
    el.style.display = "inline-block";
    el.textContent = "⏱ " + Math.max(0, view.secondsLeft) + "s";
    el.classList.toggle("low", view.secondsLeft <= 10);
  }
  function syncRoundChip() {
    if (!roundChip) return;
    if (view.state === "IN_TURN" || view.state === "ROUND_END") {
      roundChip.style.display = "inline-block"; roundChip.textContent = "Round " + (view.roundNumber || 1);
    } else roundChip.style.display = "none";
  }
  setInterval(() => {
    if (view.state === "IN_TURN" && typeof view.secondsLeft === "number" && view.secondsLeft > 0) {
      view.secondsLeft -= 1; syncTimer();
    }
    if (view.phase === "match" && view.match && view.match.seconds_left > 0) {
      view.match.seconds_left -= 1;
      if (view.state === "IN_TURN") renderActions();
    }
    // Preview countdown: when it hits 0, hide the previewed cards (memory time).
    if (view.state === "IN_TURN" && view.previewLeft > 0) {
      view.previewLeft -= 1;
      syncTimer();
      if (view.previewLeft <= 0) renderTable();
    }
    // Expire peek/King flashes and re-render when any lapse.
    var now = Date.now(), changed = false;
    for (var k in view.flashes) {
      if (view.flashes[k].until <= now) { delete view.flashes[k]; changed = true; }
    }
    if (changed && view.state === "IN_TURN") renderTable();
  }, 1000);

  function openModal(id) { const m = $(id); if (m) m.classList.add("open"); }
  function closeModal(id) { const m = $(id); if (m) m.classList.remove("open"); }

  // ---- table theme (shared impl: static/js/core/themes.js) ----
  function syncTableTheme() {
    if (window.SS.themes) window.SS.themes.apply(view.tableTheme || "default");
  }
  function syncThemeSelectorVisibility() {
    if (window.SS.themes) window.SS.themes.syncVisibility(view.hostId === youId);
  }
  socket.on("table_theme_updated", (d) => { view.tableTheme = d.theme; syncTableTheme(); });

  // Rules modal, reactions, mute, copy — all shared: static/js/core/*.js

  function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
})();
