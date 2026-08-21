/* Mobile table sheet — Scores + Action history behind one button.
 *
 * Below 720px the two collapsed panels cost ~104px above the felt before a
 * card is dealt, while the seats already show every player's score. This moves
 * them into a bottom sheet reached from a single button, and gives the felt the
 * space back. Above 720px this module does nothing: the desktop side column is
 * the right design there and is left untouched.
 *
 * Why it needed no per-game changes
 * ---------------------------------
 * All three table partials ship the *same* scoreboard markup and ids
 * (#sb-players, #score-list, #action-log, #action-log-list, …). So rather than
 * rendering a second copy of each panel — which would mean touching every
 * game's render path and keeping two views in step — this relocates the
 * existing DOM nodes into the sheet and puts them back on desktop. Every game
 * keeps writing to the same ids and does not know this happened.
 *
 * The button is inserted into .reaction-dock: that corner is already the one
 * spot proven clear of the hand tray on every felt (see reactions.css), and
 * each game bundle already reveals the dock when the table appears, so the
 * button inherits correct show/hide timing for free.
 */
(function () {
  const SS = (window.SS = window.SS || {});

  const BREAKPOINT = "(max-width: 720px)";
  const TAB_KEY = "ss_table_sheet_tab";

  const scoreboard = document.querySelector(".scoreboard");
  const scoresPanel = document.getElementById("sb-players");
  const logPanel = document.getElementById("action-log");
  // Not a table page (or a variant without the shared scoreboard): stay out.
  if (!scoreboard || !scoresPanel || !logPanel) return;

  // ---- build ------------------------------------------------------------
  const backdrop = document.createElement("div");
  backdrop.className = "ts-backdrop";
  backdrop.hidden = true;

  const sheet = document.createElement("div");
  sheet.className = "ts-sheet";
  sheet.id = "table-sheet";
  sheet.hidden = true;
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-label", "Scores and action history");
  sheet.innerHTML =
    '<div class="ts-grip" aria-hidden="true"></div>' +
    '<div class="ts-tabs" role="tablist">' +
    '<button class="ts-tab active" type="button" role="tab" data-tab="scores" aria-selected="true">Scores</button>' +
    '<button class="ts-tab" type="button" role="tab" data-tab="history" aria-selected="false">' +
    'History<span class="ts-dot" id="ts-tab-dot" hidden></span></button>' +
    '<button class="ts-close" type="button" aria-label="Close">&#10006;</button>' +
    "</div>" +
    '<div class="ts-body" id="ts-body"></div>';

  document.body.appendChild(backdrop);
  document.body.appendChild(sheet);

  const body = sheet.querySelector("#ts-body");
  const tabs = Array.from(sheet.querySelectorAll(".ts-tab"));
  const tabDot = sheet.querySelector("#ts-tab-dot");

  const fab = document.createElement("button");
  fab.className = "ts-fab";
  fab.id = "table-sheet-fab";
  fab.type = "button";
  fab.title = "Scores & action history";
  fab.setAttribute("aria-label", "Scores and action history");
  fab.setAttribute("aria-expanded", "false");
  fab.setAttribute("aria-controls", "table-sheet");
  fab.innerHTML =
    '<span aria-hidden="true">&#127942;</span><span class="ts-fab-dot" id="ts-fab-dot" hidden></span>';
  const fabDot = fab.querySelector("#ts-fab-dot");

  const dock = document.getElementById("reaction-dock");
  const rxFab = document.getElementById("reaction-fab");
  if (dock && rxFab) {
    // Above the reactions button, so reactions keeps the spot muscle memory
    // already knows.
    dock.insertBefore(fab, rxFab);
  } else {
    fab.classList.add("ts-fab-standalone");
    document.body.appendChild(fab);
  }

  // ---- state ------------------------------------------------------------
  let isMobile = false;
  let isOpen = false;
  let tab = sessionStorage.getItem(TAB_KEY) === "history" ? "history" : "scores";
  let unread = false;

  function showTab(next) {
    tab = next === "history" ? "history" : "scores";
    try { sessionStorage.setItem(TAB_KEY, tab); } catch (e) { /* private mode */ }
    // Clear the collapse class every time, not just once at adopt(): action_log.js
    // collapses the log on DOMContentLoaded, which lands *after* this component
    // has already run, and chrome.js lets a player collapse Scores on desktop
    // before narrowing the window. Either way the class must not survive into a
    // tab. table_sheet.css also overrides the collapsed styling, so a stale class
    // cannot blank a tab even if something re-adds it after this point.
    scoresPanel.classList.remove("is-collapsed");
    logPanel.classList.remove("is-collapsed");
    tabs.forEach((btn) => {
      const on = btn.dataset.tab === tab;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", String(on));
    });
    scoresPanel.style.display = tab === "scores" ? "" : "none";
    logPanel.style.display = tab === "history" ? "" : "none";
    if (tab === "history") clearUnread();
  }

  function setUnread(on) {
    unread = on;
    fabDot.hidden = !on;
    tabDot.hidden = !on;
  }
  function clearUnread() { if (unread) setUnread(false); }

  function setOpen(next) {
    isOpen = !!next && isMobile;
    sheet.hidden = !isOpen;
    backdrop.hidden = !isOpen;
    fab.setAttribute("aria-expanded", String(isOpen));
    document.body.classList.toggle("ss-sheet-open", isOpen);
    if (isOpen) showTab(tab);
  }

  // ---- adopt / release --------------------------------------------------
  function adopt() {
    body.appendChild(scoresPanel);
    body.appendChild(logPanel);
    // The tabs are the affordance in here, so any collapsed state left by
    // action_log.js / chrome.js would just hide the tab's own content.
    scoresPanel.classList.remove("is-collapsed");
    logPanel.classList.remove("is-collapsed");
    document.body.classList.add("ss-sheet-on");
    showTab(tab);
  }

  function release() {
    setOpen(false);
    // Original document order: scores above the log.
    scoreboard.appendChild(scoresPanel);
    scoreboard.appendChild(logPanel);
    scoresPanel.style.display = "";
    logPanel.style.display = "";
    document.body.classList.remove("ss-sheet-on");
    setUnread(false);
  }

  function applyMode(matches) {
    if (matches === isMobile) return;
    isMobile = matches;
    if (isMobile) adopt(); else release();
  }

  // ---- wiring ----------------------------------------------------------
  fab.addEventListener("click", () => setOpen(!isOpen));
  backdrop.addEventListener("click", () => setOpen(false));
  sheet.querySelector(".ts-close").addEventListener("click", () => setOpen(false));
  tabs.forEach((btn) => btn.addEventListener("click", () => showTab(btn.dataset.tab)));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) setOpen(false);
  });

  // New log entries while the sheet is closed (or while Scores is showing)
  // raise the unread dot. Watching the list rather than hooking action_log.js
  // keeps this working for any game that appends to it, including future ones.
  const logList = document.getElementById("action-log-list");
  if (logList && "MutationObserver" in window) {
    new MutationObserver(() => {
      if (!isMobile) return;
      if (isOpen && tab === "history") return;
      setUnread(true);
    }).observe(logList, { childList: true });
  }

  // Get out of the way when it becomes your turn: a sheet is welcome while you
  // wait and wrong the moment you have to act. `.my-seat.active` is set by
  // core/seats.js from each game's own is-my-turn flag.
  //
  // Super 4 renders its own seats and has no #myseat, so there it closes on the
  // first tap outside instead — acceptable, since its action bar sits inside
  // the felt rather than under the sheet.
  const mySeat = document.getElementById("myseat");
  if (mySeat && "MutationObserver" in window) {
    let wasMyTurn = false;
    new MutationObserver(() => {
      const myTurn = !!mySeat.querySelector(".my-seat.active");
      if (myTurn && !wasMyTurn && isOpen) setOpen(false);
      wasMyTurn = myTurn;
    }).observe(mySeat, { childList: true, subtree: true });
  }

  // Breakpoint tracking, deliberately from more than one signal. The CSS side
  // of this feature re-evaluates on any viewport change, but a missed
  // matchMedia `change` event would leave the panels stranded in the sheet
  // while the desktop column renders empty and still offsets the felt — a
  // visible, confusing break rather than a silent one. reactions.js hedges the
  // same way (a ResizeObserver plus an explicit resize listener), so this
  // follows the pattern already established here: re-read mq.matches on every
  // signal, and let applyMode's own guard make repeat calls free.
  const mq = window.matchMedia(BREAKPOINT);
  const sync = () => applyMode(mq.matches);

  sync();
  if (mq.addEventListener) mq.addEventListener("change", sync);
  else if (mq.addListener) mq.addListener(sync);   // older mobile Safari
  window.addEventListener("resize", sync);
  window.addEventListener("orientationchange", sync);

  SS.tableSheet = {
    open: () => setOpen(true),
    close: () => setOpen(false),
    showTab: showTab,
    isMobile: () => isMobile,
  };
})();
