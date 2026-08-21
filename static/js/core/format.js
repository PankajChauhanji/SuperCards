// Shared display helpers.
//
// SS.shortName keeps player names from ever wrapping or overrunning their tile.
// The shape is always "full first name + last initial", and the last initial is
// protected: when something has to go, letters come off the FIRST name and the
// initial stays, because "Chandrikapra.. R" still identifies a player while
// "Chandrikaprasad.." (the old behaviour) throws away the half that
// distinguishes two people who share a first name.
//
//   "Pankaj Chauhan"       -> "Pankaj C"
//   "Suryavanshi Chauhan"  -> "Suryavanshi C"      (13 chars — used to clip at 12
//                                                   and drop the initial entirely)
//   "Chandrikaprasad Rao"  -> "Chandrikapra.. R"
//   "Priyanka"             -> "Priyanka"
//   "Bartholomewwww"       -> "Bartholomewww.."
//
// Two dots, not an ellipsis character: at 11px a "…" reads as a smudge and costs
// the same width as two periods that actually look like periods. CSS
// text-overflow is still the final backstop where these render (Chrome only
// supports "ellipsis" there, so the JS budget below is set generously enough
// that the CSS one rarely fires).
(function () {
  const SS = window.SS || (window.SS = {});

  const CLIP = "..";

  SS.shortName = function (name, max) {
    max = max || 16;
    name = (name == null ? "" : String(name)).trim();
    if (!name) return "";
    const parts = name.split(/\s+/);

    if (parts.length >= 2) {
      const initial = parts[parts.length - 1].charAt(0).toUpperCase();
      // Reserve the space and the initial, then spend everything left on the
      // first name.
      const budget = max - 2;
      let first = parts[0];
      if (first.length > budget) {
        first = first.slice(0, Math.max(1, budget - CLIP.length)) + CLIP;
      }
      return first + " " + initial;
    }

    let out = parts[0];
    if (out.length > max) {
      out = out.slice(0, Math.max(1, max - CLIP.length)) + CLIP;
    }
    return out;
  };
})();
