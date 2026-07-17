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
    if (view.state === "IN_TURN") renderTable(); else renderLobby();
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
    if (view.state !== "IN_TURN") renderLobby();
  });
  socket.on("kicked", () => { alert("You were removed by the host."); window.location.href = "/"; });

  // ---- gameplay events ----
  socket.on("round_start", (d) => {
    applyState(d); closeModal("roundend-modal");
    view.interaction = null; view.kingLook = null; sync();
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
    showToast(`Peeked ${who}: ${d.card.code}${SUIT[d.card.suit] || ""}`);
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
    showToast(d.removed
      ? "You missed too many turns — you're spectating now. Ask the host to admit you back."
      : "You ran out of time — your turn was auto-played", 3200);
  });
  socket.on("toast", (d) => showToast(d.message, d.ms));
  socket.on("reaction", (d) => floatReaction(d.emoji, d.name));

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
    if (inRound) renderTable(); else renderLobby();
    syncRoundChip();
    syncThemeSelectorVisibility();
  }

  // ================= lobby =================
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  function renderLobby() {
    rosterEl.innerHTML = "";
    view.players.forEach((p) => {
      const li = document.createElement("li");
      const who = document.createElement("div"); who.className = "who";
      const sw = document.createElement("span"); sw.className = "swatch";
      sw.style.background = PALETTE[(p.color || 0) % PALETTE.length];
      const dot = document.createElement("span"); dot.className = "dot" + (p.connected ? " on" : "");
      const nm = document.createElement("span"); nm.className = "name"; nm.textContent = p.name;
      who.append(sw, dot, nm);
      const tags = document.createElement("div"); tags.className = "roster-tags";
      if (p.user_id === view.hostId) tags.appendChild(badge("Host", "host"));
      if (p.user_id === youId) tags.appendChild(badge("You", "you"));
      if (p.is_spectator) tags.appendChild(badge(p.pending_join ? "Joining next" : "Spectator", "spec"));
      if (youId === view.hostId && p.user_id !== youId) {
        const kick = document.createElement("button"); kick.className = "kick-btn";
        kick.textContent = "✕"; kick.title = "Remove " + p.name;
        kick.addEventListener("click", () => {
          if (confirm("Remove " + p.name + "?")) socket.emit("kick_player", { code, user_id: youId, target: p.user_id });
        });
        tags.appendChild(kick);
      }
      li.append(who, tags); rosterEl.appendChild(li);
    });

    renderLobbySettings();

    const n = view.players.length;
    metaEl.textContent = n + (n === 1 ? " player" : " players") + " in the room";

    startRow.innerHTML = "";
    if (youId === view.hostId) {
      const btn = document.createElement("button");
      btn.className = "btn-primary"; btn.textContent = "Start game";
      btn.addEventListener("click", () => socket.emit("start_game", { code, user_id: youId }));
      startRow.appendChild(btn);
    } else {
      const p = document.createElement("p"); p.className = "meta";
      p.textContent = "Waiting for the host to start…"; startRow.appendChild(p);
    }
  }
  const S4_FIELDS = [
    ["turn_timer", "Turn time (s)"], ["match_window", "Match window (s)"],
    ["preview_seconds", "Preview (s)"], ["rounds", "Rounds"],
    ["exit_score", "Exit score (out)"], ["win_score", "Stop win (caller)"],
    ["stop_loss_score", "Others on won Stop"], ["loss_score", "Loss (other rounds)"],
    ["penalty_score", "Caught-Stop penalty"], ["timeout_limit", "Missed turns (out)"],
  ];
  function renderLobbySettings() {
    if (!lobbySettings) return;
    const s = view.settings || {};
    const isHost = youId === view.hostId;
    const mode = isHost ? "host" : "guest";
    // Build the panel once per role; later renders only sync the values, so the
    // host's in-progress edits are never wiped by a roster refresh.
    if (lobbySettings.dataset.mode !== mode) {
      lobbySettings.dataset.mode = mode;
      let h = '<div style="font-size:.8rem;opacity:.7;margin-bottom:.3rem">Game settings' +
        (isHost ? "" : " (set by the host)") + "</div>" +
        '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:.35rem;font-size:.8rem">';
      S4_FIELDS.forEach(([k, label]) => {
        h += '<label style="display:flex;justify-content:space-between;gap:.4rem;align-items:center">' +
          `<span>${label}</span>` +
          (isHost
            ? `<input type="number" data-key="${k}" style="width:60px" />`
            : `<span data-key="${k}" style="font-weight:600"></span>`) +
          "</label>";
      });
      h += "</div>";
      if (isHost) {
        h += '<button class="btn-ghost" id="s4-save-settings" style="margin-top:.5rem;width:auto;padding:.3rem .8rem">Save settings</button>';
      }
      lobbySettings.innerHTML = h;
      if (isHost) {
        lobbySettings.querySelectorAll("input[data-key]").forEach((el) => {
          el.addEventListener("input", () => { el.dataset.dirty = "1"; });
        });
        $("s4-save-settings").addEventListener("click", () => {
          const out = {};
          lobbySettings.querySelectorAll("input[data-key]").forEach((el) => {
            if (el.value !== "") out[el.dataset.key] = parseInt(el.value, 10);
            delete el.dataset.dirty;
          });
          socket.emit("update_settings", { code, user_id: youId, settings: out });
          showToast("Settings saved");
        });
      }
    }
    S4_FIELDS.forEach(([k]) => {
      const el = lobbySettings.querySelector(`[data-key="${k}"]`);
      if (!el) return;
      const val = s[k] != null ? String(s[k]) : "";
      if (el.tagName === "INPUT") {
        if (el !== document.activeElement && !el.dataset.dirty) el.value = val;
      } else {
        el.textContent = val || "—";
      }
    });
  }

  function badge(text, cls) {
    const b = document.createElement("span"); b.className = "badge " + cls; b.textContent = text; return b;
  }

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
    myNameEl.textContent = (me ? me.name : "You") + (view.currentTurn === youId ? "  • your turn" : "");

    // opponents
    oppEl.innerHTML = "";
    view.players.filter((p) => p.user_id !== youId && !p.is_spectator).forEach((p) => {
      const seat = document.createElement("div");
      seat.className = "s4-seat" + (view.currentTurn === p.user_id ? " turn" : "");
      const head = document.createElement("div"); head.className = "seat-name";
      head.innerHTML = `<span>${escapeHtml(p.name)}${p.user_id === view.stopCaller ? " ✋" : ""}</span>` +
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
    const sorted = [...view.players].filter((p) => !p.is_spectator).sort((a, b) => a.score - b.score);
    let crowned = false;
    sorted.forEach((p) => {
      const li = document.createElement("li");
      const out = p.eliminated;
      let tag = "";
      if (out) tag = " 💀 OUT";
      else if (!crowned) { tag = " 👑"; crowned = true; }  // lowest active leads
      li.innerHTML = `<span>${escapeHtml(p.name)}</span><span>${p.score}${tag}</span>`;
      li.style.display = "flex"; li.style.justifyContent = "space-between";
      if (out) li.style.opacity = "0.45";
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
        nm.textContent = "👁 " + p.name + (p.user_id === youId ? " (you)" : "");
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
          btn.addEventListener("click", () => openSpectatorModal(p.user_id, p.name));
          li.appendChild(btn);
        }
        scoreList.appendChild(li);
      });
    }
  }

  // ---- spectator admit modal (host) ----
  let admitTargetId = null;
  function openSpectatorModal(targetId, name) {
    const m = $("spectator-modal"); if (!m) return;
    admitTargetId = targetId;
    $("admit-name").textContent = name;
    $("admit-penalty").value = "0";
    m.classList.add("open");
  }
  if ($("admit-cancel")) $("admit-cancel").addEventListener("click", () => {
    closeModal("spectator-modal"); admitTargetId = null;
  });
  if ($("admit-confirm")) $("admit-confirm").addEventListener("click", () => {
    if (admitTargetId) {
      const penalty = parseInt($("admit-penalty").value, 10) || 0;
      socket.emit("admit_spectator", { code, user_id: youId, target_id: admitTargetId, penalty: penalty });
    }
    closeModal("spectator-modal"); admitTargetId = null;
  });

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

  // Rules modal (per-game content)
  const rulesCache = {};
  function loadRules(lang) {
    const c = $("rules-content-container"), t = $("rules-title");
    document.querySelectorAll(".lang-btn").forEach((b) => {
      const on = b.dataset.lang === lang;
      b.style.background = on ? "#6706ce" : "transparent"; b.style.color = on ? "#fff" : "inherit";
    });
    if (t) t.textContent = lang === "hi" ? "📖 नियम" : "📖 Rule Book";
    if (rulesCache[lang]) { c.innerHTML = rulesCache[lang]; return; }
    c.innerHTML = "<p>Loading rules…</p>";
    fetch(`/static/rules/${gameType}/${lang}.html`)
      .then((r) => { if (!r.ok) throw new Error("nope"); return r.text(); })
      .then((h) => { rulesCache[lang] = h; c.innerHTML = h; })
      .catch(() => { c.innerHTML = "<p>Rules coming soon.</p>"; });
  }
  if ($("rules-btn")) $("rules-btn").addEventListener("click", () => { openModal("rules-modal"); loadRules("en"); });
  if ($("rules-close")) $("rules-close").addEventListener("click", () => closeModal("rules-modal"));
  const rulesModal = $("rules-modal");
  if (rulesModal) rulesModal.addEventListener("click", (e) => {
    if (e.target === rulesModal) closeModal("rules-modal");
  });
  document.querySelectorAll(".lang-btn").forEach((b) => b.addEventListener("click", (e) => loadRules(e.target.dataset.lang)));

  // Reactions (shared social channel) — same UX as the Super Seven bundle.
  const fab = $("reaction-fab"), panel = $("reaction-panel");
  const rxRecentContainer = $("rx-recent-container"), rxRecentGrid = $("rx-recent-grid");
  function getRecentReactions() {
    try { return JSON.parse(localStorage.getItem("super_seven_recent_rx")) || []; }
    catch (e) { return []; }
  }
  function sendReaction(emoji) {
    // Panel stays open — rapid repeat clicks spam reactions, same as Super Seven.
    socket.emit("reaction", { code, user_id: youId, emoji });
    let recent = getRecentReactions();
    recent = recent.filter((e) => e !== emoji);
    recent.unshift(emoji);
    if (recent.length > 5) recent.pop();
    localStorage.setItem("super_seven_recent_rx", JSON.stringify(recent));
    updateRecentGrid();
  }
  function updateRecentGrid() {
    if (!rxRecentContainer || !rxRecentGrid) return;
    const recent = getRecentReactions();
    if (fab && recent.length) fab.textContent = recent[0];
    if (!recent.length) { rxRecentContainer.style.display = "none"; return; }
    rxRecentContainer.style.display = "flex";
    rxRecentGrid.innerHTML = "";
    recent.forEach((emoji) => {
      const btn = document.createElement("button");
      btn.className = "rx"; btn.dataset.e = emoji; btn.title = emoji; btn.textContent = emoji;
      btn.addEventListener("click", () => sendReaction(emoji));
      rxRecentGrid.appendChild(btn);
    });
  }
  if (fab && panel) {
    // Single click toggles the panel; rapid double-click fires the last-used
    // reaction immediately (same feel as Super Seven).
    let lastFabClick = 0, fabClickTimeout = null;
    fab.addEventListener("click", () => {
      const now = Date.now();
      const rapid = now - lastFabClick < 300;
      lastFabClick = now;
      if (rapid) {
        if (fabClickTimeout) { clearTimeout(fabClickTimeout); fabClickTimeout = null; }
        sendReaction(getRecentReactions()[0] || "🤡");
      } else {
        fabClickTimeout = setTimeout(() => {
          fabClickTimeout = null;
          panel.hidden = !panel.hidden;
          if (!panel.hidden) updateRecentGrid();
        }, 220);
      }
    });
    document.querySelectorAll("#rx-main-grid .rx").forEach((b) =>
      b.addEventListener("click", () => sendReaction(b.dataset.e)));
    document.addEventListener("click", (e) => {
      const dock = $("reaction-dock");
      if (dock && !dock.contains(e.target)) panel.hidden = true;
    });
    updateRecentGrid();
  }
  function floatReaction(emoji, name) {
    const layer = $("reactions-layer"); if (!layer) return;
    const el = document.createElement("div"); el.className = "rx-float"; el.textContent = emoji;
    if (name) {
      const tag = document.createElement("span"); tag.className = "rx-name"; tag.textContent = name;
      el.appendChild(tag);
    }
    el.style.left = (10 + Math.random() * 70) + "%";
    el.style.setProperty("--drift", (Math.random() * 60 - 30) + "px");
    layer.appendChild(el); setTimeout(() => el.remove(), 3900);
  }

  // ---- table themes (same shared selector + CSS as Super Seven) ----
  const THEME_MAP = {
    default: { icon: "🟢", name: "Default" },
    casino: { icon: "🎰", name: "Casino Felt" },
    cyberpunk: { icon: "👾", name: "Cyberpunk" },
    marble: { icon: "🏛️", name: "Marble Luxury" },
    red_casino: { icon: "🍒", name: "Red Casino" },
  };
  function syncTableTheme() {
    const theme = view.tableTheme || "default";
    Object.keys(THEME_MAP).forEach((t) => document.body.classList.remove("theme-" + t));
    if (theme !== "default") document.body.classList.add("theme-" + theme);
    const icon = $("current-theme-icon"), name = $("current-theme-name");
    if (icon && name) {
      const active = THEME_MAP[theme] || THEME_MAP.default;
      icon.textContent = active.icon; name.textContent = active.name;
    }
  }
  function syncThemeSelectorVisibility() {
    const wrap = $("theme-select-wrap");
    if (wrap) wrap.style.display = view.hostId === youId ? "inline-flex" : "none";
  }
  const themeBtn = $("theme-select-btn"), themeDropdown = $("theme-dropdown");
  if (themeBtn && themeDropdown) {
    themeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const hidden = themeDropdown.hasAttribute("hidden");
      if (hidden) { themeDropdown.removeAttribute("hidden"); themeDropdown.setAttribute("aria-hidden", "false"); }
      else { themeDropdown.setAttribute("hidden", ""); themeDropdown.setAttribute("aria-hidden", "true"); }
    });
    themeDropdown.querySelectorAll(".theme-opt").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        socket.emit("change_table_theme", { code, user_id: youId, theme: btn.dataset.t });
        themeDropdown.setAttribute("hidden", ""); themeDropdown.setAttribute("aria-hidden", "true");
      });
    });
    document.addEventListener("click", () => {
      themeDropdown.setAttribute("hidden", ""); themeDropdown.setAttribute("aria-hidden", "true");
    });
  }
  socket.on("table_theme_updated", (d) => { view.tableTheme = d.theme; syncTableTheme(); });

  // Mute (best-effort)
  if ($("mute-btn") && window.SS.sound && window.SS.sound.toggleMute) {
    $("mute-btn").addEventListener("click", () => {
      const muted = window.SS.sound.toggleMute();
      $("mute-btn").textContent = muted ? "🔇" : "🔊";
    });
  }
  // Copy code
  if ($("copy-btn")) $("copy-btn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code);
      showToast("Room code copied");
    } catch (_) {
      showToast("Code: " + code);
    }
  });

  function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
})();
