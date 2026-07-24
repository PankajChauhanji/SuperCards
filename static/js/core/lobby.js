// Shared lobby renderer — reused by every game variant.
//
// The lobby is identical across games except for the *settings schema* (which
// fields, their labels and bounds). A game calls:
//     window.SS.Lobby.init({ youId, fields })   // once, with its settings schema
//     window.SS.Lobby.render(view)              // on every roster/settings change
// and this module owns the Players/Settings tabs, the roster (with host-only
// kick), the settings panel (host-editable or read-only), and the Start control.
//
// `fields` is an array of { key, label, min?, max? }. `view` supplies
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
      if (p.is_bot) tags.appendChild(badge("Bot", "you"));
      // Host may remove anyone but themselves and the bot.
      if (isHost && p.user_id !== youId && !p.is_bot) {
        const kick = document.createElement("button");
        kick.className = "kick-btn";
        kick.setAttribute("aria-label", "Remove " + p.name);
        kick.title = "Remove " + p.name;
        kick.innerHTML = "&#10005;";
        kick.addEventListener("click", () => {
          if (confirm("Remove " + p.name + " from the room?")) {
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
          inp.addEventListener("input", () => { inp.dataset.dirty = "1"; }));
        const save = $("lobby-save-settings");
        if (save) save.addEventListener("click", () => {
          const out = {};
          el.querySelectorAll("input[data-key]").forEach((inp) => {
            if (inp.value !== "") out[inp.dataset.key] = parseInt(inp.value, 10);
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
      if (node.tagName === "INPUT") {
        if (node !== document.activeElement && !node.dataset.dirty) node.value = val;
      } else {
        node.textContent = val || "—";
      }
    });
  }

  // ---- start / waiting ----
  function renderStart(view) {
    const startRow = $("start-row");
    if (!startRow) return;
    startRow.innerHTML = "";
    if (view.hostId === youId) {
      const btn = document.createElement("button");
      btn.className = "btn-primary";
      btn.textContent = "Start game";
      btn.addEventListener("click", () => socket.emit("start_game", { code, user_id: youId }));
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

  SS.Lobby = { init, render, setTab };
})();
