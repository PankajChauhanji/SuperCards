// Generic Action History feed — reusable across all game variants.
// Any game calls  window.ActionLog.push(message, type, opts)  and the sidebar
// Action History area updates automatically, newest at the bottom.
//
// type: "info" (default) | "play" | "pass" | "challenge" | "win" | "system"
// opts (optional): { actor: <player name>, colorIndex: <player.color> }
//   When `actor` is given, the name is coloured and shown at the start of the
//   message (and de-duplicated if the message already begins with it).
(function () {
  const MAX_ENTRIES = 200;
  const entries = [];
  let container = null;

  // Stable per-player identity colours — kept in sync with seven/table.js PALETTE
  // so a player's name colour here matches their swatch on the table.
  const PALETTE = ["#4ea1ff", "#ff9f43", "#a98cf0", "#f06ea9", "#43c6c6", "#d6c04a"];

  // A little emoji per event type keeps the feed lively and readable at a glance.
  const ICONS = {
    info:      "💬",
    play:      "🃏",
    pass:      "😴",
    challenge: "👀",
    win:       "🏆",
    system:    "✨",
  };

  function init() {
    container = document.getElementById("action-log-list");
  }

  function colorFor(idx) {
    if (typeof idx !== "number" || idx < 0) return null;
    return PALETTE[idx % PALETTE.length];
  }

  function push(message, type, opts) {
    type = type || "info";
    opts = opts || {};
    if (!container) init();
    if (!container) return;       // table not rendered yet

    // Split the actor's name out of the front of the message so it can be
    // coloured; if the message doesn't start with the name, leave it whole.
    const actor = opts.actor || null;
    let body = message == null ? "" : String(message);
    if (actor && body.slice(0, actor.length) === actor) {
      body = body.slice(actor.length).replace(/^\s+/, "");
    }

    entries.push({ message, type });
    if (entries.length > MAX_ENTRIES) {
      entries.shift();
      if (container.firstChild) container.removeChild(container.firstChild);
    }

    const li = document.createElement("li");
    li.className = "al-entry al-" + type;

    const icon = document.createElement("span");
    icon.className = "al-icon";
    icon.textContent = ICONS[type] || ICONS.info;
    li.appendChild(icon);

    const text = document.createElement("span");
    text.className = "al-text";
    if (actor) {
      const who = document.createElement("span");
      who.className = "al-actor";
      who.textContent = (window.SS && window.SS.shortName) ? window.SS.shortName(actor) : actor;
      const col = colorFor(opts.colorIndex);
      if (col) who.style.color = col;
      text.appendChild(who);
      if (body) text.appendChild(document.createTextNode(" " + body));
    } else {
      text.textContent = body;
    }
    li.appendChild(text);

    container.appendChild(li);
    // Auto-scroll to newest; users can scroll up for past messages.
    container.scrollTop = container.scrollHeight;
  }

  function clear() {
    entries.length = 0;
    if (container) container.innerHTML = "";
  }

  window.ActionLog = { push, clear, init, PALETTE };
})();
