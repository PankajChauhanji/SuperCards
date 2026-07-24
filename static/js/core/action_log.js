// Generic Action History — reusable across all game variants.
// Any game can call  window.ActionLog.push(message, type)  and the sidebar
// log area updates automatically, newest at the bottom.
//
// type: "info" (default) | "play" | "pass" | "challenge" | "win" | "system"
(function () {
  const MAX_ENTRIES = 200;
  const entries = [];
  let container = null;

  const ICONS = {
    info:      "ℹ️",
    play:      "🃏",
    pass:      "⏭️",
    challenge: "👀",
    win:       "🏆",
    system:    "⚙️",
  };

  function init() {
    container = document.getElementById("action-log-list");
  }

  function timestamp() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  function push(message, type) {
    type = type || "info";
    if (!container) init();
    if (!container) return;       // table not rendered yet

    const entry = { message, type, time: timestamp() };
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries.shift();

    const li = document.createElement("li");
    li.className = "al-entry al-" + type;

    const icon = document.createElement("span");
    icon.className = "al-icon";
    icon.textContent = ICONS[type] || ICONS.info;

    const text = document.createElement("span");
    text.className = "al-text";
    text.textContent = message;

    const ts = document.createElement("span");
    ts.className = "al-time";
    ts.textContent = entry.time;

    li.appendChild(icon);
    li.appendChild(text);
    li.appendChild(ts);
    container.appendChild(li);

    // Auto-scroll to newest entry
    container.scrollTop = container.scrollHeight;
  }

  function clear() {
    entries.length = 0;
    if (container) container.innerHTML = "";
  }

  window.ActionLog = { push, clear, init };
})();
