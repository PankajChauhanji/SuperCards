// Screen Wake Lock — keep the phone awake while a game is on screen.
//
// A card game has long stretches where you are watching rather than tapping,
// so the default screen timeout kills the table mid-round while you wait for
// someone else's turn.
//
// The browser always releases the lock when the page is hidden, so it has to be
// re-acquired on every return to visibility — holding a reference is not enough.
//
// Requires a secure context (https, or localhost in development). Unsupported
// or denied is a non-event: the screen simply behaves as it did before.
(function () {
  if (!("wakeLock" in navigator)) return;
  /* Only rooms need it — the landing page has no reason to hold a lock. */
  if (!/^\/room\//.test(location.pathname)) return;

  let lock = null;

  async function acquire() {
    if (document.visibilityState !== "visible" || lock) return;
    try {
      lock = await navigator.wakeLock.request("screen");
      /* Fires on tab-hide and on OS-level revocation (e.g. battery saver). */
      lock.addEventListener("release", () => {
        lock = null;
      });
    } catch {
      /* Denied — low battery or device policy. Nothing to recover from. */
      lock = null;
    }
  }

  document.addEventListener("visibilitychange", acquire);
  acquire();

  window.SS = window.SS || {};
  window.SS.wakeLock = {
    acquire,
    get held() {
      return !!lock;
    },
  };
})();
