// Shared display helpers.
//
// SS.shortName keeps player names from ever wrapping or overrunning their tile:
//   "Pankaj Chauhan"  -> "Pankaj C"     (full first name + last initial)
//   "Priyanka"        -> "Priyanka"     (short single name, unchanged)
//   "Bartholomew"     -> "Bartholom…"   (long single name, clipped)
// CSS ellipsis is still applied as a final backstop where these render.
(function () {
  const SS = window.SS || (window.SS = {});
  SS.shortName = function (name, max) {
    max = max || 12;
    name = (name == null ? "" : String(name)).trim();
    if (!name) return "";
    const parts = name.split(/\s+/);
    let out;
    if (parts.length >= 2) {
      out = parts[0] + " " + parts[parts.length - 1].charAt(0).toUpperCase();
    } else {
      out = parts[0];
    }
    if (out.length > max) out = out.slice(0, max - 1).replace(/\s+$/, "") + "…";
    return out;
  };
})();
