// The Settings sheet (templates/partials/settings_sheet.html).
//
// Opened by the topbar gear at every width: a right-hand drawer on desktop, a
// bottom sheet on phones (settings.css decides which). This module owns only
// opening and closing, plus the sound switch; the deck, hand-view and theme
// sections are wired by their own modules (deck.js, view_mode.js, themes.js),
// and Leave table by quit.js, exactly as when they lived in the topbar.
(function () {
  const SS = window.SS || (window.SS = {});
  const sheet = document.getElementById("settings-sheet");
  const backdrop = document.getElementById("settings-backdrop");
  const openBtn = document.getElementById("settings-btn");
  if (!sheet || !backdrop || !openBtn) return;

  let lastFocus = null;

  function isOpen() { return !sheet.hidden; }

  function open() {
    if (isOpen()) return;
    lastFocus = document.activeElement;
    sheet.hidden = false;
    backdrop.hidden = false;
    // Next frame, so the transition runs from the closed position.
    requestAnimationFrame(() => {
      sheet.classList.add("open");
      backdrop.classList.add("open");
    });
    openBtn.setAttribute("aria-expanded", "true");
    const close = document.getElementById("settings-close");
    if (close) close.focus({ preventScroll: true });
  }

  function close() {
    if (!isOpen()) return;
    sheet.classList.remove("open");
    backdrop.classList.remove("open");
    openBtn.setAttribute("aria-expanded", "false");
    // Hide after the slide-out; a hidden preview pane runs no transitions, so
    // a timer rather than transitionend keeps it from sticking open there.
    setTimeout(() => {
      if (sheet.classList.contains("open")) return;
      sheet.hidden = true;
      backdrop.hidden = true;
    }, 220);
    if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
  }

  openBtn.addEventListener("click", () => (isOpen() ? close() : open()));
  backdrop.addEventListener("click", close);
  const closeBtn = document.getElementById("settings-close");
  if (closeBtn) closeBtn.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen()) close();
  });

  // Rules and Install open their own dialogs (rules_modal.js wires both);
  // step aside for them.
  const rulesLink = document.getElementById("rules-btn");
  if (rulesLink) rulesLink.addEventListener("click", close);
  const installLink = document.getElementById("install-help-link");
  if (installLink) installLink.addEventListener("click", close);

  // ---- sound: the topbar button and this switch are the same setting ----
  const muteBtn = document.getElementById("mute-btn");
  const muteSwitch = document.getElementById("mute-switch");
  function paintSound() {
    if (!SS.sound) return;
    const on = !SS.sound.muted();
    if (muteSwitch) muteSwitch.checked = on;
    if (muteBtn) {
      muteBtn.innerHTML = SS.icon ? SS.icon(on ? "volume" : "volume-off") : (on ? "On" : "Off");
      muteBtn.setAttribute("aria-pressed", on ? "false" : "true");
      muteBtn.title = on ? "Sound on" : "Sound off";
    }
  }
  if (SS.sound) {
    if (muteBtn) muteBtn.addEventListener("click", () => { SS.sound.toggleMute(); paintSound(); });
    if (muteSwitch) muteSwitch.addEventListener("change", () => {
      if (muteSwitch.checked === SS.sound.muted()) SS.sound.toggleMute();
      paintSound();
    });
    paintSound();
  }

  SS.settings = { open, close, isOpen };
})();
