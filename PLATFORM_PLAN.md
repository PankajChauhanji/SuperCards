# Multi-Game Platform — Build Plan

**Goal:** evolve the Super Seven codebase into a **shared card-game platform** that hosts multiple
variants (starting with Super Seven + Super 4, designed for 3–6 total), served from **one site**
where the host picks the game when creating a room.

**Decision already made** (see rationale below): shared **monorepo**, one deployed service,
`game_type`-driven. *Not* a separate repo, *not* a generic rules engine (yet).

---

## Guiding principles

1. **Protect production.** The live Super Seven service stays untouched until the new platform is
   proven stable. Every phase leaves Super Seven fully working.
2. **Rule of two.** Only move something into shared `core` when *both* games genuinely need it the
   same way. No speculative abstraction for hypothetical games.
3. **Lock two seams, keep the rest flexible.** The **Room interface** and the **client↔server
   protocol (`game_type` envelope)** are the only expensive-to-move parts. Scoring, powers, AI, and
   table UI stay freely per-variant.
4. **Super 4 is the stress test.** It is mechanically inverted from Super 7 (face-down/fixed-slots/
   memory/powers vs. face-up/shedding/combos). If the seams support both, they support the rest.
5. **Each phase is shippable and reversible.** No phase requires a "big bang" cutover.

---

## Current state (starting point)

The `super-4` folder already began the refactor. Status:

| Area | State |
|---|---|
| `game/core/` (`player`, `cards`, `manager`) | ✅ Split out, imports consistent |
| `game/super_seven/` (`room`, `rules`, `scoring`, `ai`) | ✅ Namespaced, tests updated |
| `game/super_four/` | 🟡 Stub only (`README.md`, empty `__init__.py`) |
| `manager.py` | ❌ Hard-imports `game.super_seven.room.Room` — no registry |
| `cards.py` `card_value()` | ❌ Rank-only; can't do Red King = −1 |
| `config.py` | ❌ All Super-Seven tunables (`HAND_SIZE=7`, `stop_penalty`, …) |
| `sockets/` | 🟡 `lobby/connection/common/social` ~90% shared; `gameplay`/`director` are SS-specific |
| Frontend | 🟡 ~40% shared shell; table/selection/gameplay layer is SS-specific |
| `game_type` concept | ❌ Does not exist anywhere (server or client) |

**Reuse math (from analysis):** backend `lobby/connection/common/social` ≈ 90% reusable;
`gameplay.py` ≈ 75% fork, `director.py` ≈ 65% fork. Frontend ≈ 40–45% reusable shell,
55–60% per-variant table rewrite.

---

## Target structure

```
game/
  core/
    cards.py         # deck + Card; suit-aware / pluggable valuation
    player.py        # base player state shared by all games
    manager.py       # RoomManager + GAME REGISTRY (game_type -> Room class)
    registry.py      # {game_type: RoomClass, settings schema, defaults}   [new]
    protocol.py      # message envelope helpers (game_type, action, state)  [new]
  super_seven/
    room.py rules.py scoring.py ai.py settings.py           # existing + settings
  super_four/
    room.py powers.py scoring.py ai.py settings.py          # to build
sockets/
  __init__.py connection.py lobby.py common.py social.py    # SHARED (game-agnostic)
  director.py                                               # shared scan loop + per-game hook
  gameplay/
    __init__.py            # dispatch by room.game_type
    super_seven.py         # SS action handlers (from today's gameplay.py)
    super_four.py          # S4 action handlers                            [new]
config.py                  # runtime/deploy only; per-game settings live in variant settings.py
static/js/
  core/     socket.js identity.js sound.js lobby.js reactions.js chrome.js  # SHARED
  seven/    table.js selection.js gameplay.js
  four/     table.js selection.js gameplay.js                              [new]
templates/
  index.html   # landing page WITH game picker
  game.html    # shared shell; loads variant bundle by game_type
```

---

# Phase 1 — Platform Foundation (seams + decoupling)

**Objective:** make the codebase multi-game *capable* without adding a second game and **without
changing Super Seven's behavior at all**. This is the only phase that touches shared/core code, so
it is done carefully and verified against the existing Super Seven test suite.

### 1.1 Game registry (the central seam)
- Add `game/core/registry.py`: a mapping `game_type -> {room_class, default_settings,
  settings_bounds, display_name, min/max_players}`. Register `"super_seven"` now; leave a documented
  slot for `"super_four"`.
- Change `game/core/manager.py`:
  - Remove `from game.super_seven.room import Room`.
  - `create_room(host_id, name, settings, game_type="super_seven")` → look up the Room class in the
    registry, store `game_type` on the room.
  - `RoomManager` type hints become the base/protocol, not the concrete `Room`.

### 1.2 Room interface (contract for the shared layer)
- Define the contract every game's Room must satisfy (informal `Protocol` / documented base):
  lifecycle (`register_player`, `detach`, `migrate_host`, `any_connected`, `any_human_connected`,
  `created_at`), state (`state`, the `STATE_*` constants), views (`public_players`,
  `public_round_state` or a generic `public_state`), a turn hook the director can call, and
  `game_type`.
- Move the shared `STATE_*` constants (`LOBBY`, `IN_TURN`, `ROUND_END`, `GAME_END`) into `core` so
  `lobby.py`/`director.py` stop importing them from `super_seven`. Game-specific sub-states stay in
  the variant.

### 1.3 Suit-aware card valuation
- `game/core/cards.py`: make valuation pluggable. Keep the default `card_value(rank)=rank` for
  Super Seven, but allow a per-game valuation (e.g. Room/scoring supplies a `value_of(card)` or
  cards carry a game-supplied valuator). **Do not** hardcode Red King into core — Super 4's scoring
  owns `rank==13 and suit in RED_SUITS → -1`.
- Verify Super Seven scoring is byte-for-byte unchanged.

### 1.4 Per-game settings
- Move Super Seven's `DEFAULT_SETTINGS`, `SETTINGS_BOUNDS`, `HAND_SIZE`, `MATCH_REQUIRES_DRAW` out
  of the shared `config.py` into `game/super_seven/settings.py` (referenced via the registry).
- `config.py` keeps only runtime/deploy (`SECRET_KEY`, `CORS_ORIGINS`, `PORT`, `FLASK_DEBUG`,
  `ROOM_CODE_LENGTH`, `EMPTY_ROOM_TTL`).
- `sockets/lobby.py` `_clean_settings` reads bounds from the room's game settings, not global config.

### 1.5 `game_type` end-to-end plumbing (client↔server seam)
- `create_room` socket payload accepts `game_type`; validated against the registry; stored on room.
- Every state broadcast (`enter_room`, `room_joined`, `public_round_state`, lobby snapshots) includes
  `game_type` so the client knows which game it's in.
- For now the client still only knows Super Seven — `game_type` is carried but unused on the client.

### 1.6 Split gameplay handlers by dispatch (no behavior change)
- Create `sockets/gameplay/` package. Move today's `gameplay.py` verbatim into
  `sockets/gameplay/super_seven.py`.
- `sockets/gameplay/__init__.py` `register()` dispatches action events by `room.game_type`. With
  only Super Seven registered, behavior is identical.
- Same treatment for `director.py`: extract the SS-specific auto-play/bot logic behind a per-game
  hook; keep the shared scan loop in `core`/shared director.

### Phase 1 — acceptance criteria  ✅ DONE (2026-07-14)
- [x] Full existing Super Seven **test suite passes unchanged** — 14/15 files green; `test_rules.py`
      holds at its pre-existing 27/29 (2 stale assertions, unchanged from baseline).
- [x] Live smoke: create room, solo bot game (human plays → bot responds), deal, `game_type` in
      payloads — no errors, no server-side exceptions.
- [x] `grep` shows no `from game.super_seven` inside `game/core/` (except `registry.py`, the wiring
      point) or the shared `sockets/*` (connection, lobby, common, social, director).
- [x] `create_room(..., game_type="super_seven")` works; unknown `game_type` rejected cleanly (both
      at the manager `ValueError` and the lobby "Unknown game type." error).
- [ ] Deployed as a service, Super Seven is indistinguishable from production. *(deferred to when a
      Render service is stood up)*

**What landed in Phase 1**
- `game/core/` = `cards`, `player`, `manager`, `registry`, `states`, `room_base` (RoomProtocol).
- `game/super_seven/` = `room`, `rules`, `scoring`, `ai`, `settings`.
- `game/core/registry.py` — game_type → GameSpec(room_class, settings, bounds, min/max players).
- `card_value(rank, suit=None)` — suit-aware-capable, default unchanged; Super 4 red-King rule
  proven expressible in a variant scoring fn without touching core.
- `config.py` trimmed to runtime/deploy + room-manager constants; SS tunables moved to
  `game/super_seven/settings.py`, surfaced via the registry.
- `game_type` plumbed: `create_room`/`create_solo` payload → room → `room_joined`,
  `public_round_state`, and the `/room` template.
- `sockets/gameplay/` package: `super_seven.py` holds the (game_type-guarded) handlers + the
  director ticker; `sockets/director.py` is now a generic scan loop dispatching per `game_type`.

> **Reversibility:** Phase 1 is pure refactor. If anything regresses, revert — no data/behavior
> migration involved.

---

# Phase 2 — Shared Shell + Game Selection

**Objective:** turn the single-game UI into a **game-agnostic shell + per-variant table bundle**, and
add the landing-page game picker. Still only Super Seven is playable, but the frontend is now
multi-game aware.

### 2.1 Extract the shared frontend shell
- Split `static/js/` into `core/` (shared) and `seven/` (Super Seven table layer):
  - **Shared → `core/`:** `socket.js`, `identity.js`, `sound.js`, plus the game-agnostic parts of
    `game.js` (connect/enter_room plumbing, lobby roster, host controls, kick, reactions dock,
    themes, rules modal + i18n, spectator-admit, turn/round chrome) → `lobby.js` / `reactions.js` /
    `chrome.js`.
  - **Super Seven → `seven/`:** `selection.js`, the hand/center rendering half of `table.js`, and the
    gameplay-event half of `game.js` (`your_hand`/`cards_played`/`table_state`/round-end reveal).
- `game.html` becomes a shell: shared chrome + an empty table region + `<script>` that loads the
  variant bundle chosen by the server-provided `game_type`.

### 2.2 Landing page game picker
- `templates/index.html` (`home.js`): add a game selector (cards/tiles for each registered game).
  Selection sets `game_type` in the `create_room` call.
- Per-game settings form: the lobby settings fields are driven by the selected game's settings schema
  (Super Seven shows `max_score`/`stop_penalty`/…; other games show their own).

### 2.3 Client consumes `game_type`
- On `enter_room`, the client reads `game_type` and dynamically loads `four/…` vs `seven/…` bundle
  and renders the correct table + action bar.
- Shared shell (rooms, roster, reactions, themes, rules) renders identically for every game.

### 2.4 Rules content per game
- `static/rules/en.html` / `hi.html` become per-game (e.g. `rules/super_seven/en.html`,
  `rules/super_four/en.html`), selected by `game_type`.

### Phase 2 — acceptance criteria  ✅ DONE (2026-07-14)
- [x] Super Seven still fully playable via the shared shell + `seven/` bundle — verified in-browser:
      solo create → lobby → start → 7-card deal, deck=38, opponent shown; backend suite 15 green.
- [x] Landing page shows a game picker; Super Seven selectable, Super 4 shown disabled "Coming soon".
- [x] Client loads the right bundle purely from server `game_type` — `game.html` includes
      `games/<game_type>/{branding,table,scripts}.html`; `window.GAME_TYPE` injected; verified
      `GAME_TYPE=super_seven` on the game page.
- [x] Rules modal loads per-game content (`/static/rules/<game_type>/<lang>.html`) — verified.
- [x] No console errors, no failed network requests across the whole flow.

**Scope note (rule of two):** the JS split is `core/` (standalone shared: `socket`, `identity`,
`sound`) + `seven/` (whole SS bundle: `table`, `selection`, `game`). The *further* extraction of the
game-neutral chrome that currently lives inside `game.js` (roster, reactions, themes, rules modal,
connection plumbing) into `core/` modules was intentionally **deferred**: with only one game it would
be guessing the seam. It happens as a cleanup once Super 4 exists and shows exactly what's shared —
Super 4's `game.js` will initially carry its own chrome, then common parts get lifted to `core/`.

> **Reversibility:** the shell/bundle split is a frontend reorg. Super Seven behavior is the
> regression oracle throughout.

**What landed in Phase 2**
- `static/js/core/` = `socket`, `identity`, `sound`; `static/js/seven/` = `table`, `selection`,
  `game`; `home.js` stays shared.
- `templates/games/super_seven/` = `branding.html`, `table.html`, `scripts.html`; `game.html` is now
  a shell including them by `game_type` and injecting `window.GAME_TYPE`.
- `app.py`: `/` passes the registry `games` list to the picker; `/room` passes `game_type` +
  `display_name`.
- `index.html` + `home.js`: registry-driven picker; selected `game_type` sent in
  `create_room`/`create_solo`; per-game settings block shown for the selected game.
- Rules moved to `static/rules/super_seven/{en,hi}.html`; fetch path is `game_type`-aware.
- `.claude/launch.json` added for the preview/dev server.

---

# Phase 3 — Build Super 4

**Objective:** implement the new game entirely inside `game/super_four/`, `sockets/gameplay/
super_four.py`, and `static/js/four/`. No shared/core changes should be needed — if one is, it means
a seam was under-designed (fix it in `core`, re-verify Super Seven).

### 3.1 Backend — game logic
- `game/super_four/room.py`: state for 4 **fixed face-down slots** per player, the initial two-card
  preview, draw→keep/discard turn, penalty cards, and the **final-orbit "Stop"** phase (every other
  player gets one last turn, then reveal).
- `game/super_four/powers.py`: handlers + targeting for card powers —
  7/8 peek own, 9/10 peek opponent, 11/12 blind swap, 13 (King) look-and-optional-swap.
- `game/super_four/scoring.py`: lowest-total-wins; **Red King (KH) = −1**; Ace=1..King=13; penalty
  cards add to total.
- `game/super_four/ai.py`: bot that plays a memory game reasonably (can start simple/random, improve
  later).
- `game/super_four/settings.py`: `HAND_SIZE=4`, power config, penalty rules, min/max players.
- Register `"super_four"` in `game/core/registry.py`.

### 3.2 Backend — socket handlers
- `sockets/gameplay/super_four.py`: the Super 4 action vocabulary —
  draw → keep/discard, **real-time match reactions** (first-to-react on a discard, own-card and
  opponent-card matching with penalty on miss), power targeting, and Stop.
- Reuse shared `lobby/connection/common/social` untouched.
- Add the Super 4 turn/timeout behavior to the director's per-game hook.

### 3.3 Frontend — Super 4 table
- `static/js/four/table.js`: render 4 fixed face-down slots (labeled 1–4) per player, opponents'
  slots, the drawn-card decision UI, peek reveals (visible only to the acting player), swap
  animations, and match-reaction affordances.
- `static/js/four/selection.js`: slot targeting + power flows (peek/swap/king) + draw decision.
- `static/js/four/gameplay.js`: Super 4 event model (`your_slots`/peek/swap/match-result/round-end).
- Super 4 table markup section + power-targeting modals in the shell.
- `static/rules/super_four/en.html` + `hi.html`.

### 3.4 Enable in the picker
- Flip Super 4 from "coming soon" to selectable on the landing page.

### Phase 3 — acceptance criteria  ✅ DONE (2026-07-14)
- [x] A full Super 4 round is playable end-to-end — verified in-browser: deal, 2-card preview, draw→
      keep/discard/match, powers, Stop, reveal, scoring with **King of Hearts = −1** and emptied slots.
- [x] **Cross-player real-time matching** (Task #18) — implemented as a short blocking match window
      after each discard: any non-discarder may match the center vs. their own or an opponent's card;
      first success wins, wrong = penalty; opponent-match auto-gives your highest card; window expires
      via the director. Bots react only to matches they know. Verified end-to-end over sockets +
      15 engine checks. `match_window=0` disables it.
- [x] Bots fill a Super 4 table; solo play works — the bot drew, played, and **correctly called Stop
      and won** a round in the browser test.
- [~] Reconnection restores correct known state via `your_view` (only cards you know) — mechanism in
      place and unit-tested at the room level; a dedicated multi-client reconnect test is a follow-up.
- [x] Super Seven remains fully working — full suite **19 files green, 0 regressions**.
- [x] Unit tests for Super 4 scoring/room/powers/stop + hidden-information leakage tests — 75 checks green.

**What landed (Phase 3 core)**
- `game/super_four/`: DESIGN.md, settings.py, scoring.py (KH=−1), room.py (4 slots + per-viewer
  `known` knowledge model, draw/keep/discard/match-own, Stop/final-orbit/reveal, cumulative scoring),
  powers.py + Room `power_*` (7/8 peek own, 9/10 peek opp, 11/12 blind swap, 13 King look+swap), ai.py.
- `sockets/gameplay/super_four.py`: handlers (`s4_draw/keep/discard/match_own/power_*/stop/next_round`,
  guarded on game_type) + director ticker (timeout auto-play + bot) + presenter dealer (`your_view`).
- Shared `sockets/presenter.py` (per-game private-deal hook); lobby now calls `presenter.deal()`.
- Frontend: `static/js/four/game.js` + `templates/games/super_four/{branding,table,scripts}.html`;
  4-slot table, preview, drawn-card decision, power targeting, self-only peek reveals, round-end
  reveal, Next-round loop. Rules `static/rules/super_four/{en,hi}.html`. Registered + picker enabled.

> **Client hidden-info model (v1 decision):** cards a player *knows* (preview + peeks) are shown
> persistently to that player; everything else is face-down; opponents' faces only at reveal. This is
> server-consistent (the `known` set moves/clears knowledge on swaps). A stricter flash-then-hide
> "memory" mode can be a later settings toggle.

---

## Cross-cutting: all the cases to cover

These apply across phases — call them out explicitly so nothing is missed.

### Hidden-information / cheating (critical for Super 4)
- Server never sends a player their own face-down card values except when a power reveals them.
- Peek reveals (7–10, King) are sent **only** to the acting player's socket, never broadcast.
- Blind swap (11/12) broadcasts that a swap happened + positions, **not** values.
- On reconnect, a player regains only the knowledge they legitimately had (own preview + powers
  used), not full hand state. Store "known-to-player" flags server-side, not client-side.
- Spectators/late-joiners never receive hidden values.

### Real-time match reactions (Super 4)
- First-to-react wins; server arbitrates race with a single authority (in-memory, single worker —
  fine). Losers get a clear "too late" signal.
- Wrong match → reveal chosen card, return to slot, apply penalty card, update totals.

### Lifecycle cases (both games)
- Reconnect at every phase (lobby / mid-turn / round-end / game-end).
- Host disconnect → host migration works per game.
- Player leaves mid-game; turn skips correctly; bot takeover if configured.
- Timeout / auto-play per game's rules; 3-timeout kick.
- Empty-room reaping unchanged.
- Min/max players enforced per game (from registry).

### Settings & validation
- Per-game settings schema; host-supplied values clamped to that game's bounds.
- Unknown/invalid `game_type` rejected at create time.
- A room's `game_type` is immutable once created.

### Mixed-game platform
- Two rooms of different games coexist in one process without interference (rooms keyed by code).
- Landing page reflects only registered/enabled games.

### Deck / cards
- Red King = −1 works for Super 4 and does **not** leak into Super Seven scoring.
- Card SVGs already exist for all 52 + back; no asset work needed.

---

## Testing strategy

- **Phase 1:** existing Super Seven suite is the regression oracle — must stay 100% green. Add tests
  for the registry and `game_type` plumbing.
- **Phase 2:** frontend smoke (manual + optional headless): shell loads, picker works, bundle loads
  by `game_type`.
- **Phase 3:** new `tests/super_four/` — rules, scoring (Red King, penalties), powers, matching race,
  Stop/final-orbit, and **hidden-information leakage tests** (assert the server payload to player A
  never contains A's own unrevealed values, and never contains opponents' values).
- Keep `tests/` mirroring the package layout (`tests/super_seven/`, `tests/super_four/`, `tests/core/`).

Local run: `pip install -r requirements.txt` then `python -m pytest -q`. (Dev deps: add `pytest` to
requirements-dev.)

---

## Deployment & cutover

- **During Phases 1–3:** deploy the evolving platform as a **new, separate Render service** (new URL):
  `render.yaml` names it **`super-cards`** → `super-cards.onrender.com`, deployed from the platform
  branch. The live `super-seven.onrender.com` service keeps running the untouched `master` code.
- **Single-worker rule still absolute:** in-memory room state → `python3 app.py` (eventlet), one
  worker. Never scale to multiple workers.
- **Cutover (only after Phase 3 is stable):** point the primary domain at the platform service. This
  is a DNS/config change, not a code change, because both games share the codebase.
- **Rollback:** repoint the domain back to the old service. Because production code was never
  modified, rollback is instant and risk-free.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Under-designed seam forces core changes during Phase 3 | Design Room interface + envelope against *both* games up front; treat any Phase-3 core edit as a seam fix + Super 7 re-verify |
| Regression in live Super Seven | Never edit the `main` folder; Super 7 suite green every phase; separate service until cutover |
| Hidden-info leak in Super 4 | Server-authoritative visibility; dedicated leakage tests; per-socket targeted emits |
| Real-time match race conditions | Single-worker in-memory arbitration; explicit first-wins with server timestamp ordering |
| Over-abstraction slows delivery | Rule of two — abstract only what Super 7 + Super 4 both prove they share |
| Frontend bundle split breaks shared chrome | Super 7 via the shell is the oracle through Phase 2 |

---

## Definition of done (whole effort)

- One site, one service; host picks Super Seven or Super 4 at room creation.
- Both games fully playable, with reconnection, bots, spectators, reactions, themes, rules, host
  migration.
- Shared shell + core; per-game logic isolated in `game/<variant>/`, `sockets/gameplay/<variant>.py`,
  `static/js/<variant>/`.
- Adding game #3 = register a Room class + settings + drop in a table bundle. No shared-code surgery.
- Live Super Seven never regressed; cutover and rollback are config-only.
</content>
</invoke>
