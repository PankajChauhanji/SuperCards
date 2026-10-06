// Shared lobby renderer — reused by every game variant.
//
// The lobby is identical across games except for the *settings schema* (which
// fields, their labels and bounds). A game calls:
//     window.SS.Lobby.init({ youId, fields })   // once, with its settings schema
//     window.SS.Lobby.render(view)              // on every roster/settings change
// and this module owns the Players/Settings tabs, the roster (with host-only
// kick), the settings panel (host-editable or read-only), the Add-bot control,
// and the Start control.
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

  // Stable per-player swatch colours (match the table/action-log palette).
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];

  let youId = null;
  let fields = [];
  let wired = false;

  const $ = (id) => document.getElementById(id);

  function init(opts) {
    opts = opts || {};
    youId = opts.youId || (window.Identity && window.Identity.userId()) || null;
    fields = opts.fields || [];
    wireTabsOnce();
  }

  // ---- tabs ----
  function wireTabsOnce() {
    if (wired) return;
    const tabs = document.querySelectorAll(".lobby-tab");
    if (!tabs.length) return;
    wired = true;
    tabs.forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tab)));
  }
  function setTab(tab) {
    document.querySelectorAll(".lobby-tab").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".lobby-panel").forEach((p) => {
      p.classList.toggle("hidden", p.dataset.panel !== tab);
    });
    const tabsEl = document.querySelector(".lobby-tabs");
    if (tabsEl) tabsEl.classList.toggle("pos-settings", tab === "settings");
  }

  function badge(text, cls) {
    const b = document.createElement("span");
    b.className = "badge " + cls;
    b.textContent = text;
    return b;
  }

  // ---- roster ----
  function renderRoster(view) {
    const rosterEl = $("roster");
    if (!rosterEl) return;
    const isHost = view.hostId === youId;
    rosterEl.innerHTML = "";
    view.players.forEach((p) => {
      const li = document.createElement("li");

      const who = document.createElement("div");
      who.className = "who";
      const sw = document.createElement("span");
      sw.className = "swatch";
      sw.style.background = PALETTE[(p.color || 0) % PALETTE.length];
      const dot = document.createElement("span");
      dot.className = "dot" + (p.connected ? " on" : "");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = p.name;
      who.append(sw, dot, name);

      const tags = document.createElement("div");
      tags.className = "roster-tags";
      if (p.user_id === view.hostId) tags.appendChild(badge("Host", "host"));
      if (p.user_id === youId) tags.appendChild(badge("You", "you"));
      // Computer players render exactly like regular players in the roster —
      // no "Bot" tag — so the table reads as a table, not a lineup of extras.
      // Host may remove anyone but themselves — including a bot they seated,
      // which is the only way to undo an Add-bot before the game starts.
      if (isHost && p.user_id !== youId) {
        const kick = document.createElement("button");
        kick.className = "kick-btn";
        kick.setAttribute("aria-label", "Remove " + p.name);
        kick.title = "Remove " + p.name;
        kick.innerHTML = "&#10005;";
        kick.addEventListener("click", () => {
          // No confirm for a bot: seating one is a click, so removing one should
          // be too. Removing a person is not undoable for them, so that keeps it.
          if (p.is_bot || confirm("Remove " + p.name + " from the room?")) {
            socket.emit("kick_player", { code, user_id: youId, target: p.user_id });
          }
        });
        tags.appendChild(kick);
      }

      li.append(who, tags);
      rosterEl.appendChild(li);
    });

    const n = view.players.length;
    const meta = $("lobby-meta");
    if (meta) meta.textContent = n + (n === 1 ? " player" : " players") + " in the room";
    const count = $("players-count");
    if (count) count.textContent = n;
  }

  // ---- settings (built once per role, then value-synced) ----
  function renderSettings(view) {
    const el = $("lobby-settings");
    if (!el) return;
    const isHost = view.hostId === youId;
    const s = view.settings || {};
    const mode = isHost ? "host" : "guest";

    // Rebuild the panel only when the role changes, so a roster refresh never
    // wipes the host's in-progress edits.
    if (el.dataset.mode !== mode) {
      el.dataset.mode = mode;
      let html = '<p class="settings-note">' +
        (isHost ? "Tune the round, then start when everyone's in."
                : "Round settings (set by the host)") + "</p>";
      html += '<div class="lobby-settings-grid">';
      fields.forEach((f) => {
        if (f.type === "toggle") {
          html += '<label class="set-item set-toggle"><span class="set-label">' + f.label + "</span>" +
            (isHost
              ? '<input type="checkbox" role="switch" class="set-switch" data-key="' + f.key + '" />'
              : '<span class="set-val" data-key="' + f.key + '"></span>') +
            "</label>";
          return;
        }
        const bounds = (f.min != null ? ' min="' + f.min + '"' : "") +
                       (f.max != null ? ' max="' + f.max + '"' : "");
        html += '<label class="set-item"><span class="set-label">' + f.label + "</span>" +
          (isHost
            ? '<input type="number" data-key="' + f.key + '"' + bounds + " />"
            : '<span class="set-val" data-key="' + f.key + '"></span>') +
          "</label>";
      });
      html += "</div>";
      if (isHost) html += '<button class="btn-ghost set-save" id="lobby-save-settings">Save settings</button>';
      el.innerHTML = html;

      if (isHost) {
        el.querySelectorAll("input[data-key]").forEach((inp) =>
          ["input", "change"].forEach((ev) =>
            inp.addEventListener(ev, () => { inp.dataset.dirty = "1"; })));
        const save = $("lobby-save-settings");
        // A switch reads as instant, so it saves the moment it is flipped —
        // a flipped-but-unsaved switch looked like a setting that did nothing.
        // It saves the whole form (the server rebuilds settings from defaults,
        // so a partial update would reset the other fields).
        el.querySelectorAll('input[type="checkbox"][data-key]').forEach((inp) =>
          inp.addEventListener("change", () => { if (save) save.click(); }));
        if (save) save.addEventListener("click", () => {
          const out = {};
          el.querySelectorAll("input[data-key]").forEach((inp) => {
            if (inp.type === "checkbox") out[inp.dataset.key] = inp.checked ? 1 : 0;
            else if (inp.value !== "") out[inp.dataset.key] = parseInt(inp.value, 10);
            delete inp.dataset.dirty;
          });
          socket.emit("update_settings", { code, user_id: youId, settings: out });
          showToast("Settings saved");
        });
      }
    }

    // Sync values (skip an input the host is actively editing).
    fields.forEach((f) => {
      const node = el.querySelector('[data-key="' + f.key + '"]');
      if (!node) return;
      const val = s[f.key] != null ? String(s[f.key]) : "";
      if (f.type === "toggle") {
        const on = Number(s[f.key]) === 1;
        if (node.tagName === "INPUT") {
          if (!node.dataset.dirty) node.checked = on;
        } else {
          node.textContent = s[f.key] == null ? "—" : (on ? "On" : "Off");
        }
        return;
      }
      if (node.tagName === "INPUT") {
        if (node !== document.activeElement && !node.dataset.dirty) node.value = val;
      } else {
        node.textContent = val || "—";
      }
    });
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
        '<span class="bot-face" aria-hidden="true">' + (bot.gender === "f" ? "&#128105;" : "&#128104;") + "</span>" +
        '<span class="bot-name"></span>';
      opt.querySelector(".bot-name").textContent = bot.name;
      /* Already at the table? Still selectable — the cap is five and the roster
         is four, so a name has to be reusable. The server numbers the repeat. */
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

  function renderAddBot(view, startRow) {
    if (view.hostId !== youId || !ROSTER.length) return;
    const wrap = document.createElement("div");
    wrap.className = "add-bot-wrap";

    const btn = document.createElement("button");
    btn.className = "btn-ghost add-bot-btn";
    btn.id = "add-bot-btn";
    const blocked = addBotBlockedBecause(view);
    btn.textContent = "+ Add bot";
    if (blocked) {
      btn.disabled = true;
      btn.title = blocked;
    } else {
      btn.title = "Seat a computer player";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if ($("bot-picker")) { closeBotPicker(); return; }
        openBotPicker(btn, view);
      });
    }
    wrap.appendChild(btn);

    const note = document.createElement("span");
    note.className = "add-bot-note";
    const n = botCount(view);
    note.textContent = blocked || (n ? n + " of " + MAX_BOTS + " bots" : "");
    wrap.appendChild(note);

    startRow.appendChild(wrap);
  }

  // ---- shuffle seats (host option) ----
  // One checkbox, sent with the start: the server reorders the roster before the
  // deal (game/core/seating.py), so every game's own turn order comes out
  // shuffled. Kept in a module variable because the start row is rebuilt on
  // every roster change and the host's choice must survive that.
  let shuffleNext = false;

  function shuffleOption(onChange) {
    const label = document.createElement("label");
    label.className = "shuffle-opt";
    label.title = "Deal everyone into a random seat order";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = shuffleNext;
    box.addEventListener("change", () => { shuffleNext = box.checked; if (onChange) onChange(); });
    const text = document.createElement("span");
    text.textContent = "\uD83D\uDD00 Shuffle seats";
    label.append(box, text);
    return label;
  }

  // Everyone hears about a shuffle, whichever game this is.
  if (socket) socket.on("seats_shuffled", (d) => {
    const names = ((d && d.order) || []).map((p) => (p.user_id === youId ? "You" : p.name));
    showToast("\uD83D\uDD00 Seats shuffled", 2200);
    if (window.ActionLog && names.length) {
      window.ActionLog.push("\uD83D\uDD00 Seats shuffled: " + names.join(" \u2192 "), "system");
    }
  });

  // ---- start / waiting ----
  function renderStart(view) {
    const startRow = $("start-row");
    if (!startRow) return;
    closeBotPicker();
    startRow.innerHTML = "";
    renderAddBot(view, startRow);
    if (view.hostId === youId) {
      startRow.appendChild(shuffleOption());
      const btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.textContent = "Start game";
      btn.addEventListener("click", () =>
        socket.emit("start_game", { code, user_id: youId, shuffle: shuffleNext }));
      startRow.appendChild(btn);
    } else {
      const p = document.createElement("p");
      p.className = "waiting";
      p.textContent = "Waiting for the host to start…";
      startRow.appendChild(p);
    }
  }

  function render(view) {
    renderRoster(view);
    renderSettings(view);
    renderStart(view);
  }

  SS.Lobby = { init, render, setTab, shuffleOption, shuffleChosen: () => shuffleNext };
})();
