// Shared lobby renderer — reused by every game variant.
//
// The lobby is identical across games except for the *settings schema* (which
// fields, their labels and bounds). A game calls:
//     window.SS.Lobby.init({ youId, fields })   // once, with its settings schema
//     window.SS.Lobby.render(view)              // on every roster/settings change
// and this module owns the whole waiting room: the invite card (copy / share /
// WhatsApp), the seats (with host-only remove and Add bot), the table rules
// (a readable summary for everyone, an editor for the host), and the start bar.
//
// `fields` is an array of { key, label, min?, max? } — a number box — or
// { key, label, type: "toggle" } for an on/off switch stored as 1 / 0 (so the
// server's integer settings sanitising needs nothing new). `view` supplies
// { players, hostId, settings } (the game's own live view object).
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const code = window.SS_ROOM_CODE;
  const showToast = SS.showToast || function () {};
  const icon = (name) => (SS.icon ? SS.icon(name) : "");

  // Stable per-player swatch colours (match the table/action-log palette).
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];
  const MIN_PLAYERS = window.MIN_PLAYERS || 2;
  const GAME_NAME = window.GAME_NAME || "Super Cards";

  let youId = null;
  let fields = [];
  let editing = false;     // host has the rules editor open

  const $ = (id) => document.getElementById(id);

  function init(opts) {
    opts = opts || {};
    youId = opts.youId || (window.Identity && window.Identity.userId()) || null;
    fields = opts.fields || [];
  }

  // The lobby used to be two tabs (Players / Settings). Both are on screen now;
  // kept so any caller that still switches tabs does nothing harmful.
  function setTab() {}

  function badge(text, cls) {
    const b = document.createElement("span");
    b.className = "badge " + cls;
    b.textContent = text;
    return b;
  }

  function hostName(view) {
    const h = view.players.find((p) => p.user_id === view.hostId);
    return h ? h.name : "the host";
  }

  // ---- invite card ----
  // Share the room's own address. Someone who opens it without being seated is
  // asked only for their name and dropped straight in (core/join_gate.js).
  const inviteUrl = window.location.origin + "/room/" + encodeURIComponent(code || "");
  const inviteText = "Join my " + GAME_NAME + " table on Super Cards — code " + code;

  function wireInviteOnce() {
    const share = $("share-btn");
    if (share && !share.dataset.wired) {
      share.dataset.wired = "1";
      share.addEventListener("click", async () => {
        if (navigator.share) {
          try { await navigator.share({ title: "Super Cards", text: inviteText, url: inviteUrl }); return; }
          catch (e) { if (e && e.name === "AbortError") return; }
        }
        try {
          await navigator.clipboard.writeText(inviteUrl);
          showToast("Invite link copied", 0, "success");
        } catch (_) {
          showToast(inviteUrl, 6000);
        }
      });
    }
    const wa = $("whatsapp-btn");
    if (wa && !wa.dataset.wired) {
      wa.dataset.wired = "1";
      wa.href = "https://wa.me/?text=" + encodeURIComponent(inviteText + "\n" + inviteUrl);
    }
  }

  function renderInvite(view) {
    wireInviteOnce();
    const title = $("lobby-title");
    if (!title) return;
    const n = view.players.filter((p) => !p.is_spectator).length;
    title.textContent = n >= MIN_PLAYERS ? "Ready when you are" : "Waiting for players";
  }

  // ---- seats ----
  // How many seats to draw: everyone here plus one open seat, at least four so
  // a fresh room does not look empty, and never more than the game allows.
  function seatsToShow(n) {
    const cap = window.MAX_PLAYERS || 20;
    return Math.min(cap, Math.max(4, n + 1));
  }

  function renderRoster(view) {
    const rosterEl = $("roster");
    if (!rosterEl) return;
    const isHost = view.hostId === youId;
    rosterEl.innerHTML = "";

    view.players.forEach((p) => {
      const li = document.createElement("li");
      li.className = "seat-tile" + (p.connected ? "" : " offline") + (p.user_id === youId ? " is-you" : "");

      const av = document.createElement("span");
      av.className = "seat-av";
      av.style.background = PALETTE[(p.color || 0) % PALETTE.length];
      av.innerHTML = SS.avatarFace ? SS.avatarFace(p.name, p.avatar) : "";
      const dot = document.createElement("span");
      dot.className = "seat-dot" + (p.connected ? " on" : "");
      dot.title = p.connected ? "Online" : "Offline";
      av.appendChild(dot);

      const name = document.createElement("span");
      name.className = "seat-name";
      name.textContent = p.name;

      const tags = document.createElement("span");
      tags.className = "seat-tags";
      if (p.user_id === view.hostId) {
        const h = badge("Host", "host");
        h.insertAdjacentHTML("afterbegin", icon("crown"));
        tags.appendChild(h);
      }
      if (p.user_id === youId) tags.appendChild(badge("You", "you"));
      if (p.is_spectator) tags.appendChild(badge("Watching", "you"));

      li.append(av, name, tags);

      // Host may remove anyone but themselves — including a bot they seated,
      // which is the only way to undo an Add-bot before the game starts.
      // Computer players otherwise look exactly like everyone else, so the table
      // reads as a table, not a lineup of extras.
      if (isHost && p.user_id !== youId) {
        const kick = document.createElement("button");
        kick.className = "kick-btn";
        kick.setAttribute("aria-label", "Remove " + p.name);
        kick.title = "Remove " + p.name;
        kick.innerHTML = icon("x") || "&#10005;";
        kick.addEventListener("click", () => {
          const remove = () => socket.emit("kick_player", { code, user_id: youId, target: p.user_id });
          // No confirm for a bot: seating one is a click, so removing one should
          // be too. Removing a person is not undoable for them, so that keeps it.
          if (p.is_bot) return remove();
          const ask = SS.confirm
            ? SS.confirm({ title: "Remove " + p.name + "?", message: "They'll be taken out of this room and can rejoin with the code.",
                           confirmLabel: "Remove", danger: true })
            : Promise.resolve(window.confirm("Remove " + p.name + " from the room?"));
          ask.then((ok) => { if (ok) remove(); });
        });
        li.appendChild(kick);
      }
      rosterEl.appendChild(li);
    });

    const open = seatsToShow(view.players.length) - view.players.length;
    for (let i = 0; i < open; i++) {
      const li = document.createElement("li");
      li.className = "seat-tile open";
      li.innerHTML = '<span class="seat-av">' + icon("user-plus") + '</span><span class="seat-name">Open seat</span>';
      rosterEl.appendChild(li);
    }

    const n = view.players.length;
    const meta = $("lobby-meta");
    if (meta) {
      meta.textContent = n < MIN_PLAYERS
        ? "Need at least " + MIN_PLAYERS + " players. Share the code, or add a bot."
        : n + (n === 1 ? " player" : " players") + " at the table";
    }
    const count = $("players-count");
    if (count) count.textContent = n;
  }

  // ---- table rules ----
  // Everyone sees a readable summary; the host gets an Edit button that opens
  // the same number boxes and switches as before. The editor is built once per
  // opening, so a roster refresh never wipes the host's in-progress edits.
  function formatValue(f, v) {
    if (v == null || v === "") return "—";
    if (f.type === "toggle") return Number(v) === 1 ? "On" : "Off";
    const n = Number(v);
    return Number.isFinite(n) ? n.toLocaleString("en-IN") : String(v);
  }

  function renderSummary(view, el) {
    const s = view.settings || {};
    const list = document.createElement("dl");
    list.className = "rules-summary";
    fields.forEach((f) => {
      const row = document.createElement("div");
      row.className = "rules-item";
      const dt = document.createElement("dt");
      dt.textContent = f.label;
      const dd = document.createElement("dd");
      dd.textContent = formatValue(f, s[f.key]);
      if (f.type === "toggle") dd.classList.add(Number(s[f.key]) === 1 ? "on" : "off");
      row.append(dt, dd);
      list.appendChild(row);
    });
    el.appendChild(list);
  }

  function buildEditor(view, el) {
    let html = '<div class="lobby-settings-grid">';
    fields.forEach((f) => {
      if (f.type === "toggle") {
        html += '<label class="set-item set-toggle"><span class="set-label">' + f.label + "</span>" +
          '<input type="checkbox" role="switch" class="set-switch" data-key="' + f.key + '" /></label>';
        return;
      }
      const bounds = (f.min != null ? ' min="' + f.min + '"' : "") +
                     (f.max != null ? ' max="' + f.max + '"' : "");
      html += '<label class="set-item"><span class="set-label">' + f.label + "</span>" +
        '<input type="number" inputmode="numeric" data-key="' + f.key + '"' + bounds + " /></label>";
    });
    html += "</div>";
    html += '<div class="rules-editor-actions">' +
      '<button class="btn-ghost btn-sm" type="button" id="lobby-cancel-settings">Cancel</button>' +
      '<button class="btn-primary btn-sm" type="button" id="lobby-save-settings">Save rules</button></div>';
    el.innerHTML = html;

    const s = view.settings || {};
    el.querySelectorAll("input[data-key]").forEach((inp) => {
      const v = s[inp.dataset.key];
      if (inp.type === "checkbox") inp.checked = Number(v) === 1;
      else inp.value = v != null ? String(v) : "";
    });

    function save(close) {
      const out = {};
      // It saves the whole form: the server rebuilds settings from defaults, so
      // a partial update would reset the other fields.
      el.querySelectorAll("input[data-key]").forEach((inp) => {
        if (inp.type === "checkbox") out[inp.dataset.key] = inp.checked ? 1 : 0;
        else if (inp.value !== "") out[inp.dataset.key] = parseInt(inp.value, 10);
      });
      socket.emit("update_settings", { code, user_id: youId, settings: out });
      showToast("Rules saved", 0, "success");
      if (close) { editing = false; renderSettings(view); }
    }
    $("lobby-save-settings").addEventListener("click", () => save(true));
    $("lobby-cancel-settings").addEventListener("click", () => { editing = false; renderSettings(view); });
    // A switch reads as instant, so it saves the moment it is flipped — a
    // flipped-but-unsaved switch looked like a setting that did nothing.
    el.querySelectorAll('input[type="checkbox"][data-key]').forEach((inp) =>
      inp.addEventListener("change", () => save(false)));
  }

  function renderSettings(view) {
    const el = $("lobby-settings");
    if (!el) return;
    const isHost = view.hostId === youId;
    if (!isHost) editing = false;

    const actions = $("lobby-rules-actions");
    if (actions) {
      actions.innerHTML = "";
      if (isHost && !editing) {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "btn-ghost btn-sm";
        edit.innerHTML = icon("pencil") + "Edit";
        edit.addEventListener("click", () => { editing = true; renderSettings(view); });
        actions.appendChild(edit);
      }
    }

    // While the host is editing, leave the form alone: a roster change or a
    // settings broadcast must not wipe what they are typing.
    if (editing && el.dataset.mode === "edit") return;
    el.innerHTML = "";
    if (editing) {
      el.dataset.mode = "edit";
      buildEditor(view, el);
    } else {
      el.dataset.mode = "summary";
      renderSummary(view, el);
      const note = document.createElement("p");
      note.className = "settings-note";
      note.textContent = isHost ? "You're the host — tap Edit to change these before you start."
                                : "Set by " + hostName(view) + ".";
      el.appendChild(note);
    }
  }

  // ---- add bot ----
  // A computer player can be seated in any room, not just a solo one: three
  // friends and two bots is a better game than three friends alone. The roster
  // and the caps are injected with the page (see app.py) because they are static
  // platform data; the server re-checks everything the picker sends.
  const ROSTER = window.BOT_ROSTER || [];
  const MAX_BOTS = window.MAX_BOTS || 0;
  const MAX_PLAYERS = window.MAX_PLAYERS || 0;

  function botCount(view) {
    return view.players.filter((p) => p.is_bot).length;
  }

  /* Why the host cannot add one right now, or "" if they can. Returned as the
     reason rather than a boolean so the button can say what is wrong instead of
     being mysteriously dead. */
  function addBotBlockedBecause(view) {
    if (!ROSTER.length) return "Computer players are unavailable";
    if (MAX_PLAYERS && view.players.length >= MAX_PLAYERS) return "The table is full";
    if (botCount(view) >= MAX_BOTS) return "Max " + MAX_BOTS + " computer players";
    return "";
  }

  function closeBotPicker() {
    const menu = $("bot-picker");
    if (menu) menu.remove();
  }

  function openBotPicker(anchor, view) {
    closeBotPicker();
    const seated = new Set(view.players.map((p) => p.name));
    const menu = document.createElement("div");
    menu.className = "bot-picker";
    menu.id = "bot-picker";
    menu.setAttribute("role", "menu");

    ROSTER.forEach((bot) => {
      const opt = document.createElement("button");
      opt.type = "button";
      opt.className = "bot-opt";
      opt.setAttribute("role", "menuitem");
      opt.innerHTML =
        '<span class="bot-face">' + (SS.avatarFace ? SS.avatarFace(bot.name, bot.avatar) : "") + "</span>" +
        '<span class="bot-name"></span>';
      opt.querySelector(".bot-name").textContent = bot.name;
      /* Already at the table? Still selectable — the cap is five and the roster
         is five too, but a name has to be reusable. The server numbers the repeat. */
      if (seated.has(bot.name)) {
        const tag = document.createElement("span");
        tag.className = "bot-seated";
        tag.textContent = "seated";
        opt.appendChild(tag);
      }
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        socket.emit("add_bot", { code, user_id: youId, bot: bot.key });
        closeBotPicker();
      });
      menu.appendChild(opt);
    });

    anchor.parentNode.appendChild(menu);
    /* One-shot dismissal, so the picker never outlives the click that opened it. */
    setTimeout(() => document.addEventListener("click", closeBotPicker, { once: true }), 0);
  }

  function renderAddBot(view) {
    const slot = $("lobby-addbot");
    if (!slot) return;
    closeBotPicker();
    slot.innerHTML = "";
    if (view.hostId !== youId || !ROSTER.length) return;
    const wrap = document.createElement("div");
    wrap.className = "add-bot-wrap";

    const btn = document.createElement("button");
    btn.className = "btn-ghost btn-sm add-bot-btn";
    btn.id = "add-bot-btn";
    const blocked = addBotBlockedBecause(view);
    btn.innerHTML = icon("bot") + "Add computer";
    if (blocked) {
      btn.disabled = true;
      btn.title = blocked;
    } else {
      const n = botCount(view);
      btn.title = n ? n + " of " + MAX_BOTS + " computer players seated" : "Seat a computer player";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if ($("bot-picker")) { closeBotPicker(); return; }
        openBotPicker(btn, view);
      });
    }
    wrap.appendChild(btn);
    slot.appendChild(wrap);
  }

  // ---- shuffle seats (host option) ----
  // One switch, sent with the start: the server reorders the roster before the
  // deal (game/core/seating.py), so every game's own turn order comes out
  // shuffled. Kept in a module variable because the start bar is rebuilt on
  // every roster change and the host's choice must survive that.
  let shuffleNext = false;

  function shuffleOption(onChange) {
    const label = document.createElement("label");
    label.className = "shuffle-opt";
    label.title = "Deal everyone into a random seat order";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "switch";
    box.setAttribute("role", "switch");
    box.checked = shuffleNext;
    box.addEventListener("change", () => { shuffleNext = box.checked; if (onChange) onChange(); });
    const text = document.createElement("span");
    text.innerHTML = icon("shuffle") + "Shuffle seats";
    label.append(box, text);
    return label;
  }

  // Everyone hears about a shuffle, whichever game this is.
  if (socket) socket.on("seats_shuffled", (d) => {
    const names = ((d && d.order) || []).map((p) => (p.user_id === youId ? "You" : p.name));
    showToast("Seats shuffled", 2200);
    if (window.ActionLog && names.length) {
      window.ActionLog.push("Seats shuffled: " + names.join(" → "), "system");
    }
  });

  // Tell a player when the host role lands on them mid-game (the host's socket
  // dropped and the server moved it). Otherwise the table can sit waiting on
  // someone who has no idea they now hold the Next round button.
  let knownHost = null;
  function onRoster(d) {
    if (!d || !d.host_id) return;
    const me = window.Identity && window.Identity.userId();
    if (knownHost && d.host_id !== knownHost && d.host_id === me) {
      showToast("You're the host now", 3200, "success");
    }
    knownHost = d.host_id;
  }
  if (socket) {
    socket.on("player_list", onRoster);
    socket.on("room_joined", onRoster);
  }

  // ---- start bar ----
  function renderStart(view) {
    const startRow = $("start-row");
    if (!startRow) return;
    startRow.innerHTML = "";
    const inner = document.createElement("div");
    inner.className = "start-bar-inner";
    if (view.hostId === youId) {
      inner.appendChild(shuffleOption());
      const btn = document.createElement("button");
      btn.className = "btn-primary btn-lg start-btn";
      btn.innerHTML = icon("play") + "Start game";
      const enough = view.players.filter((p) => p.connected && !p.is_spectator).length >= MIN_PLAYERS;
      if (!enough) {
        btn.disabled = true;
        btn.title = "Need at least " + MIN_PLAYERS + " players";
      }
      btn.addEventListener("click", () => {
        btn.classList.add("is-loading");
        socket.emit("start_game", { code, user_id: youId, shuffle: shuffleNext });
        setTimeout(() => btn.classList.remove("is-loading"), 2500);
      });
      inner.appendChild(btn);
    } else {
      const p = document.createElement("p");
      p.className = "waiting";
      p.innerHTML = '<span class="waiting-dot" aria-hidden="true"></span>';
      p.appendChild(document.createTextNode("Waiting for " + hostName(view) + " to start the game"));
      inner.appendChild(p);
    }
    startRow.appendChild(inner);
  }

  function render(view) {
    renderInvite(view);
    renderRoster(view);
    renderAddBot(view);
    renderSettings(view);
    renderStart(view);
  }

  SS.Lobby = { init, render, setTab, shuffleOption, shuffleChosen: () => shuffleNext };
})();
