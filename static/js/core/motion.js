// Table motion and haptics — the moments that should feel physical.
//
//  * The deal: the first hand that arrives after a round starts is dealt in,
//    card by card (body.dealing, CSS in table.css). Later hand updates in the
//    same round — a draw, a throw — just appear, as they always did.
//  * Your turn: a short pulse on your seat (body.turn-arrived) and, on phones,
//    a short vibration. Both ride on SS.sound.turnPing(), which every game
//    already calls exactly when the turn passes to you, so no game had to learn
//    a new hook. The vibration ignores the sound mute (a muted phone in a
//    pocket is exactly when a buzz helps) and has its own switch in Settings.
//
// Everything visual is skipped under prefers-reduced-motion by the CSS.
(function () {
  const SS = window.SS || (window.SS = {});
  const socket = SS.socket;
  const body = document.body;

  // ---- the deal ----
  let dealArmed = false;
  let dealTimer = null;
  if (socket) {
    socket.on("round_start", () => { dealArmed = true; });
    socket.on("your_hand", (d) => {
      if (!dealArmed || !d || !(d.cards || []).length) return;
      dealArmed = false;
      body.classList.remove("dealing");
      void body.offsetWidth;          // restart if a deal is somehow still running
      body.classList.add("dealing");
      clearTimeout(dealTimer);
      // Long enough for the last card's delay plus its flight.
      dealTimer = setTimeout(() => body.classList.remove("dealing"), 1600);
    });
  }

  // ---- vibration preference ----
  const VIBE_KEY = "ss_vibrate";
  // Desktop Chrome exposes navigator.vibrate too and silently does nothing, so
  // the setting is offered only on touch devices, where it can actually buzz.
  const canVibrate = typeof navigator !== "undefined" && typeof navigator.vibrate === "function" &&
    !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
  function vibrateOn() {
    try { return localStorage.getItem(VIBE_KEY) !== "0"; } catch (e) { return true; }
  }
  const vibeRow = document.getElementById("vibrate-row");
  const vibeSwitch = document.getElementById("vibrate-switch");
  if (vibeRow) vibeRow.hidden = !canVibrate;
  if (vibeSwitch) {
    vibeSwitch.checked = vibrateOn();
    vibeSwitch.addEventListener("change", () => {
      try { localStorage.setItem(VIBE_KEY, vibeSwitch.checked ? "1" : "0"); } catch (e) {}
      if (vibeSwitch.checked && canVibrate) navigator.vibrate(30);   // a sample buzz
    });
  }

  // ---- your turn ----
  let turnTimer = null;
  function turnArrived() {
    body.classList.remove("turn-arrived");
    void body.offsetWidth;
    body.classList.add("turn-arrived");
    clearTimeout(turnTimer);
    turnTimer = setTimeout(() => body.classList.remove("turn-arrived"), 1400);
    // Chrome refuses (and logs an error for) a buzz before the player has
    // touched the page at all — e.g. the turn arriving right after a reload.
    const touched = !navigator.userActivation || navigator.userActivation.hasBeenActive;
    if (canVibrate && vibrateOn() && touched) {
      try { navigator.vibrate([35, 60, 35]); } catch (e) { /* not allowed yet */ }
    }
  }
  if (SS.sound && typeof SS.sound.turnPing === "function") {
    const ping = SS.sound.turnPing;
    SS.sound.turnPing = function () {
      turnArrived();
      return ping.apply(this, arguments);
    };
  }

  SS.motion = { turnArrived };
})();
