# Super 4 — implementation design & locked decisions

Source rules: docs/PLATFORM_PLAN.md + the Super 4 rules. Where the rules were silent or
ambiguous, the decision made here is marked **[decision]** so it can be revisited.

## Core model
- **4 fixed slots** per player, indexed 0–3 (shown to users as 1–4). A slot holds a
  Card or is **empty** (removed via matching) — empties count as 0 and lower your total.
- **Preview:** at deal, each player privately sees **slots 0 and 1** (their "first two").
  The host may start play early; the server starts it automatically after at most 30 seconds.
- **Card values:** Ace=1 … King=13. Both red Kings — **King of Hearts (KH)** and
  **King of Diamonds (KD)** — are worth −1.
- **Deck:** standard 52 (num_decks configurable). Reshuffle the discard back into the draw
  pile when it runs out (keep the current center card out).

## Turn flow
1. **Draw** the top card — its face is private to the active player.
2. Then exactly one of:
   - **Keep**: choose a slot; drawn card goes there (face-down), the old card goes to the
   center face-up. The kept card remains face-down. **No power triggers** on a kept card.
   - **Discard**: drawn card goes to the center face-up. If its rank is **7–13 it triggers
     a power** (see below) — powers fire ONLY on an immediately-discarded drawn card.
   - **Match own card** ("Matching Your Own Card"): pick one of your slots; if that card's
     rank == the drawn card's rank, **both are discarded** (your slot empties → fewer
     points). If wrong, that slot is **revealed to all**, returned, the drawn card is
     discarded, and you take **one penalty card** into an empty slot / appended.

## Card powers (only on discard of the drawn card)
- **7 or 8** — peek one of **your own** cards (private to you).
- **9 or 10** — peek one **opponent** card (private to you).
- **11 or 12** — **blind swap** one of your cards with an opponent's (no reveal to anyone).
- **13 King** — look at one of yours + one opponent's (private to you), then **optionally swap**.

**Every power is optional (updated 2026-07-17):** the acting player may skip it — the client
sends `s4_power_skip` (same `Room.power_skip` the director already used on timeout). The King's
swap decision was always optional; now the look/swap/peek itself is too.

## Hidden information (critical — no leaks)
Per-viewer knowledge is tracked: `known[viewer] = set((owner, slot))` = positions whose
current card that viewer legitimately knows. Rules:
- Init: `known[uid] ⊇ {(uid,0),(uid,1)}` from preview.
- Peek (7/8/9/10, King look): add the peeked `(owner,slot)` to the actor's known set.
- **Swap moves knowledge with the card:** on swapping positions p and q, every viewer's
  knowledge bit for p and q is exchanged (a viewer who knew p's card now knows it's at q).
  King's actor saw both first, so they still know both after swapping.
- Server NEVER sends a card value for a position the recipient doesn't know. Public state
  carries only counts / face-down flags + momentary public reveals (failed matches, final
  reveal). Peeks are sent to the **acting socket only**.

## Table matching (rewritten 2026-07-17 — see game/super_four/matching.py)
Whenever a card lands face-up on the center, a match window opens: it lasts at most
`match_window` seconds (max 10) and also closes as soon as the **next player starts their
turn** (draw or Stop). Every player, including the discarder, may throw.
**Only the FIRST throw counts** (rules.txt): a correct throw removes the cards; a wrong
throw returns them and costs a hidden penalty card at the last index — either way the
window closes and everyone else is too late. A submission may contain any number of own
and opponent cards, as long as every selected card matches the center rank (suit does not
matter). For each opponent card removed, the reacting player chooses one of their own
cards to transfer into that exact slot. Malformed requests are rejected without consuming
the window. The window/validation logic lives in `matching.MatchWindow`; the Room applies
the mutations.

## Scoring (risk-based round points, updated 2026-07-17)

Replaces the 2026-07-14 lowest-hand-wins model. **Lower cumulative is better**, and the
**only way to score negative is to call Stop and win**. A won Stop also inflates the whole
table toward `exit_score`, so passivity is punished twice — you fall behind AND move closer
to elimination:
- A **Stop caller with the strictly-lowest hand** (a tie = caught): `win_score` (default **−1**).
- **Everyone else when the caller wins**: `stop_loss_score` (default **+2**).
- A **caught** caller (tied or beaten): `penalty_score` (default **+4**); the rest take the
  routine `loss_score` (default **+1**).
- A round with **no caller** (degenerate deck-out): every active player takes `loss_score`.
- Balance rationale: winning a Stop gains 3 relative points (−1 vs +2); being caught costs 3
  (+4 vs the +1 the rest take) — so calling is correct at roughly ≥50% confidence, keeping the
  memory/judgment core intact while five passive rounds of +2 hit the default exit score of 10.
- Wrong own/cross matches keep costing a **penalty card** (raises that round's hand), not points.

A player is **eliminated** once cumulative ≥ `exit_score` (default **10**) → they spectate the rest.
A game is `rounds` rounds (default **5**) and also ends early if ≤1 player remains un-eliminated;
the **lowest cumulative** then wins.

Mid-game joiners enter as **spectators**; the host may admit them (with an optional penalty %).
At the next round boundary (`_finalize_round`) an admitted spectator becomes active at the
table's average cumulative score plus `abs(avg) * penalty%` (abs so the penalty still hurts
when the average is negative).

Host-configurable settings (see settings.py): turn_timer, match_window, preview_seconds, rounds,
exit_score, win_score, stop_loss_score, loss_score, penalty_score, num_decks. Editable on the
create screen and in the lobby.

## Preview (updated: strict flash-then-hide)

Each player sees **their own** first two cards until the host starts play or the server's 30-second
maximum expires, then all cards go face-down and you play from memory.
The client shows preview cards ONLY while the window is open; peeks (7-10, King) flash briefly then
hide. Cards are never shown persistently (fixes the old "known cards stay visible" behavior).

## Stop / end
- **Stop** can be declared at the **start of your own turn** (before drawing).
  **[decision]** not allowed in the very first orbit (everyone plays once first), matching
  Super Seven's fairness gate.
- After Stop, every other player gets **one final turn**; when play returns to the caller,
  all cards are revealed.
- **[decision]** Caller **wins iff their total is strictly the lowest** (ties → caller loses,
  consistent with Super Seven). Non-callers never score negative — the lowest hand is shown as
  the round's best hand but only a winning caller earns `win_score` (see Scoring).

## Rounds / session
- **[decision]** Super 4 is round-based: each round ends at reveal with per-player totals and
  a winner. Host can start the next round (or rematch). No cumulative elimination cap in v1
  (the rules describe a single-round win/lose); can be added later via settings.

## Table limits & timers **[decision]**
- MIN_PLAYERS=2, MAX_PLAYERS=8 (memory game; keep the table readable).
- turn_timer=30s (auto-play a discard on timeout), timeout_limit=2 (benched to spectator;
  host can admit back — same flow as late joiners), preview≤30s,
  match_window=10s max (0 disables; window also ends when the next player acts).
