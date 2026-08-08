// Shared install experience — one-tap install where the browser supports it,
// platform-filtered manual steps everywhere else.
//
// Three runtime states drive the UI:
//   1. Already installed (standalone display-mode) — every install entry point
//      is hidden, so the footer link stops nagging people who already did it.
//   2. Browser offers a native prompt (beforeinstallprompt fired) — a real
//      "Install now" button; the manual steps stay as a collapsed fallback.
//   3. No native prompt (iOS Safari, unsupported browsers) — manual steps only,
//      filtered to the platform the visitor is actually on.
//
// Loaded from <head> rather than the usual bottom-of-body slot: Chrome fires
// beforeinstallprompt as soon as it has the manifest + service worker, which can
// beat a deferred script. The listener is attached at parse time; DOM wiring
// waits for DOMContentLoaded.
(function () {
  "use strict";

  let deferredPrompt = null;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.navigator.standalone === true /* iOS Safari */
    );
  }

  /* Only decides which manual steps to show — never gates functionality. */
  function platform() {
    const ua = navigator.userAgent || "";
    if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
    if (/Android/i.test(ua)) return "android";
    return "desktop";
  }

  /* ── Capture the native prompt (must be attached at parse time) ─────── */

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // suppress Chrome's own mini-infobar; we place our own
    deferredPrompt = event;
    paint();
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    paint();
  });

  /* ── Painting ──────────────────────────────────────────────────────── */

  function paint() {
    const installed = isStandalone();

    /* Footer entry point: pointless once the app is installed. */
    document.querySelectorAll(".footer-install").forEach((el) => {
      el.hidden = installed;
    });

    const nowRow = document.getElementById("install-now-row");
    const doneNote = document.getElementById("install-done-note");
    const manualIntro = document.getElementById("install-manual-intro");

    if (nowRow) nowRow.hidden = installed || !deferredPrompt;
    if (doneNote) doneNote.hidden = !installed;
    /* "Prefer to do it manually?" only makes sense next to a real button. */
    if (manualIntro) manualIntro.hidden = installed || !deferredPrompt;
  }

  /* Show only the steps for this platform. Desktop sees everything — someone on
     a laptop is often reading in order to help their phone. */
  function decorate(container) {
    if (!container) return;
    const here = platform();
    container.querySelectorAll("[data-platform]").forEach((section) => {
      const want = section.dataset.platform;
      section.hidden = !(
        want === "any" || here === "desktop" || want === here
      );
    });
    paint();
  }

  async function promptInstall() {
    if (!deferredPrompt) return "unavailable";
    const event = deferredPrompt;
    /* A prompt can only be used once — drop it before awaiting so a double
       tap can't fire it twice. */
    deferredPrompt = null;
    event.prompt();
    let outcome = "dismissed";
    try {
      ({ outcome } = await event.userChoice);
    } catch {
      /* Treat a thrown userChoice as a dismissal. */
    }
    paint();
    return outcome;
  }

  /* ── Wiring ────────────────────────────────────────────────────────── */

  function init() {
    const btn = document.getElementById("install-now-btn");
    if (btn) {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const outcome = await promptInstall();
        btn.disabled = false;
        if (outcome === "accepted") {
          const modal = document.getElementById("install-modal");
          if (modal) modal.classList.remove("open");
        }
      });
    }

    /* Chrome keeps standalone mode out of matchMedia until the PWA relaunches,
       but catching the change keeps a same-session install tidy. */
    window
      .matchMedia("(display-mode: standalone)")
      .addEventListener("change", paint);

    paint();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.SS = window.SS || {};
  window.SS.install = { decorate, paint, promptInstall, isStandalone, platform };
})();
