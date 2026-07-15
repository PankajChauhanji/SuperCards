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
    roundNumber: 0, settings: null, secondsLeft: null,
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
    sync();
  });
  socket.on("player_list", (d) => {
    view.hostId = d.host_id; view.players = d.players;
    if (view.state !== "IN_TURN") renderLobby();
  });
  socket.on("room_reset", (d) => {
    view.state = "LOBBY"; view.hostId = d.host_id; view.players = d.players;
    if (d.settings) view.settings = d.settings;
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
    showToast((d.user_id === youId ? "You" : d.name) + " ran out of time");
  });
  socket.on("reaction", (d) => floatReaction(d.emoji));

  function applyState(d) {
    if (d.state) view.state = d.state;
    if (d.players) view.players = d.players;
    if (d.host_id) view.hostId = d.host_id;
    if (d.settings) view.settings = d.settings;
    view.currentTurn = d.current_turn;
    view.turnOrder = d.turn_order || [];
    view.deckCount = d.deck_count;
    view.drawn = d.drawn; view.drawnBy = d.drawn_by;
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
    ["exit_score", "Exit score (out)"], ["win_score", "Win score"],
    ["loss_score", "Loss score"], ["penalty_score", "Caught-Stop penalty"],
  ];
  function renderLobbySettings() {
    if (!lobbySettings) return;
    const s = view.settings || {};
    if (youId === view.hostId) {
      let h = '<div style="font-size:.8rem;opacity:.7;margin-bottom:.3rem">Game settings (host)</div>' +
        '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:.35rem;font-size:.8rem">';
      S4_FIELDS.forEach(([k, label]) => {
        h += `<label style="display:flex;justify-content:space-between;gap:.4rem;align-items:center">` +
          `<span>${label}</span><input type="number" data-key="${k}" value="${s[k] != null ? s[k] : ""}" style="width:60px" /></label>`;
      });
      h += '</div><button class="btn-ghost" id="s4-save-settings" style="margin-top:.5rem;width:auto;padding:.3rem .8rem">Save settings</button>';
      lobbySettings.innerHTML = h;
      const save = $("s4-save-settings");
      if (save) save.addEventListener("click", () => {
        const out = {};
        lobbySettings.querySelectorAll("input[data-key]").forEach((el) => {
          if (el.value !== "") out[el.dataset.key] = parseInt(el.value, 10);
        });
        socket.emit("update_settings", { code, user_id: youId, settings: out });
        showToast("Settings saved");
      });
    } else {
      lobbySettings.innerHTML = '<div style="font-size:.8rem;opacity:.75">' +
        `Turn ${s.turn_timer || 30}s · Match ${s.match_window != null ? s.match_window : 3}s · ` +
        `Rounds ${s.rounds || 5} · Out at ${s.exit_score || 10} · ` +
        `Win ${s.win_score != null ? s.win_score : -3} / Loss +${s.loss_score != null ? s.loss_score : 1} / ` +
        `Caught +${s.penalty_score != null ? s.penalty_score : 3}</div>`;
    }
  }

  function badge(text, cls) {
    const b = document.createElement("span"); b.className = "badge " + cls; b.textContent = text; return b;
  }

  // ================= table =================
  function canMatchNow() {
    return view.phase === "match" && view.match &&
      view.match.discarder !== youId && !(view.match.attempted || []).includes(youId);
  }

  function armAutoInteraction() {
    // During a match window I can attempt, arm the "match_center" targeting mode.
    if (canMatchNow()) {
      if (!view.interaction || view.interaction.mode !== "match_center") {
        view.interaction = { mode: "match_center", firstPick: null };
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
      if (attachClicks && occupied && isSelectable(owner, isMine, mode)) {
        slot.classList.add("selectable");
        slot.addEventListener("click", () => onSlotClick(owner, i));
      }
      wrap.appendChild(slot);
    });
    return wrap;
  }

  function isSelectable(owner, isMine, mode) {
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
      if (owner === youId) socket.emit("s4_match_center_own", { ...base, slot });
      else socket.emit("s4_match_center_opp", { ...base, target: owner, slot });
      view.interaction = null;
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
      instrEl.textContent = {
        peek_own: "Power: tap one of YOUR cards to peek.",
        peek_opp: "Power: tap an OPPONENT's card to peek.",
        blind_swap: firstDone ? "Now tap an OPPONENT's card to swap." : "Blind swap: tap one of YOUR cards.",
        king: firstDone ? "Now tap an OPPONENT's card to look." : "King: tap one of YOUR cards.",
      }[kind] || "Use your power.";
      return;
    }

    if (view.phase === "match" && view.match) {
      const m = view.match;
      const card = m.card ? `${m.card.code}${SUIT[m.card.suit] || ""}` : "";
      if (canMatchNow()) {
        instrEl.textContent = `Match the ${card}! Tap YOUR card or an OPPONENT's — or pass. (${m.seconds_left}s)`;
        addBtn("Pass", () => { view.interaction = null; socket.emit("s4_match_pass", { code, user_id: youId }); }, true);
      } else {
        instrEl.textContent = `${nameOf(m.discarder)} discarded ${card}. Matching window… (${m.seconds_left}s)`;
      }
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

    if (view.phase === "decide" && view.drawnBy === youId && view.drawn) {
      const d = view.drawn;
      const it = view.interaction;
      if (it && (it.mode === "keep" || it.mode === "match")) {
        instrEl.textContent = it.mode === "keep"
          ? `Keep ${d.code}${SUIT[d.suit] || ""} — tap a slot to place it.`
          : `Match — tap the slot you think holds a ${d.code}.`;
        addBtn("Cancel", () => { view.interaction = null; renderTable(); }, true);
        return;
      }
      const powerNote = (d.rank >= 7) ? " (discarding triggers its power)" : "";
      instrEl.textContent = `You drew ${d.code}${SUIT[d.suit] || ""}. Keep, discard${powerNote}, or match.`;
      addBtn("Keep", () => { view.interaction = { mode: "keep", firstPick: null }; renderTable(); });
      addBtn("Discard", () => socket.emit("s4_discard", { code, user_id: youId }));
      addBtn("Match", () => { view.interaction = { mode: "match", firstPick: null }; renderTable(); }, true);
      return;
    }

    instrEl.textContent = "Your turn…";
  }

  function canStop() {
    return view.firstOrbitComplete && !view.stopCaller && view.phase === "draw" && view.currentTurn === youId;
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
  }

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
    } else if (winners.length > 1) {
      title.textContent = winNames + " tie for the round";
    } else if (winners.length === 1) {
      title.textContent = winNames + " wins the round!";
    } else {
      title.textContent = "Round over";
    }

    let subtext = "";
    if (d.caller) {
      subtext = d.caller_won
        ? nameOf(d.caller) + " called Stop and won."
        : nameOf(d.caller) + " called Stop but was caught (+" + penaltyPts() + ").";
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
    openModal("roundend-modal");
  }

  function penaltyPts() {
    return (view.settings && view.settings.penalty_score != null) ? view.settings.penalty_score : 3;
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
  document.querySelectorAll(".lang-btn").forEach((b) => b.addEventListener("click", (e) => loadRules(e.target.dataset.lang)));

  // Reactions (shared social channel)
  const fab = $("reaction-fab"), panel = $("reaction-panel");
  if (fab && panel) {
    fab.addEventListener("click", () => { panel.hidden = !panel.hidden; });
    document.querySelectorAll(".rx").forEach((b) => b.addEventListener("click", () => {
      socket.emit("reaction", { code, user_id: youId, emoji: b.dataset.e }); panel.hidden = true;
    }));
  }
  function floatReaction(emoji) {
    const layer = $("reactions-layer"); if (!layer) return;
    const el = document.createElement("div"); el.className = "reaction-float"; el.textContent = emoji;
    el.style.left = (10 + Math.floor(Math.random() * 80)) + "%";
    layer.appendChild(el); setTimeout(() => el.remove(), 2600);
  }

  // Mute (best-effort)
  if ($("mute-btn") && window.SS.sound && window.SS.sound.toggleMute) {
    $("mute-btn").addEventListener("click", () => {
      const muted = window.SS.sound.toggleMute();
      $("mute-btn").textContent = muted ? "🔇" : "🔊";
    });
  }
  // Copy code
  if ($("copy-btn")) $("copy-btn").addEventListener("click", () => {
    navigator.clipboard && navigator.clipboard.writeText(location.href);
    showToast("Room link copied");
  });

  function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
})();
