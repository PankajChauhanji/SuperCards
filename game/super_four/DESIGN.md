# Super 4 — implementation design & locked decisions

Source rules: PLATFORM_PLAN.md + the Super 4 rules. Where the rules were silent or
ambiguous, the decision made here is marked **[decision]** so it can be revisited.

## Core model
- **4 fixed slots** per player, indexed 0–3 (shown to users as 1–4). A slot holds a
  Card or is **empty** (removed via matching) — empties count as 0 and lower your total.
- **Preview:** at deal, each player privately learns **slots 0 and 1** (their "first two").
  Client shows them for a countdown, then hides. Server marks those two as known-to-owner.
- **Card values:** Ace=1 … King=13. **[decision]** The rules name "the Red King (King of
  Hearts)" as −1 → **only King of Hearts (KH) = −1**; King of Diamonds is a normal 13.
- **Deck:** standard 52 (num_decks configurable). Reshuffle the discard back into the draw
  pile when it runs out (keep the current center card out).

## Turn flow
1. **Draw** the top card — its face is **public** (everyone sees the drawn card).
2. Then exactly one of:
   - **Keep**: choose a slot; drawn card goes there (face-down), the old card goes to the
     center face-up. **No power triggers** on a kept card.
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

## Cross-player matching ("Matching a Card Discarded by Another Player")
Whenever a card lands on the center, a **match window** opens (config
`match_window` seconds). Any player may attempt:
- **Match own card**: pick own slot; correct → discard it (empty slot); wrong → reveal +
  penalty card.
- **Match an opponent's card**: pick opponent slot; correct → remove their card and **give
  them one of your own cards** to fill it (your total drops); wrong → reveal + penalty.
First **successful** attempt closes the window ("only the first who reacts successfully").
Wrong attempts penalise the actor but leave the window open until success or timeout.
**[decision]** v1 builds the turn loop + powers + Stop first; the real-time window is a
distinct increment (Task #18) so the core game is playable and testable earlier.

## Scoring (round-points model, updated 2026-07-14)

Replaces the original cumulative-hand-total model. **Lower cumulative is better.**
Each round the lowest hand wins; the running score updates by deltas:
- Round **winner(s)** (strictly-lowest hand; ties share): `win_score` (default **−3**).
- Every other active player: `loss_score` (default **+1**).
- A caller who calls **Stop but is caught** (not a winner): `penalty_score` (default **+3**),
  instead of the loss.
- Wrong own/cross matches keep costing a **penalty card** (raises that round's hand), not points.

A player is **eliminated** once cumulative ≥ `exit_score` (default **10**) → they spectate the rest.
A game is `rounds` rounds (default **5**) and also ends early if ≤1 player remains un-eliminated;
the **lowest cumulative** then wins.

Host-configurable settings (see settings.py): turn_timer, match_window, preview_seconds, rounds,
exit_score, win_score, loss_score, penalty_score, num_decks. Editable on the create screen and in
the lobby.

## Preview (updated: strict flash-then-hide)

Each player sees **their own** first two cards for `preview_seconds` (server-timed via
`preview_deadline` / `preview_seconds_left`), then all cards go face-down and you play from memory.
The client shows preview cards ONLY while the window is open; peeks (7-10, King) flash briefly then
hide. Cards are never shown persistently (fixes the old "known cards stay visible" behavior).

## Stop / end
- **Stop** can be declared at the **start of your own turn** (before drawing).
  **[decision]** not allowed in the very first orbit (everyone plays once first), matching
  Super Seven's fairness gate.
- After Stop, every other player gets **one final turn**; when play returns to the caller,
  all cards are revealed.
- **[decision]** Caller **wins iff their total is strictly the lowest** (ties → caller loses,
  consistent with Super Seven). Non-callers: lowest total is the round winner.

## Rounds / session
- **[decision]** Super 4 is round-based: each round ends at reveal with per-player totals and
  a winner. Host can start the next round (or rematch). No cumulative elimination cap in v1
  (the rules describe a single-round win/lose); can be added later via settings.

## Table limits & timers **[decision]**
- MIN_PLAYERS=2, MAX_PLAYERS=8 (memory game; keep the table readable).
- turn_timer=45s (auto-play a discard on timeout), timeout_limit=3 (kick), preview=10s,
  match_window=5s.
