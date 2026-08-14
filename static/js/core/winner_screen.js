// Shared winner screen — the game-over medal stand (podium, tiered trophies,
// confetti/fireworks), used by every variant instead of a plain results list.
// Self-contained: each game bundle's showGameOver(winnerId, rows) just calls
// SS.showWinnerScreen({...}) with the rows it already builds (name/score/
// eliminated per player, ranked). This module owns the DOM/animation and the
// footer's Play again / Back to home buttons via callbacks.
(function () {
  const SS = window.SS || (window.SS = {});

  const TROPHY_PATH =
    "M6 3h12v2a6 6 0 0 1-4 5.66V13a2 2 0 0 0 2 2h1v2H7v-2h1a2 2 0 0 0 2-2v-2.34A6 6 0 0 1 6 5V3zm-4 2h3v2a4 4 0 0 0 1.2 2.86A4 4 0 0 1 2 6V5zm20 0v1a4 4 0 0 1-4.2 3.86A4 4 0 0 0 19 6V5h3zM8 19h8v2H8v-2z";

  // rank (1-based) -> {tier class, trophy fill}. Ranks beyond this live in
  // the plain overflow list below the podium instead.
  const TIERS = [
    null, // unused, ranks are 1-based
    { cls: "r1", fill: "#9fe8ff" }, // diamond
    { cls: "r2", fill: "#c7ccd1" }, // silver
    { cls: "r3", fill: "#c3763f" }, // bronze
    { cls: "r4", fill: "#7a8088" }, // iron
    { cls: "r5", fill: "#8a8f96" }, // plain
  ];
  const MAX_PODIUM = 5;
  const CONFETTI_COLORS = ["#e6b23c", "#57d98a", "#e8593f", "#9fe8ff", "#a98cf0", "#e7efe9"];

  // Centered "podium mountain" left-to-right order for N ranks (1..5):
  // rank 1 sits at the middle slot, ranks 2/3/4/5 alternate left/right of it.
  // N=5 -> [4,2,1,3,5]; N=3 -> [2,1,3]; N=2 -> [1,2]; N=1 -> [1].
  function podiumOrder(n) {
    const order = new Array(n);
    const center = Math.floor((n - 1) / 2);
    order[center] = 1;
    let rank = 2;
    let left = center;
    let right = center;
    let goLeft = true;
    while (rank <= n) {
      if (goLeft) {
        left -= 1;
        if (left >= 0) { order[left] = rank; rank += 1; }
      } else {
        right += 1;
        if (right < n) { order[right] = rank; rank += 1; }
      }
      goLeft = !goLeft;
    }
    return order;
  }

  function trophySvg(fill, big) {
    const size = big ? 42 : 34;
    return (
      '<svg class="trophy" viewBox="0 0 24 24" width="' + size + '" height="' + size +
      '" fill="' + fill + '"><path d="' + TROPHY_PATH + '"/></svg>'
    );
  }

  function buildPlace(row, rank, isWinner) {
    const tier = TIERS[Math.min(rank, MAX_PODIUM)];
    const el = document.createElement("div");
    el.className = "winner-place " + tier.cls;
    el.innerHTML =
      trophySvg(tier.fill, rank === 1) +
      '<div class="winner-p-name"></div>' +
      (isWinner ? '<div class="winner-you-badge" hidden>You</div>' : "") +
      '<div class="winner-p-score"></div>' +
      '<div class="winner-riser"><span class="winner-rank-num">' + rank + "</span></div>";
    el.querySelector(".winner-p-name").textContent = row.name;
    el.querySelector(".winner-p-score").textContent = row.total_score + " pts";
    return el;
  }

  function spawnConfetti(layer, count) {
    for (let i = 0; i < count; i += 1) {
      const el = document.createElement("div");
      el.className = "winner-confetti";
      el.style.left = Math.random() * 100 + "%";
      el.style.background = CONFETTI_COLORS[i % CONFETTI_COLORS.length];
      el.style.animationDuration = 2.4 + Math.random() * 2 + "s";
      el.style.animationDelay = Math.random() * 2.5 + "s";
      layer.appendChild(el);
    }
    [{ x: "18%", y: "20%" }, { x: "80%", y: "16%" }, { x: "50%", y: "12%" }].forEach((p, i) => {
      const b = document.createElement("div");
      b.className = "winner-burst";
      b.style.left = p.x;
      b.style.top = p.y;
      b.style.color = CONFETTI_COLORS[i % CONFETTI_COLORS.length];
      b.style.animationDelay = i * 0.5 + "s";
      layer.appendChild(b);
    });
  }

  // rows: [{user_id, name, total_score, eliminated}], already ranked (index 0 = winner).
  function showWinnerScreen({ winnerId, rows, youId, isHost, onRematch }) {
    const modal = document.getElementById("winner-modal");
    const title = document.getElementById("winner-title");
    const sub = document.getElementById("winner-sub");
    const podiumRow = document.getElementById("winner-podium-row");
    const overflow = document.getElementById("winner-overflow");
    const confettiLayer = document.getElementById("winner-confetti-layer");
    const footer = document.getElementById("winner-footer");
    if (!modal) return;

    const winnerName = (rows.find((r) => r.user_id === winnerId) || {}).name || "Nobody";
    title.textContent = winnerName + " wins!";
    sub.textContent = winnerId === youId
      ? "You're the last one standing."
      : "Last player standing takes the game.";

    const podiumRows = rows.slice(0, MAX_PODIUM);
    const order = podiumOrder(podiumRows.length);
    podiumRow.innerHTML = "";
    order.forEach((rank) => {
      const row = podiumRows[rank - 1];
      const place = buildPlace(row, rank, row.user_id === winnerId);
      if (row.user_id === youId) {
        const badge = place.querySelector(".winner-you-badge");
        if (badge) badge.hidden = false;
      }
      podiumRow.appendChild(place);
    });

    overflow.innerHTML = "";
    const rest = rows.slice(MAX_PODIUM);
    if (rest.length) {
      rest.forEach((row, i) => {
        const line = document.createElement("div");
        line.className = "winner-overflow-row";
        line.textContent = (MAX_PODIUM + i + 1) + ". " + row.name + " — " + row.total_score + " pts";
        overflow.appendChild(line);
      });
    }

    confettiLayer.innerHTML = "";
    spawnConfetti(confettiLayer, Math.min(40, 10 + podiumRows.length * 6));

    footer.innerHTML = "";
    if (isHost) {
      const again = document.createElement("button");
      again.className = "btn-primary";
      again.style.width = "auto";
      again.textContent = "Play again";
      again.addEventListener("click", () => {
        again.disabled = true;
        if (onRematch) onRematch();
      });
      footer.appendChild(again);
    } else {
      const wait = document.createElement("span");
      wait.className = "waiting";
      wait.style.marginRight = "auto";
      wait.textContent = "Waiting for the host to start a rematch…";
      footer.appendChild(wait);
    }
    const home = document.createElement("button");
    home.className = "btn-ghost";
    home.style.width = "auto";
    home.textContent = "Back to home";
    home.addEventListener("click", () => { window.location.href = "/"; });
    footer.appendChild(home);

    modal.classList.add("open");
  }

  function hideWinnerScreen() {
    const modal = document.getElementById("winner-modal");
    if (modal) modal.classList.remove("open");
  }

  SS.showWinnerScreen = showWinnerScreen;
  SS.hideWinnerScreen = hideWinnerScreen;
})();
