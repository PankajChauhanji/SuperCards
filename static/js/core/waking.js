// First-connect loading screen.
//
// The host sleeps when idle and takes ~20-50s to wake. The service worker can
// now paint the landing page from cache immediately, which means the player sees
// a complete, fully-styled UI that simply cannot do anything yet — arguably worse
// than a blank screen, because it looks broken rather than loading.
//
// This covers that gap: while the socket is still making its first connection,
// show a branded screen with something to read. Reconnects mid-session are NOT
// handled here — core/connection.js owns those with a much lighter banner.
(function () {
  const socket = window.SS && window.SS.socket;
  if (!socket) return;

  /* Already connected by the time we ran: nothing to cover. */
  if (socket.connected) return;

  const SHOW_AFTER = 1200; // don't flash on a warm server
  const TIP_EVERY = 3800;
  const EXPLAIN_AFTER = 9000; // be honest once it's clearly not instant
  const RETRY_AFTER = 45000;

  const GENERAL_TIPS = [
    "Tip: the room code is all a friend needs to join — share it from the lobby.",
    "Tip: you can play against the computer any time with “Play with computer”.",
    "Tip: tap the table theme picker to change the felt.",
    "Tip: react with emoji mid-game from the corner button.",
  ];

  const GAME_TIPS = {
    super_seven: [
      "Super 7: reaching exactly zero makes you Safe for the round.",
      "Super 7: calling Stop when you're not lowest is expensive — count first.",
      "Super 7: pairs, sets and sequences let you shed several cards at once.",
    ],
    super_four: [
      "Super 4: the King of Hearts is worth −1. Hold onto it.",
      "Super 4: 7s and 8s peek at your own cards; 9s and 10s peek at someone else's.",
      "Super 4: you only remember what you've actually seen — so watch the swaps.",
    ],
    bluff: [
      "Bluff: only the next player can call Show on you.",
      "Bluff: if everyone passes, the pile is swept away for good.",
      "Bluff: telling the truth early buys you a bigger lie later.",
    ],
  };

  const tips = GENERAL_TIPS.concat(GAME_TIPS[window.GAME_TYPE] || []);

  let el = null;
  let tipTimer = null;
  let showTimer = null;
  let explainTimer = null;
  let retryTimer = null;
  let done = false;

  function build() {
    el = document.createElement("div");
    el.id = "waking";
    el.setAttribute("role", "status");
    el.innerHTML =
      '<div class="waking-inner">' +
      '<div class="waking-cards"><i></i><i></i><i></i></div>' +
      '<p class="waking-title">Shuffling the deck…</p>' +
      '<p class="waking-tip"></p>' +
      '<p class="waking-note"></p>' +
      '<button type="button" class="waking-retry" hidden>Reload</button>' +
      "</div>";
    document.body.appendChild(el);

    el.querySelector(".waking-retry").addEventListener("click", () => {
      location.reload();
    });

    /* Start on a random tip so a repeated cold start isn't identical each time. */
    let i = Math.floor(Math.random() * tips.length);
    const tipEl = el.querySelector(".waking-tip");
    const paint = () => {
      tipEl.textContent = tips[i % tips.length];
      i += 1;
    };
    paint();
    tipTimer = setInterval(paint, TIP_EVERY);

    explainTimer = setTimeout(() => {
      if (!el) return;
      el.querySelector(".waking-note").textContent =
        "The server naps when nobody's playing — waking it up now. This can take up to a minute.";
    }, EXPLAIN_AFTER - SHOW_AFTER);

    retryTimer = setTimeout(() => {
      if (!el) return;
      el.querySelector(".waking-retry").hidden = false;
    }, RETRY_AFTER - SHOW_AFTER);
  }

  function teardown() {
    if (done) return;
    done = true;
    clearTimeout(showTimer);
    clearTimeout(explainTimer);
    clearTimeout(retryTimer);
    clearInterval(tipTimer);
    if (el) {
      el.classList.add("waking-out");
      const node = el;
      el = null;
      setTimeout(() => node.remove(), 260);
    }
  }

  showTimer = setTimeout(() => {
    if (!done && !socket.connected) build();
  }, SHOW_AFTER);

  socket.on("connect", teardown);

  window.SS = window.SS || {};
  window.SS.waking = { dismiss: teardown };
})();
