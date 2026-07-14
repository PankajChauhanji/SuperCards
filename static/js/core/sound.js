// Minimal Web Audio cues — no asset files. Currently just a soft "your turn"
// chime, plus a persisted mute toggle.
(function () {
  let ctx = null;
  function audio() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) ctx = new AC();
    }
    return ctx;
  }

  function muted() {
    return localStorage.getItem("ss_muted") === "1";
  }

  function tone(freq, start, dur, gainPeak) {
    const a = audio();
    if (!a) return;
    const osc = a.createOscillator();
    const gain = a.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    osc.connect(gain);
    gain.connect(a.destination);
    const t = a.currentTime + start;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(gainPeak, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  }

  window.SS = window.SS || {};
  window.SS.sound = {
    turnPing() {
      if (muted()) return;
      const a = audio();
      if (a && a.state === "suspended") a.resume();
      // Two-note rising chime.
      tone(660, 0, 0.18, 0.12);
      tone(880, 0.12, 0.22, 0.12);
    },
    muted,
    toggleMute() {
      const next = muted() ? "0" : "1";
      localStorage.setItem("ss_muted", next);
      return next === "1";
    },
  };
})();
