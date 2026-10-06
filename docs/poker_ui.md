# Poker — UI spec

Screen-by-screen design for the Poker client. The gameplay rules are in
[`poker_rules.md`](poker_rules.md). The rule here is **reuse first**: every screen below is
built from a shared component, and the table gives each one a poker-specific *fill*. Nothing
shared is forked.

| Screen part | Shared component reused | Poker-specific fill |
| :--- | :--- | :--- |
| Topbar brand | `games/<game>/branding.html` pattern | "Poker" + `poker_symbol.svg` (gold spade on a teal card) |
| Home tile | `index.html` picker (`game_meta`) | emblem ♠ as text "A", accent teal `#2fb7a3`, "Bet, bluff & take the pot" |
| Lobby | `core/lobby.js` (`SS.Lobby.init({fields})`) | 5 settings fields (below) |
| Seats | `core/seats.js` arc + own seat, including its liquid gauge | the gauge is the **stack vs. coins received** (full at the start, drains as coins leave) with the amount written in the circle; a **money pouch** replaces the card-count badge; two mini face-down cards beside anyone still in; a chip line with D / SB / BB, this stage's bet and Folded / All-in / Sat out |
| Scores panel + phone sheet | `#sb-players` / `#action-log` ids (`core/table_sheet.js` relocates them) | rows ranked by coins, with net +/- |
| Action history | `core/action_log.js` | "Ben raises to 150K", "Board: K♦ 7♥ 2♠" |
| Hand-rankings card | its own 🃏 button on the felt (not the side column) | opens the ten hands with real card art (kickers dimmed). Docked panel on desktop, bottom sheet on a phone. Client-only, static, the same for every player |
| Round summary | shared `#roundend-modal` markup | pot winners + hand names, shown hands, coins left, delta, 30s countdown, host **Start next round** |
| Game over | `core/winner_screen.js` (`SS.showWinnerScreen`) | `scoreText` = "2.45M (+1.45M)" |
| Rules modal | `core/rules_modal.js` | `static/rules/poker/{en,hi}.html` |
| Themes, reactions, deck choice, sound, wake lock, reconnect | all `core/*` | nothing; they work unchanged |

The "Standard / Box view" control is hidden for poker: two cards never need a box view. This
is done from poker's own `table.html`, so `core/view_mode.js` is untouched.

## Lobby settings

| Field | Label | min – max |
| :--- | :--- | :--- |
| `starting_chips` | Starting coins | 10,000 – 100,000,000 |
| `rounds` | Rounds | 1 – 100 |
| `turn_timer` | Turn timer (s) | 15 – 120 |
| `timeout_limit` | Missed turns before sat out | 1 – 10 |
| `blind_up_every` | Blinds double every (rounds, 0 = off) | 0 – 50 |
| `hand_hints` | Hand hints (show each player their hand) | on / off switch, **off** by default |

The on/off switch is a `{type: "toggle"}` field in the shared `core/lobby.js`. It is an
additive option that stores 1 / 0, so the server's existing integer settings handling is
unchanged, and games that pass no `type` render exactly as before. Guests see "On" or "Off".

## Table (felt), top to bottom

1. **Opponents' arc**, using the shared seats.
   * **The circle is the money.** The shared liquid gauge, which Super Seven uses for
     elimination, here shows the player's stack against the coins they were given. It is
     full at the start and drains as coins leave. The stack amount (`1.2M`) is written in
     the circle.
   * A player who is up on the game gets a soft gold halo.
   * **Money pouch** in the badge slot where other games show a card count. It is bright
     gold and glowing when the player is up on the game, and flat tan when they are down.
     It disappears when they are out of coins. Hovering shows "Up 120,000 this game".
   * **Two mini face-down cards** beside the circle while the player still holds a hand.
     They go away on a fold.
   * Under the plate is a chip line:
     * a round **D**, **SB** or **BB** marker;
     * a gold coin chip with this stage's bet (`30K`);
     * an **ALL-IN** / Folded / Sat out tag.
   * At an all-in runout or a showdown, the seat's two cards appear face up under the plate.
2. **Centre:**
   * The **board**: five card slots, with dashed outlines until dealt. Cards turn up as
     they are dealt.
   * The **pot as a pile of gold coins.** Up to five stacks, which grow with the pot on a
     gentle log scale, and new coins drop in. Under the pile are "Pot 790K" and, when there
     are any, "Main / Side" chips. The pile is the round's total, including this stage's
     bets, so thrown coins visibly land in it.
   * Under that, a small info line: *Flop · Blinds 5K / 10K · Round 3 of 10*.
3. **Your area:**
   * Your two hole cards, large. They are **dealt face down** the instant the round starts
     and **turned over** when your private deal arrives. The face image is decoded first,
     so the flip never shows an empty box. All 52 faces of your chosen deck are preloaded
     on page load.
   * Under the cards, **"Your hand: Two Pair, Kings and Sevens"**, only when the host has
     turned on **Hand hints**. It is computed by the server from your cards and the board,
     sent only to you, and kept current every stage. With hints off it is not sent at all.
   * Your seat (the shared own-seat badge, dressed the same way) and the action bar.

## Motion

Every motion is skipped under `prefers-reduced-motion`.

* **Coins to the pot.** When anyone calls, bets, raises, posts a blind or goes all-in,
  3–10 gold coins (more for bigger amounts) arc from their seat into the pile, with a
  synthesized chip clink. The clink respects the mute button and needs no sound files.
* **Pot to the winner.**
  1. At a showdown the winning five cards light up and the rest of the board dims.
  2. After a beat, the pot flies to each winner's seat and their circle glows gold.
  3. The pile clears, and then the round summary opens. A fold win skips straight to the
     coins.
  The last round does the same before the podium.

## Action bar (only on your turn)

`[ Fold ]  [ Check | Call 20K ]  [ Raise to 60K ]  [ All-in 1.2M ]`

* Above the buttons sits a **raise row**: presets **Min · ½ Pot · Pot · All-in**, a slider
  that steps in small-blind units from the minimum raise to all-in, and a number box.
  Changing any of the three updates the other two and the Raise button's label.
* **Bet** replaces **Raise** when nobody has bet in the stage.
* The raise row and Raise button are hidden when a raise is not allowed: a short all-in did
  not re-open the betting, or nobody is left to answer it.
* **Confirmations are small bubbles that open from the button itself**, never a browser
  dialog:
  * **All-in** always asks: "Go all-in for 1,000,000 coins?" with **Cancel** / **All-in**.
  * **Fold** asks only when checking is free: "Checking is free — fold anyway?"
  * The bubble sits above the button, with an arrow pointing at it, and stays inside the
    screen.
  * It closes on Cancel, a tap elsewhere, Escape, scrolling, or the turn moving on.
* **Pre-actions while you wait.** **Check / Fold** and **Check** toggles show when it is
  not your turn and you are still in the hand.
  * When the turn reaches you, the chosen one is played at once.
  * **Check** never turns into a call: if someone bets first, it quietly drops and the turn
    is yours to decide.
  * Both reset at each new stage.
* When it is not your turn, the bar shows a status line instead: "Waiting for Ben…",
  "Folded — waiting for the next round", "All-in", or a big **I'm back** button when you
  are sat out.
* On phones the buttons wrap two per row, the slider runs full width, and the bar keeps
  clear of the floating reaction buttons.

## Round summary popup

Opens after the payout animation above.

* **Title:** "Round 3 of 10".
* **Sub-title:** one line per pot, e.g. "Ben wins 790K with Three of a Kind, Sevens", or
  "Ben wins 15K — everyone else folded".
* **Body:** one row per player, most coins first. Each row shows the name, any cards shown
  at showdown with the hand name, the delta (green **+410K** / red **−380K**), and the coins
  left. Busted players are marked "Out of coins".
* **Footer:**
  * The host gets **Start next round (27s)**, counting down.
  * Everyone else sees "Next round starts in 27s…".
  * When the countdown hits 0, the server deals by itself.

## Hand-rankings card

Rebuilt on 2026-10-06 after play-testing. The first version lived inside the Coins card. A
scroll box inside a scroll box made it hard to scroll, and the shared phone sheet squeezed
it to about 120px. The side column is now Coins + Action History again, as in the other
games.

* **Button:** **🃏 Hands** in the felt's top-right corner. It is icon-only on a phone, and
  shows a gold dot while hand hints are on and you hold a hand.
* **Each row has two lines** *(enlarged 2026-10-06)*: the number, name and hint across the
  top, then the five example cards across the full row width. The cards are 46×64px on
  desktop and 52×73px on a phone, up from 19×27, so the card art can actually be read.
* **Desktop:** a panel docked inside the right edge of the felt, 300px wide.
  * Its height is capped at the smaller of the table height and the window height, minus
    room for the floating reaction buttons, so it never runs past the table or under that
    corner.
  * It scrolls inside itself, with one scroll area only.
  * It sits clear of your cards and the betting bar.
  * It may cover the right-most seats while open, because the player opened it.
* **Phone:** a bottom sheet with a backdrop, up to 78% of the screen, again fitting all ten
  rows. It closes by ✕, the backdrop, or Escape.
* **It stays open until you close it.** Your turn does not close it. The one exception is a
  phone: there the sheet steps aside when the round summary or the podium opens, since it
  would otherwise bury the host's Start next round button.
* **One scroll area only:** the panel itself. Nothing inside it scrolls separately.
* **With hand hints on:**
  * the header shows your hand as a gold chip, e.g. "High Card, King";
  * your row glows with a "YOU" tag;
  * the card opens with your row in view.
  * With hints off, a note says the host can switch them on.

## Number format

The table shows compact amounts: **5K, 350K, 1.2M, 12.5M**. Hovering or long-pressing shows
the full amount (`title` attribute). The round summary and podium use the same compact form
with the full amount on hover.

The game UI is English everywhere, so the table uses K / M. The Hindi rules page writes
amounts the Indian way (Lakh / Crore) in prose, as recorded in the rules doc.
