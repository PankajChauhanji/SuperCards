// Shared seat rendering — the circular ring+avatar+name+score badge used for
// both opponents (arced across the top of the felt) and the player's own
// seat (centered under the hand). Reused by every variant that wants this
// look (currently Seven + Bluff); each variant builds its own seat
// descriptors from its own state and hands them to SS.renderOpponentSeats /
// SS.renderMySeat.
(function () {
  const SS = window.SS || (window.SS = {});

  // green -> yellow -> orange -> red, matching the Scores panel's own
  // progress-bar gradient (table.css .sb-bar-fill) so the two read as one
  // system: the ring is that same bar, wrapped around the avatar.
  const RING_STOPS = [
    [0.00, [74, 222, 128]],
    [0.40, [250, 204, 21]],
    [0.70, [249, 115, 22]],
    [1.00, [239, 68, 68]],
  ];
  function ringColor(pct) {
    pct = Math.max(0, Math.min(1, pct));
    for (let i = 1; i < RING_STOPS.length; i++) {
      const [p0, c0] = RING_STOPS[i - 1];
      const [p1, c1] = RING_STOPS[i];
      if (pct <= p1) {
        const t = p1 === p0 ? 0 : (pct - p0) / (p1 - p0);
        const c = c0.map((v, j) => Math.round(v + (c1[j] - v) * t));
        return "rgb(" + c.join(",") + ")";
      }
    }
    return "rgb(239,68,68)";
  }

  // Positions are computed from the container's actual rendered width, so
  // the same math holds at any breakpoint — no separate mobile/desktop code
  // paths, just smaller numbers once the container is narrow.
  function layout(container, count) {
    const w = container.clientWidth || 320;
    const mobile = w < 460;
    const seatW = mobile ? 60 : 74;
    const margin = seatW / 2 + 6;
    const usable = Math.max(w - margin * 2, 20);
    const curveDepth = mobile ? 28 : 44;
    const positions = [];
    for (let i = 0; i < count; i++) {
      // frac spans 0..1 across the row; t re-centers it to -1..1 so the
      // curve is symmetric. count===1 forces frac to 0.5 (t=0), which is
      // exactly the "single opponent centered at the very top" case.
      const frac = count === 1 ? 0.5 : (i + 0.5) / count;
      const t = frac * 2 - 1;
      positions.push({
        left: margin + frac * usable,
        top: curveDepth * (t * t),
      });
    }
    return positions;
  }

  // seat: { name, color, cardCount, score?, safe?, ringPct?, active?,
  //         connected?, eliminated?, timerPct?, timerLabel? }
  // ringPct is 0..1 (how close to elimination) or null/undefined to render a
  // plain bordered avatar for games with no such metric (e.g. Bluff). This
  // score ring is ALWAYS shown when present — it never gets replaced.
  // timerPct (0..1, time REMAINING) + timerLabel ("14s left") add a SECOND,
  // outer ring around it whenever this seat is the active turn, so the two
  // meanings (how close to elimination / how much time is left) stay
  // visible at once instead of one hiding the other.
  function buildSeatEl(s) {
    const el = document.createElement("div");
    if (s.active) el.classList.add("active");
    if (!s.connected) el.classList.add("offline");
    if (s.eliminated) el.classList.add("out");
    if (s.ringPct == null) el.classList.add("no-ring");

    const outer = document.createElement("div");
    outer.className = "opp-ring-outer";
    if (s.timerPct != null) {
      const pct = Math.max(0, Math.min(1, s.timerPct));
      outer.style.setProperty("--timer-pct", (pct * 100).toFixed(1) + "%");
      outer.style.setProperty("--timer-color", ringColor(1 - pct));
    }

    const ring = document.createElement("div");
    ring.className = "opp-ring";
    if (s.ringPct != null) {
      const pct = Math.max(0, Math.min(1, s.ringPct));
      ring.style.setProperty("--ring-pct", (pct * 100).toFixed(1) + "%");
      ring.style.setProperty("--ring-color", ringColor(pct));
    }

    const avatar = document.createElement("div");
    avatar.className = "opp-avatar";
    avatar.style.background = s.color || "var(--line)";
    avatar.textContent = (s.name || "?").trim().charAt(0).toUpperCase();
    ring.appendChild(avatar);
    outer.appendChild(ring);

    const count = document.createElement("span");
    count.className = "opp-count" + (s.safe ? " safe" : "");
    count.textContent = s.safe ? "0" : String(s.cardCount != null ? s.cardCount : "");
    outer.appendChild(count);

    el.appendChild(outer);

    const name = document.createElement("span");
    name.className = "opp-name";
    name.textContent = s.name || "";
    el.appendChild(name);

    if (s.timerPct != null && s.timerLabel) {
      const status = document.createElement("span");
      status.className = "opp-score timer";
      status.textContent = s.timerLabel;
      el.appendChild(status);
    } else if (typeof s.score === "number") {
      const score = document.createElement("span");
      score.className = "opp-score";
      score.textContent = s.score + " pts";
      el.appendChild(score);
    }

    return el;
  }

  // Curved "held in hand" fan for the player's own cards — same shape as
  // the seat arc above (0 at the center card, growing toward the edges),
  // applied as rotation + a downward lift instead of position.
  //
  // Overlap combines two pulls, and always takes whichever wants MORE
  // overlap:
  //  - MIN_OVERLAP_RATIO: cards always sit bunched together like a hand
  //    actually held, even with room to spare — at most 75% of each card
  //    shows (the last/rightmost card is the one exception, nothing sits
  //    on top of it). Without this floor, a wide desktop felt or a small
  //    hand would space cards apart edge-to-edge instead of overlapping.
  //  - fit-to-container: for a big enough hand on a narrow enough screen,
  //    75%-visible still doesn't fit one row, so overlap grows further —
  //    all the way down to a 1px sliver if it truly has to — rather than
  //    ever wrapping to a second row.
  // Call once after all card-slot elements are appended (so measurement is
  // accurate); `slots` is a plain array of the .card-slot elements in order.
  const FAN_MAX_ROT = 20;
  const FAN_CURVE_DEPTH = 14;
  const FAN_MIN_OVERLAP_RATIO = 0.25;
  function layoutHandFan(container, slots) {
    const n = slots.length;
    if (n === 0) return;
    const firstCard = slots[0].querySelector(".hand-card") || slots[0];
    const cardWidth = firstCard.getBoundingClientRect().width || 74;
    const containerWidth = container.clientWidth || cardWidth * n;

    let overlap = 0;
    if (n > 1) {
      const available = containerWidth - cardWidth;
      const neededToFit = cardWidth - available / (n - 1);
      const minOverlap = cardWidth * FAN_MIN_OVERLAP_RATIO;
      overlap = Math.max(minOverlap, neededToFit);
      overlap = Math.min(overlap, cardWidth - 1); // never fully hide a card
    }

    const mid = (n - 1) / 2;
    slots.forEach((slot, i) => {
      if (i > 0) slot.style.marginLeft = -overlap + "px";
      const t = mid ? (i - mid) / mid : 0;
      slot.style.setProperty("--rot", (t * FAN_MAX_ROT).toFixed(1) + "deg");
      slot.style.setProperty("--fan-y", (FAN_CURVE_DEPTH * t * t).toFixed(1) + "px");
    });
  }

  // Flat, wrapping, scrollable grid — the alternative to the fan for hands
  // that don't work as a single overlapped row on a small screen (Bluff can
  // run to 50+ cards for one player in a 2-player game; squeezed into one
  // row that's a 1px sliver per card, untappable). No overlap math needed:
  // just clear whatever the fan set, and let CSS (.hand-flat-scroll on the
  // container) handle wrapping/height/scroll.
  function layoutHandGrid(container, slots) {
    slots.forEach((slot) => {
      slot.style.marginLeft = "";
      slot.style.setProperty("--rot", "0deg");
      slot.style.setProperty("--fan-y", "0px");
    });
  }

  // Seats arrive pre-ordered clockwise-from-you (each variant rotates its
  // own turn order before calling this), so left-to-right position IS the
  // turn sequence — no TURN/NEXT label needed, only `active` for whoever's
  // up now.
  function renderOpponentSeats(container, seats) {
    container.innerHTML = "";
    const positions = layout(container, seats.length);
    seats.forEach((s, i) => {
      const el = buildSeatEl(s);
      el.classList.add("opp-seat");
      el.style.left = positions[i].left + "px";
      el.style.top = positions[i].top + "px";
      container.appendChild(el);
    });
  }

  // The player's own seat: same badge, centered under the hand instead of
  // arced. `seat` may be null (e.g. not yet seated) to just clear the slot.
  function renderMySeat(container, seat) {
    container.innerHTML = "";
    if (!seat) return;
    const el = buildSeatEl(seat);
    el.classList.add("my-seat");
    container.appendChild(el);
  }

  SS.renderOpponentSeats = renderOpponentSeats;
  SS.renderMySeat = renderMySeat;
  SS.layoutHandFan = layoutHandFan;
  SS.layoutHandGrid = layoutHandGrid;
})();
