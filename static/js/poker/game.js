// Poker game page controller — the client's view of the room, server events,
// the betting bar, the round summary and the podium.
//
// The server is the only authority (sockets/gameplay/poker.py). This file never
// decides what is legal: it renders the `actions` the server sends for whoever
// is on turn, and sends back one `poker_action`. Everything shared — lobby,
// seats, themes, reactions, rules, the winner podium — comes from core/.
(function () {
  const SS = window.SS;
  const { socket, showToast } = SS;
  const C = SS.pokerChips;
  const FX = SS.pokerFx;

  const code = window.SS_ROOM_CODE;
  const youId = window.Identity.userId();

  const view = {
    you: youId,
    hostId: null,
    state: "LOBBY",
    players: [],
    seats: [],
    currentTurn: null,
    board: [],
    pots: [],
    potTotal: 0,
    hand: [],
    handRound: 0,       // which round `hand` belongs to (never show last round's cards)
    handName: null,     // your best hand so far — sent privately, only with hand hints on
    handRank: null,     // its row in the rankings card (0 = Royal Flush ... 9 = High Card)
    roundNumber: 0,
    roundsTotal: 0,
    blinds: null,
    button: null,
    sbId: null,
    bbId: null,
    street: null,
    phase: null,
    actions: null,
    revealed: {},
    winBest: null,      // Set of card ids in the winning five, at round end
    winners: null,      // Set of winning user ids, at round end
    potSwept: false,    // the payout animation has carried the pot away
    secondsLeft: null,
    settings: null,
    tableTheme: "casino",
  };
  SS.view = view;

  // Betting-bar state, declared up front because applyState() resets it.
  let pending = false;   // an action is in flight; wait for the server's answer
  let raiseTo = 0;
  let raiseKey = null;   // resets the chosen amount when the betting context changes
  let preAction = null;  // "checkfold" | "check" — chosen before your turn
  let preKey = null;     // round|street the pre-action was chosen for
  let revealTimer = null;
  let podiumShown = false;   // the game-end podium is up (or its payout is running)

  const SUIT = { S: "♠", H: "♥", D: "♦", C: "♣" };
  const cardText = (c) => c.code + (SUIT[c.suit] || c.suit);

  const playerOf = (uid) => view.players.find((p) => p.user_id === uid) || null;
  const nameOf = (uid) => (uid === youId ? "You" : ((playerOf(uid) || {}).name || "Someone"));
  const colorOf = (uid) => { const p = playerOf(uid); return p ? p.color : -1; };
  const isHost = () => view.hostId === youId;
  // "You fold" / "Ben folds".
  const verb = (uid, base) => (uid === youId ? base : base + "s");
  const bb = () => (view.blinds && view.blinds.bb) || 1;

  const lobbyView = document.getElementById("lobby-view");
  const tableView = document.getElementById("table-view");
  document.getElementById("room-code").textContent = code;

  // ---- attach / reconnect ----
  function enter() {
    socket.emit("enter_room", { code, name: window.Identity.name(), user_id: youId });
  }
  socket.on("connect", enter);
  if (SS.onResync) SS.onResync(enter);
  if (SS.onRepaint) SS.onRepaint(() => {
    if (FX) FX.preload();     // a deck switch needs the other deck's images
    if (tableView.style.display !== "none") { Table.render(view); renderActions(); }
  });
  if (socket.connected) enter();

  // ---- roster / lobby events ----
  socket.on("room_joined", (data) => {
    view.hostId = data.host_id;
    view.state = data.state;
    view.players = data.players;
    if (data.settings) view.settings = data.settings;
    view.tableTheme = data.table_theme || "casino";
    sync();
  });

  socket.on("player_list", (data) => {
    view.hostId = data.host_id;
    view.players = data.players;
    sync();
  });

  socket.on("settings_updated", (data) => {
    if (data.settings) view.settings = data.settings;
    if (view.state === "LOBBY") SS.Lobby.render(view);
    showToast("Host updated the game settings");
  });

  socket.on("room_reset", (data) => {
    view.state = "LOBBY";
    view.hostId = data.host_id;
    view.players = data.players;
    if (data.settings) view.settings = data.settings;
    view.tableTheme = data.table_theme || "casino";
    view.hand = [];
    view.handName = null;
    view.handRank = null;
    view.board = [];
    view.revealed = {};
    view.secondsLeft = null;
    clearRoundEndFx();
    podiumShown = false;
    hideRoundEnd();
    if (SS.hideWinnerScreen) SS.hideWinnerScreen();
    sync();
    showToast("New game — back to the lobby");
  });

  socket.on("kicked", () => {
    alert("You have been removed from the room by the host.");
    window.location.href = "/";
  });

  socket.on("table_theme_updated", (data) => {
    view.tableTheme = data.theme;
    if (SS.themes) SS.themes.apply(view.tableTheme || "casino");
  });

  // ---- game state ----
  let prevTurn = null;

  function applyState(d) {
    if (d.state) view.state = d.state;
    view.players = d.players || view.players;
    if (d.host_id) view.hostId = d.host_id;
    if (d.settings) view.settings = d.settings;
    if (d.table_theme) view.tableTheme = d.table_theme;
    view.seats = d.seats || [];
    view.currentTurn = d.current_turn;
    view.board = d.board || [];
    view.pots = d.pots || [];
    view.potTotal = d.pot_total || 0;
    view.roundNumber = d.round_number;
    view.roundsTotal = d.rounds_total;
    view.blinds = d.blinds;
    view.button = d.button;
    view.sbId = d.sb_id;
    view.bbId = d.bb_id;
    view.street = d.street;
    view.phase = d.phase;
    view.actions = d.actions;
    view.revealed = d.revealed || {};
    view.secondsLeft = typeof d.turn_seconds_left === "number" ? d.turn_seconds_left : null;

    if (view.state === "IN_TURN" && view.currentTurn === youId && prevTurn !== youId) {
      if (SS.sound) SS.sound.turnPing();
    }
    prevTurn = view.currentTurn;
    pending = false;
  }

  function clearRoundEndFx() {
    clearTimeout(revealTimer);
    revealTimer = null;
    view.winBest = null;
    view.winners = null;
    view.potSwept = false;
  }

  socket.on("round_start", (data) => {
    const newRound = data.round_number !== view.roundNumber || view.state !== "IN_TURN";
    applyState(data);
    if (newRound) {
      clearRoundEndFx();
      // Last round's cards must never show: until this round's private deal
      // lands, the hand is dealt face down (table.js) and turned up on arrival.
      if (view.handRound !== data.round_number) {
        view.hand = [];
        view.handName = null;
        view.handRank = null;
      }
      preAction = null;
    }
    hideRoundEnd();
    if (SS.hideWinnerScreen) SS.hideWinnerScreen();
    if (newRound && window.ActionLog) {
      window.ActionLog.clear();
      const b = data.blinds || {};
      window.ActionLog.push(
        "Round " + data.round_number + " of " + data.rounds_total + " — blinds " +
        C.chips(b.sb) + " / " + C.chips(b.bb) + ". " + nameOf(data.button) + " " +
        verb(data.button, "deal") + ".", "system");
    }
    raiseKey = null;
    sync();
    // The blinds go in.
    if (newRound && FX) {
      [data.sb_id, data.bb_id].forEach((uid) => {
        const p = playerOf(uid);
        if (p && p.bet) FX.toPot(uid, p.bet, bb());
      });
    }
  });

  socket.on("poker_state", (data) => {
    const before = view.board.length;
    applyState(data);
    const now = view.board.length;
    if (now > before && window.ActionLog) {
      const label = now === 3 ? "Flop" : now === 4 ? "Turn" : "River";
      window.ActionLog.push(label + ": " + view.board.slice(before).map(cardText).join(" "), "system");
    }
    sync();
  });

  socket.on("your_hand", (data) => {
    // A late copy of the previous round's deal must not overwrite this round's.
    if (typeof data.round_number === "number" && data.round_number < view.roundNumber) return;
    view.hand = data.cards || [];
    view.handRound = typeof data.round_number === "number" ? data.round_number : view.roundNumber;
    view.handName = data.hand_name || null;
    view.handRank = typeof data.hand_rank === "number" ? data.hand_rank : null;
    if (tableView.style.display !== "none") Table.render(view);
    markRankings();
  });

  socket.on("poker_acted", (d) => {
    const who = nameOf(d.user_id);
    const actor = playerOf(d.user_id);
    const v = (base) => verb(d.user_id, base);
    let what;
    let moved = 0;
    switch (d.action) {
      case "fold": what = v("fold"); break;
      case "check": what = v("check"); break;
      case "call": what = v("call") + " " + C.chips(d.amount); moved = d.amount || 0; break;
      case "bet": what = v("bet") + " " + C.chips(d.to); moved = (d.to || 0) - ((actor && actor.bet) || 0); break;
      case "raise": what = v("raise") + " to " + C.chips(d.to); moved = (d.to || 0) - ((actor && actor.bet) || 0); break;
      default: what = d.action;
    }
    if (d.all_in) what += " (all-in)";
    if (d.reason === "timeout") what += " — out of time";
    else if (d.reason === "sitting_out") what += " — sat out";
    const msg = who + " " + what;
    if (window.ActionLog) {
      window.ActionLog.push(msg, d.action === "fold" ? "pass" : "play",
        { actor: who, colorIndex: colorOf(d.user_id) });
    }
    if (d.user_id !== youId) showToast(msg, 1800);
    // Coins travel from the seat into the middle — captured now, before the
    // state broadcast that follows rebuilds the seats.
    if (moved > 0 && FX) FX.toPot(d.user_id, moved, bb());
  });

  socket.on("player_timed_out", (d) => {
    if (d.sat_out) showToast((d.user_id === youId ? "You are" : d.name + " is") + " now sat out", 2600);
  });

  // A refused action must not leave the buttons disabled.
  socket.on("error", () => { pending = false; renderActions(); });

  // ---- view switching ----
  function atTable() {
    return view.state === "IN_TURN" || view.state === "ROUND_END" || view.state === "GAME_END";
  }

  function sync() {
    const table = atTable();
    lobbyView.style.display = table ? "none" : "block";
    tableView.style.display = table ? "flex" : "none";
    const dock = document.getElementById("reaction-dock");
    if (dock) dock.style.display = table ? "flex" : "none";
    if (SS.themes) {
      SS.themes.syncVisibility(isHost());
      SS.themes.apply(view.tableTheme || "casino");
    }
    if (table) {
      Table.render(view);
      renderActions();
    } else {
      SS.Lobby.render(view);
    }
    markRankings();
  }

  // Light up your row in the Hand rankings card — only while the host has hand
  // hints on (the server sends no hand name otherwise) and you still hold a hand.
  function markRankings() {
    if (!SS.pokerRanks) return;
    const me = playerOf(youId);
    const hints = !!(view.settings && Number(view.settings.hand_hints) === 1);
    const holding = me && me.in_hand && !me.folded && view.state !== "LOBBY" && view.hand.length;
    SS.pokerRanks.mark(hints, holding ? view.handRank : null, holding ? view.handName : null);
  }

  // ---- lobby settings (shared renderer: core/lobby.js) ----
  SS.Lobby.init({
    youId,
    fields: [
      { key: "starting_chips", label: "Starting coins", min: 10000, max: 100000000 },
      { key: "rounds", label: "Rounds", min: 1, max: 100 },
      { key: "turn_timer", label: "Turn timer (s)", min: 15, max: 120 },
      { key: "timeout_limit", label: "Missed turns before sat out", min: 1, max: 10 },
      { key: "blind_up_every", label: "Blinds double every (rounds, 0 = off)", min: 0, max: 50 },
      // Whole table, set by the host: when on, each player sees the name of the
      // hand they hold and its row lights up in the Hand rankings card.
      { key: "hand_hints", label: "Hand hints (show each player their hand)", type: "toggle" },
    ],
  });

  // ---- inline confirmation, anchored to the button that asked ----
  // Replaces window.confirm(): a small bubble opens from the button itself, so
  // the question appears where the player is looking and the page keeps its
  // look. Closes on Cancel, a tap elsewhere, Escape, scrolling, or a turn change.
  let confirmBox = null;

  function closeConfirm() {
    if (!confirmBox) return;
    confirmBox.remove();
    confirmBox = null;
    document.removeEventListener("pointerdown", onOutside, true);
    document.removeEventListener("keydown", onEscape, true);
    window.removeEventListener("scroll", closeConfirm, true);
  }
  function onOutside(e) { if (confirmBox && !confirmBox.contains(e.target)) closeConfirm(); }
  function onEscape(e) { if (e.key === "Escape") closeConfirm(); }

  function askConfirm(anchor, text, okLabel, danger, onOk) {
    closeConfirm();
    const box = document.createElement("div");
    box.className = "pk-confirm" + (danger ? " danger" : "");
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-label", text);
    const msg = document.createElement("p");
    msg.textContent = text;
    const row = document.createElement("div");
    row.className = "pk-confirm-row";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "pk-confirm-cancel";
    cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.type = "button";
    ok.className = "pk-confirm-ok";
    ok.textContent = okLabel;
    cancel.addEventListener("click", closeConfirm);
    ok.addEventListener("click", () => { closeConfirm(); onOk(); });
    row.append(cancel, ok);
    box.append(msg, row);
    document.body.appendChild(box);

    // Above the button, centred on it, kept inside the screen; the little
    // arrow keeps pointing at the button even when the bubble is nudged.
    const r = anchor.getBoundingClientRect();
    const w = box.offsetWidth;
    const h = box.offsetHeight;
    const margin = 8;
    const left = Math.max(margin, Math.min(window.innerWidth - w - margin, r.left + r.width / 2 - w / 2));
    const above = r.top - h - 12 >= margin;
    box.style.left = left + "px";
    box.style.top = (above ? r.top - h - 12 : r.bottom + 12) + "px";
    box.classList.add(above ? "above" : "below");
    box.style.setProperty("--arrow-x", (r.left + r.width / 2 - left) + "px");
    ok.focus();

    confirmBox = box;
    setTimeout(() => {
      document.addEventListener("pointerdown", onOutside, true);
      document.addEventListener("keydown", onEscape, true);
      window.addEventListener("scroll", closeConfirm, true);
    }, 0);
  }

  // ---- betting bar ----
  const $ = (id) => document.getElementById(id);
  const bar = {
    label: $("play-label"),
    raiseRow: $("pk-raise"),
    slider: $("pk-slider"),
    amount: $("pk-amount"),
    btns: $("pk-btns"),
    fold: $("pk-fold"),
    call: $("pk-call"),
    callLabel: $("pk-call-label"),
    raise: $("pk-raise-btn"),
    raiseLabel: $("pk-raise-label"),
    allin: $("pk-allin"),
    allinLabel: $("pk-allin-label"),
    back: $("pk-back"),
    pre: $("pk-pre"),
  };

  function setLabel(text, cls) {
    bar.label.textContent = text;
    bar.label.className = "play-label" + (cls ? " " + cls : "");
  }

  function waitingText(me) {
    if (!me || me.is_spectator) return "Watching";
    if (view.state === "ROUND_END") return "Round over";
    if (view.state === "GAME_END") return "Game over";
    if (me.eliminated) return "Out of coins — watching";
    if (me.folded && me.in_hand) return "Folded — waiting for the next round";
    if (me.all_in) return "All-in — good luck!";
    if (view.phase === "runout") return "Running it out…";
    if (view.currentTurn) return "Waiting for " + nameOf(view.currentTurn) + "…";
    return "";
  }

  function clampRaise(v, a) {
    v = Math.round(Number(v) || 0);
    return Math.max(a.min_to, Math.min(a.max_to, v));
  }

  function setRaise(v, a) {
    raiseTo = clampRaise(v, a);
    bar.slider.value = String(raiseTo);
    if (document.activeElement !== bar.amount) bar.amount.value = String(raiseTo);
    const verbText = a.verb === "bet" ? "Bet " : "Raise to ";
    bar.raiseLabel.textContent = verbText + C.chips(raiseTo);
    bar.raise.title = verbText + C.full(raiseTo);
  }

  function preset(kind, a) {
    const potAfterCall = view.potTotal + a.to_call;
    const base = a.bet + a.to_call;          // the current bet level
    if (kind === "min") return a.min_to;
    if (kind === "max") return a.max_to;
    if (kind === "half") return base + Math.round(potAfterCall / 2);
    return base + potAfterCall;              // "pot"
  }

  // Pre-actions: decide while others think, and the game plays it the moment
  // the turn reaches you. Chosen per street; "Check" quietly drops itself if
  // someone bets in the meantime (it never turns into a call or a fold).
  function renderPreActions(me) {
    const key = view.roundNumber + "|" + view.street;
    if (preKey !== key) { preKey = key; preAction = null; }
    const able = view.state === "IN_TURN" && view.phase === "betting" && me && me.in_hand &&
      !me.folded && !me.all_in && !me.sitting_out && view.currentTurn !== youId;
    bar.pre.hidden = !able;
    bar.pre.querySelectorAll("[data-pre]").forEach((b) => {
      const on = preAction === b.dataset.pre;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  bar.pre.querySelectorAll("[data-pre]").forEach((b) => {
    b.addEventListener("click", () => {
      preAction = preAction === b.dataset.pre ? null : b.dataset.pre;
      renderActions();
    });
  });

  // True if a pre-selected move was played for this turn.
  function runPreAction(a) {
    const choice = preAction;
    preAction = null;
    if (choice === "checkfold") {
      send(a.check ? "check" : "fold");
      return true;
    }
    if (choice === "check" && a.check) {
      send("check");
      return true;
    }
    return false;            // "Check" with a bet to face: hand the turn back to the player
  }

  function renderActions() {
    const me = playerOf(youId);
    const a = view.actions;
    const myTurn = view.state === "IN_TURN" && view.currentTurn === youId && a;

    bar.back.hidden = !(me && me.sitting_out && !me.eliminated && view.state !== "GAME_END");
    renderPreActions(me);

    if (!myTurn) {
      closeConfirm();
      bar.btns.style.display = "none";
      bar.raiseRow.hidden = true;
      setLabel(waitingText(me), "muted");
      return;
    }

    if (preAction && !pending && runPreAction(a)) {
      bar.btns.style.display = "none";
      bar.raiseRow.hidden = true;
      setLabel("Playing your pre-selected move…", "muted");
      return;
    }

    bar.btns.style.display = "";
    [bar.fold, bar.call, bar.raise, bar.allin].forEach((b) => (b.disabled = pending));
    setLabel(a.to_call ? C.chips(a.to_call) + " to call" : "Your turn", "ok");

    if (a.check) {
      bar.callLabel.textContent = "Check";
    } else if (a.call >= a.stack) {
      bar.callLabel.textContent = "Call all-in " + C.chips(a.call);
    } else {
      bar.callLabel.textContent = "Call " + C.chips(a.call);
    }

    const canRaise = a.raise;
    const onlyAllIn = canRaise && a.min_to >= a.max_to;
    bar.raiseRow.hidden = !canRaise || onlyAllIn;
    bar.raise.style.display = canRaise && !onlyAllIn ? "" : "none";
    bar.allin.style.display = canRaise ? "" : "none";
    bar.allinLabel.textContent = "All-in " + C.chips(a.max_to);
    bar.allin.title = "All-in: " + C.full(a.stack) + " coins";

    if (canRaise && !onlyAllIn) {
      const step = (view.blinds && view.blinds.sb) || 1;
      bar.slider.min = String(a.min_to);
      bar.slider.max = String(a.max_to);
      bar.slider.step = String(step);
      bar.amount.min = String(a.min_to);
      bar.amount.max = String(a.max_to);
      const key = [view.roundNumber, view.street, a.min_to, a.max_to].join("|");
      if (key !== raiseKey) {
        raiseKey = key;
        raiseTo = a.min_to;
      }
      setRaise(raiseTo, a);
    }
  }

  bar.slider.addEventListener("input", () => {
    // The last notch can sit up to one step below a stack that is not a whole
    // number of small blinds, so anything within a step of the top is all-in.
    const a = view.actions;
    if (!a) return;
    const step = Number(bar.slider.step) || 1;
    setRaise(Number(bar.slider.value) + step > a.max_to ? a.max_to : bar.slider.value, a);
  });
  bar.amount.addEventListener("change", () => { if (view.actions) setRaise(bar.amount.value, view.actions); });
  bar.amount.addEventListener("keydown", (e) => { if (e.key === "Enter") bar.raise.click(); });
  document.querySelectorAll(".pk-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (view.actions) setRaise(preset(btn.dataset.preset, view.actions), view.actions);
    });
  });

  function send(action, amount) {
    if (pending) return;
    pending = true;
    closeConfirm();
    renderActions();
    socket.emit("poker_action", { code, user_id: youId, action, amount: amount == null ? null : amount });
  }

  bar.fold.addEventListener("click", () => {
    const a = view.actions;
    if (a && a.check) {
      askConfirm(bar.fold, "Checking is free — fold anyway?", "Fold", true, () => send("fold"));
      return;
    }
    send("fold");
  });
  bar.call.addEventListener("click", () => {
    const a = view.actions;
    if (a) send(a.check ? "check" : "call");
  });
  bar.raise.addEventListener("click", () => {
    const a = view.actions;
    if (!a) return;
    setRaise(bar.amount.value || raiseTo, a);
    send("raise", raiseTo);
  });
  bar.allin.addEventListener("click", () => {
    const a = view.actions;
    if (!a) return;
    askConfirm(bar.allin, "Go all-in for " + C.full(a.stack) + " coins?", "All-in", true, () => send("allin"));
  });
  bar.back.addEventListener("click", () => socket.emit("poker_back", { code, user_id: youId }));

  // ---- turn timer countdown (the ring lives on the active seat) ----
  setInterval(() => {
    if (view.state === "IN_TURN" && typeof view.secondsLeft === "number" && view.secondsLeft > 0) {
      view.secondsLeft -= 1;
      if (tableView.style.display !== "none") Table.tick(view);
    }
  }, 1000);

  // ---- round end: show the winning cards, pay the pot out, then the summary ----
  let reTimer = null;

  function hideRoundEnd() {
    clearInterval(reTimer);
    reTimer = null;
    const modal = $("roundend-modal");
    if (modal) modal.classList.remove("open");
  }

  function miniCard(card, best) {
    const img = document.createElement("img");
    img.className = "card re-card" + (best ? " pk-best" : "");
    img.src = SS.cardSrc(card.face);
    img.alt = cardText(card);
    return img;
  }

  // Highlight the winning five, fly the pot to the winners, then call `next`.
  // Returns nothing; `next` runs once the table has had its moment.
  function payOut(result, next) {
    clearTimeout(revealTimer);
    const winners = new Set();
    const best = new Set();
    (result.awards || []).forEach((aw) => aw.winners.forEach((u) => {
      winners.add(u);
      const h = (result.hands || {})[u];
      if (h && h.best) h.best.forEach((id) => best.add(id));
    }));
    view.winners = winners;
    view.winBest = best.size ? best : null;
    view.potSwept = false;
    Table.render(view);

    // A showdown gets a beat to read the cards before the coins move.
    const pause = result.fold_win ? 250 : 900;
    revealTimer = setTimeout(() => {
      let done = 0;
      (result.awards || []).forEach((aw, i) => {
        Object.entries(aw.payouts || {}).forEach(([uid, amount], j) => {
          if (FX) done = Math.max(done, FX.toSeat(uid, amount, bb(), (i + j) * 180) || 0);
        });
      });
      revealTimer = setTimeout(() => {
        view.potSwept = true;
        Table.render(view);
        revealTimer = setTimeout(next, 450);
      }, Math.max(300, done - 150));
    }, pause);
  }

  socket.on("poker_round_end", (d) => {
    const first = view.state !== "ROUND_END" || !$("roundend-modal").classList.contains("open");
    view.state = "ROUND_END";
    if (d.host_id) view.hostId = d.host_id;
    if (d.players) view.players = d.players;
    view.secondsLeft = null;
    view.actions = null;
    sync();
    // A resync of a summary that is already up just refreshes it in place.
    if (!first || view.potSwept) { showRoundEnd(d); return; }
    const result = d.result || {};
    if (window.ActionLog) awardLines(result).forEach((l) => window.ActionLog.push(l, "win"));
    payOut(result, () => showRoundEnd(d));
  });

  function awardLines(result) {
    return (result.awards || []).map((aw, i) => {
      const names = aw.winners.map(nameOf).join(" & ");
      const verbText = aw.winners.length > 1 ? " split " : (aw.winners[0] === youId ? " win " : " wins ");
      const pot = (result.awards.length > 1 ? (i === 0 ? "the main pot of " : "a side pot of ") : "");
      const how = result.fold_win ? " — everyone else folded" : (aw.hand_name ? " with " + aw.hand_name : "");
      return names + verbText + pot + C.chips(aw.amount) + how;
    });
  }

  function showRoundEnd(d) {
    if (SS.pokerRanks) SS.pokerRanks.yieldToOverlay();
    const result = d.result || {};
    const modal = $("roundend-modal");
    $("roundend-title").textContent = "Round " + d.round_number + " of " + d.rounds_total;
    $("roundend-sub").textContent = awardLines(result).join(" · ");

    const body = $("roundend-body");
    body.innerHTML = "";
    const hands = result.hands || {};
    const winners = new Set();
    (result.awards || []).forEach((aw) => aw.winners.forEach((u) => winners.add(u)));

    (d.rows || []).forEach((r) => {
      const row = document.createElement("div");
      row.className = "re-row" + (winners.has(r.user_id) ? " caller" : "") + (r.eliminated ? " out" : "");
      const head = document.createElement("div");
      head.className = "re-head";
      const name = document.createElement("span");
      name.className = "re-name";
      name.textContent = r.name + (r.user_id === youId ? " (you)" : "");
      const score = document.createElement("span");
      score.className = "re-score";
      const delta = document.createElement("span");
      delta.className = "pk-delta " + (r.delta > 0 ? "up" : r.delta < 0 ? "down" : "");
      delta.textContent = r.delta ? C.signed(r.delta) : "±0";
      delta.title = (r.delta > 0 ? "+" : "") + C.full(r.delta);
      const left = document.createElement("span");
      left.className = "pk-left";
      left.textContent = r.eliminated ? "Out of coins" : C.chips(r.chips) + " left";
      left.title = C.full(r.chips) + " coins";
      score.append(delta, left);
      head.append(name, score);
      row.appendChild(head);

      const shown = hands[r.user_id];
      if (shown) {
        const cards = document.createElement("div");
        cards.className = "re-cards";
        const best = new Set(shown.best || []);
        shown.cards.forEach((c) => cards.appendChild(miniCard(c, best.has(c.id))));
        const hn = document.createElement("span");
        hn.className = "re-total";
        hn.textContent = shown.name;
        cards.appendChild(hn);
        row.appendChild(cards);
      } else if (r.folded) {
        const f = document.createElement("div");
        f.className = "re-cards";
        const t = document.createElement("span");
        t.className = "re-total";
        t.textContent = "Folded";
        f.appendChild(t);
        row.appendChild(f);
      }
      body.appendChild(row);
    });

    if ((result.board || []).length) {
      const boardRow = document.createElement("div");
      boardRow.className = "re-cards pk-re-board";
      const lbl = document.createElement("span");
      lbl.className = "re-total";
      lbl.textContent = "Board";
      boardRow.appendChild(lbl);
      const best = view.winBest || new Set();
      result.board.forEach((c) => boardRow.appendChild(miniCard(c, best.has(c.id))));
      body.insertBefore(boardRow, body.firstChild);
    }

    const footer = $("roundend-footer");
    footer.innerHTML = "";
    let btn = null;
    let wait = null;
    if (isHost()) {
      btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.addEventListener("click", () => {
        btn.disabled = true;
        socket.emit("poker_next_round", { code, user_id: youId });
      });
      footer.appendChild(btn);
    } else {
      wait = document.createElement("p");
      wait.className = "waiting";
      wait.style.margin = "0";
      footer.appendChild(wait);
    }

    // The countdown is the server's; the payout animation above eats a couple
    // of its seconds, which is fine — the server deals on its own clock anyway.
    const endsAt = Date.now() + Math.max(0, d.seconds_left || 0) * 1000;
    function paint() {
      const s = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
      if (btn && !btn.disabled) btn.textContent = s > 0 ? "Start next round (" + s + "s)" : "Dealing…";
      if (wait) wait.textContent = s > 0 ? "Next round starts in " + s + "s…" : "Dealing…";
    }
    paint();
    clearInterval(reTimer);
    reTimer = setInterval(paint, 500);
    modal.classList.add("open");
  }

  // ---- game over: the last pot pays out, then the shared podium ----
  socket.on("game_end", (d) => {
    // The state broadcast just before this already says GAME_END, so "first
    // time" has to be remembered explicitly rather than read off view.state.
    const already = podiumShown;
    podiumShown = true;
    hideRoundEnd();
    view.state = "GAME_END";
    if (d.host_id) view.hostId = d.host_id;
    if (d.players) view.players = d.players;
    view.secondsLeft = null;
    view.actions = null;
    const last = d.last_round;
    if (!already && last && window.ActionLog) awardLines(last).forEach((l) => window.ActionLog.push(l, "win"));
    sync();

    const rows = d.standings || [];
    const holding = rows.filter((r) => !r.eliminated).length;
    const mine = rows.find((r) => r.user_id === youId);
    let subtitle = holding <= 1
      ? "Won every coin on the table."
      : "Most coins after " + d.rounds_played + " rounds.";
    if (mine && d.winner !== youId) subtitle += " You finished #" + mine.place + ".";
    const podium = () => {
      if (SS.pokerRanks) SS.pokerRanks.yieldToOverlay();
      if (window.ActionLog && !already) {
        window.ActionLog.push("🎉 " + nameOf(d.winner) + " " + verb(d.winner, "win") + " the game!", "win");
      }
      SS.showWinnerScreen({
        winnerId: d.winner,
        rows,
        youId,
        isHost: isHost(),
        onRematch: () => socket.emit("rematch", { code, user_id: youId }),
        subtitle,
        scoreText: (r) => C.chips(r.chips) + " (" + (r.net ? C.signed(r.net) : "±0") + ")",
      });
    };
    if (!already && last && !view.potSwept) payOut(last, podium);
    else podium();
  });
})();
