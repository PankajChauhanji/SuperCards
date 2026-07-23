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
  };
  window.SS.view = view; // selection.js reads this live reference

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
  if (socket.connected) enter();

  // ---- server events ----
  socket.on("room_joined", (data) => {
    view.hostId = data.host_id;
    view.state = data.state;
    view.players = data.players;
    if (data.settings) view.settings = data.settings;
    view.tableTheme = data.table_theme || "default";
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
    view.tableTheme = data.table_theme || "default";
    syncTableTheme();
    view.hand = [];
    view.justDrawnId = null;
    view.secondsLeft = null;
    prevTurn = null;
    document.getElementById("roundend-modal").classList.remove("open");
    syncTimer();
    sync();
    showToast("New game — back to the lobby");
  });

  socket.on("round_start", (data) => {
    view.state = "IN_TURN";
    applyTable(data);
    document.getElementById("roundend-modal").classList.remove("open");
    if (window.Selection) window.Selection.reset();
    sync();
    syncTimer();
  });

  socket.on("table_state", (data) => {
    applyTable(data);
    if (view.state === "IN_TURN") {
      Table.render(view);
      if (window.Selection) window.Selection.refresh();
    }
    syncTimer();
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
      drawnTimer = setTimeout(() => {
        view.justDrawnId = null;
        if (view.state === "IN_TURN") Table.render(view);
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
    if (data.by === youId) return;
    const p = view.players.find((x) => x.user_id === data.by);
    const who = p ? p.name : "Someone";
    showToast(`${who} threw ${data.count} card(s) as ${data.declared_rank}`);
  });

  socket.on("player_passed", (data) => {
    const p = view.players.find((x) => x.user_id === data.by);
    const who = p ? p.name : "Someone";
    showToast(`${who} passed`);
  });

  socket.on("bluff_show_result", (data) => {
    const challenger = view.players.find(p => p.user_id === data.challenger);
    const defender = view.players.find(p => p.user_id === data.defender);
    const chName = challenger ? challenger.name : "Someone";
    const defName = defender ? defender.name : "Someone";
    
    if (data.is_bluff) {
      showToast(`${chName} caught ${defName}'s bluff!`);
    } else {
      showToast(`${defName} told the truth! ${chName} was wrong.`);
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
    if (view.state !== "IN_TURN") renderLobby();
    showToast("Host updated the game settings");
  });

  socket.on("round_end", (data) => {
    view.state = "ROUND_END";
    view.secondsLeft = null;
    if (data.host_id) view.hostId = data.host_id;
    if (data.players) view.players = data.players;
    if (tableView.style.display !== "none") Table.render(view);
    if (window.Selection) window.Selection.refresh();
    syncTimer();
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
    syncTimer();
    showGameOver(data.winner, data.standings);
  });

  // ---- turn timer countdown ----
  function syncTimer() {
    const el = document.getElementById("turn-timer");
    if (view.state !== "IN_TURN" || view.secondsLeft == null) {
      el.style.display = "none";
      return;
    }
    el.style.display = "inline-block";
    el.textContent = "\u23f1 " + Math.max(0, view.secondsLeft) + "s";
    el.classList.toggle("low", view.secondsLeft <= 10);
  }
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
      syncTimer();
    }
    if (view.state === "IN_TURN" && view.awaitingDraw &&
        typeof view.pickSecondsLeft === "number" && view.pickSecondsLeft > 0) {
      view.pickSecondsLeft -= 1;
    }
    syncPickTimer();
  }, 1000);

  // ---- view switching ----
  function sync() {
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
      renderLobby();
    }
  }

  // ---- lobby rendering ----
  const LOBBY_PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];

  function renderLobby() {
    rosterEl.innerHTML = "";
    view.players.forEach((p) => {
      const li = document.createElement("li");
      const who = document.createElement("div");
      who.className = "who";
      const sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = LOBBY_PALETTE[(p.color || 0) % LOBBY_PALETTE.length];
      const dot = document.createElement("span");
      dot.className = "dot" + (p.connected ? " on" : "");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = p.name;
      who.appendChild(sw);
      who.appendChild(dot);
      who.appendChild(name);

      const tags = document.createElement("div");
      tags.className = "roster-tags";
      if (p.user_id === view.hostId) tags.appendChild(makeBadge("Host", "host"));
      if (p.user_id === youId) tags.appendChild(makeBadge("You", "you"));
      if (youId === view.hostId && p.user_id !== youId) {
        const kick = document.createElement("button");
        kick.className = "kick-btn";
        kick.textContent = "\u2715";
        kick.title = "Remove " + p.name;
        kick.addEventListener("click", () => {
          if (confirm("Remove " + p.name + " from the room?")) {
            socket.emit("kick_player", { code, user_id: youId, target: p.user_id });
          }
        });
        tags.appendChild(kick);
      }

      li.appendChild(who);
      li.appendChild(tags);
      rosterEl.appendChild(li);
    });

    renderLobbySettings();

    const n = view.players.length;
    metaEl.textContent = n + (n === 1 ? " player" : " players") + " in the room";

    const isHost = youId === view.hostId;
    startRow.innerHTML = "";
    if (isHost) {
      const btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.textContent = "Start game";
      btn.addEventListener("click", () => {
        socket.emit("start_game", { code, user_id: youId });
      });
      startRow.appendChild(btn);
    } else {
      const p = document.createElement("p");
      p.className = "waiting";
      p.textContent = "Waiting for the host to start\u2026";
      startRow.appendChild(p);
    }
  }

  function renderLobbySettings() {
    const el = document.getElementById("lobby-settings");
    if (!el) return;
    const s = view.settings;
    if (!s) { el.innerHTML = ""; return; }
    const isHost = youId === view.hostId;

    if (!isHost) {
      const items = [
        ["Turn timer", s.turn_timer + "s"],
        ["Timeouts", s.timeout_limit],
        ["Decks", s.num_decks || 1],
      ];
      el.innerHTML = "<h3>Game settings</h3>";
      const grid = document.createElement("div");
      grid.className = "settings-readout";
      items.forEach(([k, v]) => {
        const row = document.createElement("div");
        row.className = "sr-item";
        row.innerHTML = "<span>" + k + "</span><strong>" + v + "</strong>";
        grid.appendChild(row);
      });
      el.appendChild(grid);
      return;
    }

    // Host: editable before the game starts.
    el.innerHTML = "<h3>Game settings <span class=\"se-hint\">(you can edit these)</span></h3>";
    const fields = [
      ["turn_timer", "Turn timer (s)", 15, 180],
      ["timeout_limit", "Timeouts allowed", 1, 10],
      ["num_decks", "Number of decks", 1, 10],
    ];
    const grid = document.createElement("div");
    grid.className = "settings-edit";
    fields.forEach(([key, label, lo, hi]) => {
      const wrap = document.createElement("div");
      wrap.className = "se-item";
      const lab = document.createElement("label");
      lab.textContent = label;
      const inp = document.createElement("input");
      inp.type = "number"; inp.min = lo; inp.max = hi; inp.value = s[key];
      inp.dataset.key = key;
      wrap.appendChild(lab); wrap.appendChild(inp);
      grid.appendChild(wrap);
    });
    el.appendChild(grid);

    const save = document.createElement("button");
    save.className = "btn-ghost se-save";
    save.textContent = "Save settings";
    save.addEventListener("click", () => {
      const out = {};
      grid.querySelectorAll("input").forEach((i) => {
        out[i.dataset.key] = parseInt(i.value, 10);
      });
      socket.emit("update_settings", { code, user_id: youId, settings: out });
    });
    el.appendChild(save);
  }

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
      if (r.is_safe) name.appendChild(makeBadge("Safe", "safe"));
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
          img.src = "/static/img/cards/" + c.face + ".svg";
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
        socket.emit("next_round", { code, user_id: youId });
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

  function showGameOver(winnerId, rows) {
    const modal = document.getElementById("roundend-modal");
    const title = document.getElementById("roundend-title");
    const sub = document.getElementById("roundend-sub");
    const body = document.getElementById("roundend-body");

    const winnerName = (rows.find((r) => r.user_id === winnerId) || {}).name || "Nobody";
    title.textContent = winnerName + " wins!";
    sub.textContent = winnerId === youId
      ? "You're the last one standing."
      : "Last player standing takes the game.";

    body.innerHTML = "";
    rows.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "re-row";
      if (r.user_id === winnerId) row.classList.add("caller");
      if (r.eliminated) row.classList.add("out");

      const head = document.createElement("div");
      head.className = "re-head";
      const name = document.createElement("span");
      name.className = "re-name";
      name.textContent = (i + 1) + ". " + r.name;
      if (r.user_id === winnerId) name.appendChild(makeBadge("Winner", "host"));
      if (r.eliminated) name.appendChild(makeBadge("Out", "you"));
      const score = document.createElement("span");
      score.className = "re-score";
      score.textContent = r.total_score + " pts";
      head.appendChild(name);
      head.appendChild(score);
      row.appendChild(head);
      body.appendChild(row);
    });

    const footer = document.getElementById("roundend-footer");
    footer.innerHTML = "";

    if (youId === view.hostId) {
      const again = document.createElement("button");
      again.className = "btn-primary";
      again.textContent = "Play again";
      again.addEventListener("click", () => {
        again.disabled = true;
        socket.emit("rematch", { code, user_id: youId });
      });
      footer.appendChild(again);
    } else {
      const wait = document.createElement("span");
      wait.className = "waiting";
      wait.style.marginRight = "auto";
      wait.textContent = "Waiting for the host to start a rematch\u2026";
      footer.appendChild(wait);
    }

    const home = document.createElement("button");
    home.className = "btn-ghost";
    home.style.width = "auto";
    home.textContent = "Back to home";
    home.addEventListener("click", () => { window.location.href = "/"; });
    footer.appendChild(home);

    modal.classList.add("open");
  }

  // ---- reactions ----
  const rxDock = document.getElementById("reaction-dock");
  const rxFab = document.getElementById("reaction-fab");
  const rxPanel = document.getElementById("reaction-panel");
  const rxRecentContainer = document.getElementById("rx-recent-container");
  const rxRecentGrid = document.getElementById("rx-recent-grid");

  function getRecentReactions() {
    try {
      return JSON.parse(localStorage.getItem("super_seven_recent_rx")) || [];
    } catch (e) {
      return [];
    }
  }

  function addRecentReaction(emoji) {
    let recent = getRecentReactions();
    recent = recent.filter(e => e !== emoji);
    recent.unshift(emoji);
    if (recent.length > 5) recent.pop();
    localStorage.setItem("super_seven_recent_rx", JSON.stringify(recent));
    updateRecentGrid();
  }

  function updateRecentGrid() {
    if (!rxRecentContainer || !rxRecentGrid) return;
    const recent = getRecentReactions();
    if (rxFab && recent.length > 0) {
      rxFab.textContent = recent[0];
    }
    if (recent.length === 0) {
      rxRecentContainer.style.display = "none";
      return;
    }
    rxRecentContainer.style.display = "flex";
    rxRecentGrid.innerHTML = "";
    recent.forEach((emoji) => {
      const btn = document.createElement("button");
      btn.className = "rx";
      btn.dataset.e = emoji;
      btn.title = emoji;
      btn.textContent = emoji;
      btn.addEventListener("click", () => {
        socket.emit("reaction", { code, user_id: youId, emoji });
        addRecentReaction(emoji);
      });
      rxRecentGrid.appendChild(btn);
    });
  }

  if (rxFab && rxPanel) {
    let lastFabClickTime = 0;
    let fabClickTimeout = null;

    rxFab.addEventListener("click", (e) => {
      const now = Date.now();
      const diff = now - lastFabClickTime;
      lastFabClickTime = now;

      if (diff < 300) {
        // Double click / rapid-fire spam
        if (fabClickTimeout) {
          clearTimeout(fabClickTimeout);
          fabClickTimeout = null;
        }
        const recent = getRecentReactions();
        const emoji = recent[0] || "🤡";
        socket.emit("reaction", { code, user_id: youId, emoji });
        addRecentReaction(emoji);
      } else {
        // Single click (detecting double click first)
        fabClickTimeout = setTimeout(() => {
          fabClickTimeout = null;
          rxPanel.hidden = !rxPanel.hidden;
          if (!rxPanel.hidden) {
            updateRecentGrid();
          }
        }, 220);
      }
    });

    rxPanel.querySelectorAll("#rx-main-grid .rx").forEach((btn) => {
      btn.addEventListener("click", () => {
        const emoji = btn.dataset.e;
        socket.emit("reaction", { code, user_id: youId, emoji });
        addRecentReaction(emoji);
      });
    });

    document.addEventListener("click", (e) => {
      if (rxDock && !rxDock.contains(e.target)) rxPanel.hidden = true;
    });

    // Initialize recent grid
    updateRecentGrid();
  }

  socket.on("reaction", (data) => floatReaction(data.emoji, data.name));

  function floatReaction(emoji, name) {
    const layer = document.getElementById("reactions-layer");
    if (!layer) return;
    const el = document.createElement("div");
    el.className = "rx-float";
    el.textContent = emoji;
    if (name) {
      const tag = document.createElement("span");
      tag.className = "rx-name";
      tag.textContent = name;
      el.appendChild(tag);
    }
    // Random-ish horizontal start in the lower-middle of the screen.
    el.style.left = (10 + Math.random() * 70) + "%";
    el.style.setProperty("--drift", (Math.random() * 60 - 30) + "px");
    layer.appendChild(el);
    setTimeout(() => el.remove(), 3900);
  }

  // ---- selection / actions ----
  if (window.Selection) {
    window.Selection.init({ socket, code, you: youId });
  }

  // ---- rules modal ----
  const modal = document.getElementById("rules-modal");
  document.getElementById("rules-btn").addEventListener("click", () => modal.classList.add("open"));
  document.getElementById("rules-close").addEventListener("click", () => modal.classList.remove("open"));
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("open");
  });

  const rulesContainer = document.getElementById('rules-content-container');
  const rulesTitle = document.getElementById('rules-title');
  const langBtns = document.querySelectorAll('.lang-btn');
  const rulesCache = {};

  function loadRules(lang) {
    if (!rulesContainer || !rulesTitle) return;
    
    langBtns.forEach(btn => {
      if(btn.dataset.lang === lang) {
        btn.style.background = '#6706ce';
        btn.style.color = 'white';
      } else {
        btn.style.background = 'transparent';
        btn.style.color = 'inherit';
      }
    });

    rulesTitle.innerText = lang === 'hi' ? '📖 नियम पुस्तिका' : '📖 Rule Book';

    if (rulesCache[lang]) {
      rulesContainer.innerHTML = rulesCache[lang];
    } else {
      rulesContainer.innerHTML = '<p>Loading rules...</p>';
      const gameType = window.GAME_TYPE || 'super_seven';
      fetch(`/static/rules/${gameType}/${lang}.html`)
        .then(res => {
          if (!res.ok) throw new Error('Network response was not ok');
          return res.text();
        })
        .then(html => {
          rulesCache[lang] = html;
          rulesContainer.innerHTML = html;
        })
        .catch(err => {
          rulesContainer.innerHTML = '<p>Error loading rules. Please try again.</p>';
        });
    }
  }

  langBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      loadRules(e.target.dataset.lang);
    });
  });

  if (rulesContainer) {
    loadRules('en');
  }

  // ---- spectator admit modal ----
  let admitTargetId = null;
  const specModal = document.getElementById("spectator-modal");
  const specCancel = document.getElementById("admit-cancel");
  const specConfirm = document.getElementById("admit-confirm");

  window.SS.openSpectatorModal = function(targetId, name) {
    if (!specModal) return;
    admitTargetId = targetId;
    document.getElementById("admit-name").textContent = name;
    document.getElementById("admit-penalty").value = "0";
    specModal.classList.add("open");
  };

  if (specCancel) {
    specCancel.addEventListener("click", () => {
      specModal.classList.remove("open");
      admitTargetId = null;
    });
  }
  
  if (specConfirm) {
    specConfirm.addEventListener("click", () => {
      if (admitTargetId) {
        const penalty = parseInt(document.getElementById("admit-penalty").value, 10) || 0;
        socket.emit("admit_spectator", { code, user_id: youId, target_id: admitTargetId, penalty: penalty });
      }
      specModal.classList.remove("open");
      admitTargetId = null;
    });
  }

  // ---- mute toggle ----
  const muteBtn = document.getElementById("mute-btn");
  if (muteBtn && window.SS.sound) {
    const paint = () => { muteBtn.textContent = window.SS.sound.muted() ? "\uD83D\uDD07" : "\uD83D\uDD0A"; };
    paint();
    muteBtn.addEventListener("click", () => {
      window.SS.sound.toggleMute();
      paint();
    });
  }

  // ---- copy code ----
  const copyBtn = document.getElementById("copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(code);
        showToast("Room code copied.");
      } catch (_) {
        showToast("Code: " + code);
      }
    });
  }

  // ---- Table Theme Selector ----
  const themeSelectWrap = document.getElementById("theme-select-wrap");
  const themeSelectBtn = document.getElementById("theme-select-btn");
  const themeDropdown = document.getElementById("theme-dropdown");

  if (themeSelectBtn && themeDropdown) {
    themeSelectBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isHidden = themeDropdown.hasAttribute("hidden");
      if (isHidden) {
        themeDropdown.removeAttribute("hidden");
        themeDropdown.setAttribute("aria-hidden", "false");
      } else {
        themeDropdown.setAttribute("hidden", "");
        themeDropdown.setAttribute("aria-hidden", "true");
      }
    });

    themeDropdown.querySelectorAll(".theme-opt").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const theme = btn.dataset.t;
        socket.emit("change_table_theme", { code, user_id: youId, theme });
        themeDropdown.setAttribute("hidden", "");
        themeDropdown.setAttribute("aria-hidden", "true");
      });
    });

    document.addEventListener("click", () => {
      if (themeDropdown) {
        themeDropdown.setAttribute("hidden", "");
        themeDropdown.setAttribute("aria-hidden", "true");
      }
    });
  }

  function syncThemeSelectorVisibility() {
    if (!themeSelectWrap) return;
    const isHost = view.hostId === youId;
    themeSelectWrap.style.display = isHost ? "inline-flex" : "none";
  }

  function syncTableTheme() {
    const theme = view.tableTheme || "default";
    document.body.classList.remove("theme-default", "theme-casino", "theme-cyberpunk", "theme-marble", "theme-red_casino");
    if (theme !== "default") {
      document.body.classList.add("theme-" + theme);
    }

    const currentIcon = document.getElementById("current-theme-icon");
    const currentName = document.getElementById("current-theme-name");
    if (currentIcon && currentName) {
      const themeMap = {
        "default": { icon: "🟢", name: "Default" },
        "casino": { icon: "🎰", name: "Casino Felt" },
        "cyberpunk": { icon: "👾", name: "Cyberpunk" },
        "marble": { icon: "🏛️", name: "Marble Luxury" },
        "red_casino": { icon: "🍒", name: "Red Casino" }
      };
      const active = themeMap[theme] || themeMap["default"];
      currentIcon.textContent = active.icon;
      currentName.textContent = active.name;
    }
  }

  socket.on("table_theme_updated", (data) => {
    view.tableTheme = data.theme;
    syncTableTheme();
  });
})();
