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
  // The avatar gauge's own ramp. It starts on a calm blue at a clean score and
  // then joins RING_STOPS exactly, so the gauge and the Scores panel's bar stay
  // one system below the top end while the healthy state still reads as "full
  // and calm" rather than "full of green".
  const GAUGE_STOPS = [
    [0.00, [95, 208, 232]],
    [0.15, [74, 222, 128]],
    [0.40, [250, 204, 21]],
    [0.70, [249, 115, 22]],
    [1.00, [239, 68, 68]],
  ];

  function lerpStops(stops, pct) {
    pct = Math.max(0, Math.min(1, pct));
    for (let i = 1; i < stops.length; i++) {
      const [p0, c0] = stops[i - 1];
      const [p1, c1] = stops[i];
      if (pct <= p1) {
        const t = p1 === p0 ? 0 : (pct - p0) / (p1 - p0);
        const c = c0.map((v, j) => Math.round(v + (c1[j] - v) * t));
        return "rgb(" + c.join(",") + ")";
      }
    }
    const last = stops[stops.length - 1][1];
    return "rgb(" + last.join(",") + ")";
  }

  function ringColor(pct) { return lerpStops(RING_STOPS, pct); }
  function gaugeColor(pct) { return lerpStops(GAUGE_STOPS, pct); }

  // Fit an already-shortened "First L" into a hard character budget.
  //
  // Above ~9 characters the "First.. L" shape still works and the last initial is
  // worth keeping. Below that, the ".." would eat a third of the budget to say
  // something the reader can already see, so spend everything on real letters of
  // the first name instead: "Surya" beats "Su.. C" when only six glyphs fit.
  function fitName(name, max) {
    name = (name || "").trim();
    if (!name || name.length <= max) return name;
    if (max >= 9 && window.SS.shortName) return window.SS.shortName(name, max);
    return name.split(/\s+/)[0].slice(0, max);
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
  //         connected?, eliminated?, timerPct?, timerLabel?, timerSeconds?,
  //         you?, own? }
  //
  // Two meanings, two deliberately different visual channels — they can never
  // be mistaken for each other:
  //
  //   ring  = whose turn it is, and how much time is left. Transient: it only
  //           exists while that seat is on the clock.
  //   gauge = how close this player is to elimination. Persistent: a liquid
  //           level inside the avatar that DRAINS as the score climbs, so full
  //           and calm means healthy and near-empty means nearly out.
  //
  // This replaced two concentric rings that sat 3px apart and both ran through
  // the same green-to-red ramp, so a red outer arc ("act now") and a red inner
  // arc ("nearly eliminated") looked nearly identical — worst of all at phone
  // sizes, where the two rings were 50px and 44px.
  //
  // ringPct is 0..1 (how close to elimination), or null for a game with no such
  // metric (Bluff), which keeps the older plain avatar filled with the player's
  // colour. When a gauge IS drawn, identity moves to the avatar's rim so the
  // interior is free to be the level.
  function buildSeatEl(s) {
    const el = document.createElement("div");
    if (s.active) el.classList.add("active");
    if (!s.connected) el.classList.add("offline");
    if (s.eliminated) el.classList.add("out");
    if (s.ringPct == null) el.classList.add("no-ring");
    if (s.own) el.classList.add("own-seat");

    const outer = document.createElement("div");
    outer.className = "opp-ring-outer";
    const timerPct = s.timerPct != null ? Math.max(0, Math.min(1, s.timerPct)) : null;
    const timerColor = timerPct != null ? ringColor(1 - timerPct) : null;
    if (timerPct != null) {
      outer.style.setProperty("--timer-pct", (timerPct * 100).toFixed(1) + "%");
      outer.style.setProperty("--timer-color", timerColor);
    }

    // Kept as a plain wrapper: the nesting outer > ring > avatar is what the
    // existing size and active-state CSS hangs off. It no longer paints the
    // score arc.
    const ring = document.createElement("div");
    ring.className = "opp-ring";

    const initial = (s.name || "?").trim().charAt(0).toUpperCase();
    const avatar = document.createElement("div");
    avatar.className = "opp-avatar";
    if (s.ringPct != null) {
      const pct = Math.max(0, Math.min(1, s.ringPct));
      avatar.classList.add("gauge");
      // Rim carries identity; a coloured fill would collide with the level.
      avatar.style.borderColor = s.color || "var(--line)";
      const level = document.createElement("span");
      level.className = "av-level";
      level.style.height = ((1 - pct) * 100).toFixed(1) + "%";
      level.style.background = gaugeColor(pct);
      avatar.appendChild(level);
      const ini = document.createElement("b");
      ini.className = "av-ini";
      ini.textContent = initial;
      avatar.appendChild(ini);
    } else {
      avatar.style.background = s.color || "var(--line)";
      avatar.textContent = initial;
    }
    ring.appendChild(avatar);
    outer.appendChild(ring);

    const count = document.createElement("span");
    count.className = "opp-count" + (s.safe ? " safe" : "");
    count.textContent = s.safe ? "0" : String(s.cardCount != null ? s.cardCount : "");
    outer.appendChild(count);

    el.appendChild(outer);

    // One plate instead of two floating text lines. The translucent backing is
    // load-bearing, not decoration: --muted on Casino Felt's upper gradient
    // measures about 1.8:1, and Red Casino and Sunset are no better. A plate is
    // one fix for all fourteen themes instead of tuning text per theme.
    const plate = document.createElement("div");
    plate.className = "seat-plate";

    const name = document.createElement("span");
    name.className = "opp-name";
    // On a cramped arc, re-shorten deliberately instead of letting CSS chop the
    // name mid-word. Re-running shortName on the already-shortened form keeps the
    // last initial — "Surya.. C" identifies a player, a hard-cut "Suryav" does
    // not, and the ".." says that something was removed.
    name.textContent = s.nameMax ? fitName(s.name || "", s.nameMax) : (s.name || "");
    plate.appendChild(name);

    if (s.you) {
      const pill = document.createElement("span");
      pill.className = "seat-you";
      pill.textContent = "you";
      plate.appendChild(pill);
    }

    const showTimer = timerPct != null && s.timerLabel;
    // Your own seat shows score AND timer: it is the number you are deciding
    // against, and hiding it exactly while you decide was the old behaviour.
    // Opponent seats are 74px wide in the arc (60px on phones) and cannot fit
    // both, so there the timer takes the slot — only ever one seat at a time.
    if (typeof s.score === "number" && (s.own || !showTimer)) {
      const score = document.createElement("span");
      score.className = "opp-score";
      // " pts" costs about 22px — roughly four more letters of somebody's name —
      // and on an opponent's plate the unit is inferable from position and from
      // the Scores panel. Your own seat has the room, so it keeps the label.
      score.textContent = s.own ? s.score + " pts" : String(s.score);
      plate.appendChild(score);
    }

    if (showTimer) {
      const status = document.createElement("span");
      status.className = "opp-score timer";
      // Inherit the ring's current colour. These are two halves of one signal;
      // the old static green meant that at three seconds the ring was red and
      // the number underneath was still calm.
      status.style.color = timerColor;
      if (s.timerSeconds != null && s.timerSeconds <= 5) status.classList.add("urgent");
      status.textContent = s.timerLabel;
      plate.appendChild(status);
    }

    el.appendChild(plate);

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

    // A single-row name plate needs more width than the 74px seat, so it gets
    // exactly the horizontal room the arc actually allocates per seat — no more.
    // Hardcoding a width would either cramp a 3-player table or collide plates
    // on a 20-player one; the spacing is right there in the layout, so use it.
    const w = container.clientWidth || 320;
    const mobile = w < 460;
    const spacing = seats.length > 1
      ? positions[1].left - positions[0].left
      : (mobile ? 150 : 190);
    // Floor is low on purpose. The arc packs seats closer than their own 60px box
    // on a narrow felt (a 292px container with 4 opponents leaves 55px of pitch),
    // so a comfortable minimum width would guarantee neighbouring plates collide.
    // Better to let the name ellipsise than to overlap.
    const plateMax = Math.max(44, Math.min(mobile ? 132 : 168, spacing - 6));
    container.style.setProperty("--plate-max", Math.round(plateMax) + "px");

    // Below this there is genuinely no room for a name AND a score on one line,
    // so the score drops and the name keeps the space. Scores stay available in
    // the Scores panel (desktop) or its sheet (phones, todos §11).
    const tight = plateMax < 74;
    container.classList.toggle("tight", tight);
    // Roughly the glyphs that fit once the score is gone: ~6px each at 0.68rem,
    // less the plate's 8px of padding. Handed to the seat so it re-shortens on
    // purpose instead of being cut mid-word by text-overflow.
    const nameMax = tight ? Math.max(6, Math.floor((plateMax - 8) / 6)) : null;

    // Wave motion is per-element compositing, so a very crowded table drops it
    // and keeps a static level. Super Seven allows 20 seats, and this page
    // already holds a wake lock (todos §9).
    container.classList.toggle("dense", seats.length > 10);

    seats.forEach((s, i) => {
      const el = buildSeatEl(nameMax ? Object.assign({}, s, { nameMax: nameMax }) : s);
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
    // own:true unlocks the wider single-row plate and the score-plus-timer rule.
    // This seat renders under the hand rather than into the arc, so unlike the
    // opponent seats it is not width-constrained by its neighbours.
    const el = buildSeatEl(Object.assign({}, seat, { own: true, you: true }));
    el.classList.add("my-seat");
    container.appendChild(el);
  }

  SS.renderOpponentSeats = renderOpponentSeats;
  SS.renderMySeat = renderMySeat;
  SS.layoutHandFan = layoutHandFan;
  SS.layoutHandGrid = layoutHandGrid;
})();
