// SS.icon(name, extraClass) — the app's one icon set, for markup built in JS.
//
// The symbols live in templates/partials/icons.html, included once per page;
// this only writes the <use> reference, so an icon costs a few bytes wherever it
// appears. Templates write the same markup directly. Decorative by default
// (aria-hidden): every icon sits next to a text label or inside a button that
// carries its own aria-label.
(function () {
  const SS = window.SS || (window.SS = {});

  SS.icon = function (name, extraClass) {
    return '<svg class="ico' + (extraClass ? " " + extraClass : "") +
      '" aria-hidden="true" focusable="false"><use href="#i-' + name + '"/></svg>';
  };

  // The avatar motifs a player can choose. Must match game/core/avatars.py
  // MOTIFS (tests/test_avatars.py checks it); the server rejects anything else.
  SS.AVATARS = [
    "spade", "heart", "diamond", "club",
    "crown", "star", "flame", "bolt",
    "moon", "sun", "leaf", "anchor",
    "rocket", "music", "ghost", "gem",
  ];

  // What goes inside a player's avatar circle: their chosen motif, or their
  // initial when they have not picked one (game/core/avatars.py). The server
  // only ever sends a known motif name; the pattern check is a second fence so
  // nothing else can reach the markup. Returns HTML.
  SS.avatarFace = function (name, avatar) {
    if (avatar && /^[a-z]+$/.test(avatar)) return SS.icon(avatar, "av-motif");
    const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
    const span = document.createElement("span");
    span.textContent = initial;
    return span.innerHTML;
  };
})();
