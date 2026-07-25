# Super Cards Platform — Thoughts, TODOs & Improvements

Working notes for the multi-game platform (Super Seven + Super Four + Bluff).

**Scope:** this repo only. The standalone `super_seven_cards-main` project is frozen
production and is **not** touched from here.

---

## 0. Context / verdict on the refactor

The reuse refactor (one Super Seven game → a `game_type`-driven platform hosting three
games) was a **good call and is validated**: a third, mechanically-inverted game (Bluff)
was built on the same seams without reworking them. The backend abstraction is sized right
— thin seams (registry + `RoomProtocol` + shared states + presenter/director hooks), no
speculative "generic rules engine." The expensive, bug-prone plumbing (lobby, reconnection,
host migration, spectator admit, timer director) is shared exactly once.

What it really is: a **shared lobby/lifecycle platform**, not a shared *game engine* — each
game keeps its own gameplay vocabulary, room, scoring, and client bundle by design. That's
correct; just naming it so expectations stay honest.

The debt is on the **frontend**, not the backend (see §1).

---

## 1. Frontend chrome duplication  — ✅ DONE (2026-07-25)

**Problem (was).** Each game's client re-implemented near-identical "chrome": reactions dock,
table themes, rules modal + i18n, spectator-admit modal, mute, copy-code. `four/game.js` was
~965 lines and a large tail duplicated the Super Seven bundle. `PLATFORM_PLAN.md` §2.2 had
deferred lifting this into `core/`.

**What landed.** Shared chrome extracted into self-initializing `static/js/core/` modules
(loaded in `game.html` after the existing core scripts, before the variant bundle):
- [x] `core/reactions.js` — dock/fab/panel, recent-emoji, float animation, `reaction` event
- [x] `core/themes.js` — dropdown wiring + `SS.themes.apply(theme)` / `syncVisibility(isHost)`
- [x] `core/rules_modal.js` — fully self-contained per-game rules fetch + EN/HI toggle
- [x] `core/chrome.js` — mute, copy-code, and `SS.openSpectatorModal(id, name)`
- [x] `seven/`, `bluff/`, `four/` bundles now delegate: theme calls go through `SS.themes.*`
      (thin `syncTableTheme`/`syncThemeSelectorVisibility` shims kept so call-sites are
      unchanged); reactions/rules/mute/copy/spectator blocks deleted. Net −285 lines across
      the three bundles.
- [x] Verified in-browser (solo) for all three games: no console errors; rules load per
      `game_type`; theme apply toggles `<body>` class; mute painted; Super 4 reaction
      round-trips and floats.

**Scope note.** Turn-timer / round-chip were intentionally left per-variant — Super 4's timer
diverges (preview + match-window countdowns) from Super 7/Bluff's turn+pick timers. Extracting
it would mean forcing a shared shape over genuinely different logic; revisit only if a 4th game
proves the shape is common.

Dev convenience added: `/.claude/launch.json` (repo root) runs the app via the `env_seven`
venv for the preview server.

## 2. `core/player.py` concept leakage — ✅ DONE (2026-07-25)

Investigated actual usage across the three games:
- `hand` / `card_count` / `public_view()` are shared by **Super Seven + Bluff** (both
  hand-based) → rule of two satisfied, they legitimately stay in core.
- Super 4 never calls `public_view()` — it builds its own slot-aware `public_players()`, so
  none of the hand/safe fields ever reach a Super 4 client.
- `is_safe` was the only truly single-game field (Super Seven). Bluff had two **dead** uses:
  a no-op `player.is_safe = False` reset (never set True) and a round-end "Safe" badge that
  never fired.

**Decision (option b, justified):** one boolean doesn't justify a Player subclass, so instead:
- [x] Rewrote `core/player.py` with fields grouped/labelled by ownership (all-games /
      hand-based / Super-Seven-only) and documented that Super 4 uses its own `public_players()`.
- [x] Removed Bluff's two dead `is_safe` uses (`game/bluff/room.py`, `static/js/bluff/game.js`)
      so Super Seven is now the sole real owner of `is_safe`.
- [x] Verified: 14 engine/logic tests pass (they construct Players + call
      `public_players`/`public_view`); all three games load clean in-browser.

## 3. Docs hygiene — ✅ DONE (2026-07-25)

- [x] `rules.txt` scoring updated to the implemented risk-based model, then **removed** (raw
      source rules no longer needed; README + `static/rules/super_four/{en,hi}.html` are the
      source of truth and already match the code).
- [x] Verified no remaining doc drift: Super Seven defaults (max_score 100 / stop_penalty 40 /
      win_discount 5) match the README rulebook; Bluff settings carry no scoring numbers to drift.
- [x] Put the "keep in sync" convention where the change happens — a docstring note at the top
      of each `game/<variant>/settings.py` listing the docs to update together (README rulebook,
      rules HTML, and DESIGN.md for Super 4).

## 4. Home page redesign — ✅ DONE (2026-07-25)

Reworked the landing page (`templates/index.html`, `static/js/home.js`, `static/css/*`):
- [x] Game selection is now its **own panel** ("① Choose your game"), separated from the
      create/play actions — no longer crammed into the create-room block.
- [x] Three games on **one row** as card-style tiles (Super 7 / Super 4 / Bluff): each has a
      playing-card emblem, short name, one-line descriptor, and a **per-game accent** pulled
      from the app palette (7=vermilion, 4=green, Bluff=violet) instead of the old off-palette
      purple. Selected tile gets an accent ring + glow.
- [x] Step-based flow (① game → ② name + Create/Play) with a compact inline join row.
- [x] **Removed the game-settings block from home** — create/solo now send no settings; the
      server fills defaults and the host tunes them in the lobby (verified: Super 4 lobby shows
      all 10 settings at their defaults).
- [x] Mobile: tiles stay one row (3-col grid, emblems shrink < 400px), action buttons stack.
      Verified at 360px and desktop; no console errors; create/solo/join all work.

## 5. Lobby redesign + reusable settings — ✅ DONE (2026-07-25)

De-cluttered the lobby and made it a shared, game-agnostic component:
- [x] New `static/js/core/lobby.js` — one renderer for roster + settings + start, reused by all
      three games. A game supplies only its settings **field schema**
      (`SS.Lobby.init({ youId, fields: [{key,label,min,max}] })`) and calls `SS.Lobby.render(view)`.
      Deleted each bundle's duplicated `renderLobby`/`renderLobbySettings` (seven −140, bluff −126,
      four −102 lines).
- [x] **Players / Settings tabs** (segmented control) with an always-visible Start row, replacing
      the stacked roster+settings clutter. Players tab shows a live count badge.
- [x] **Reusable settings panel**, identical design for every game — differs only in fields,
      labels, and count (Super 7 = 6, Super 4 = 10, Bluff = 3). Responsive `auto-fit` grid:
      multi-column on desktop, single column on mobile. Host-editable (built once per role so
      in-progress edits aren't wiped) vs. read-only for guests.
- [x] **Per-game topbar brand** — card emblem + short name + accent, matching the home tiles
      (Super 7 = red "7", Super 4 = green "4", Bluff = violet "?"); updates automatically per the
      room's `game_type`.
- [x] **Kick button redesigned** — subtle round icon, muted by default, red on hover; host-only,
      never shown for self or the bot. (Was an ugly bordered box.)
- [x] **Topbar controls stay on ONE line at every width** — no more mobile wrapping. Labels
      collapse to icons under 480px (Rules/Quit/theme become icon buttons; theme name hidden);
      full labels on desktop.
- [x] Verified in-browser for all three games (solo): correct branding, tabs switch, correct
      field counts, Start works, no console errors; desktop + mobile layouts checked.

## 6. Brand symbols (home + per-game) — ✅ DONE (2026-07-25)

Gave the platform and each game a consistent card-symbol identity in the shared "playing-card"
style of the original `super_seven_symbol.svg` (red/dark card, gold border + glyph):
- [x] New SVGs: `super_cards_symbol.svg` (home — gold **jester hat** = the platform's wild card),
      `super_four_symbol.svg` (green top, gold **4**), `bluff_symbol.svg` (violet top, gold **?**).
      Super Seven keeps its original `super_seven_symbol.svg`.
- [x] Home header rebranded to **"SUPER CARDS"** + the joker symbol (was "SUPER SEVEN" + 7 card).
- [x] Per-game topbar brand reordered to **name first, then symbol** (matching the original
      Super Seven treatment): "Super 7" + 7-card, "Super 4" + 4-card, "Bluff" + ?-card. Shown in
      both lobby and game window; updates automatically per the room's `game_type`.
- [x] Bonus fix: added `is_bot` to `core/player.py` `public_view()` so Seven/Bluff (which use it)
      now correctly show a **Bot** badge and hide the kick control for the bot — matching Super 4.
- [x] Verified in-browser (all three games + home): symbols load & render, topbars consistent,
      bot no longer kickable, no console errors; 14 engine tests still green.

## 7. Game-window UI: hand tray, mobile topbar, card faces — ✅ DONE (2026-07-25)

Three fixes to the in-game table (all three games):
- [x] **Self-hand is a responsive elevated "tray."** Root cause of overflow: `.hand` had lost
      `flex-wrap` (`gap:0`) and Bluff used a `-50px` overlap with no wrap. Restored `flex-wrap`
      + gap, wrapped the hand in an elevated panel (`.myhand-wrap` / Super 4 `.s4-mine`), and
      added mobile card-size shrink so cards wrap tidily and **never leave the felt**. Verified:
      Super 7 = 4-above-3-below on mobile; Super 4 = 4-slot tray; Bluff = 26 cards wrap ~4/row
      and pile below (no horizontal overflow). Bluff overlap removed in favor of compact wrapping.
- [x] **Mobile topbar hamburger.** In-game the row (timer + round + sound/theme/rules/quit)
      crowded the game name. Wrapped the four action controls in `.topbar-actions` and added a
      `#topbar-menu-btn` hamburger (shared `core/chrome.js` toggle). ≤600px: controls collapse
      into a dropdown menu (labelled rows); desktop keeps them inline. Removed the old
      icon-only-on-mobile hack.
- [x] **Better face cards.** The J/Q/K were muddy hand-drawn portraits. Rewrote them in
      `tools/generate_cards.py` as clean **gold emblems that say what they are** — Jack = sword,
      Queen = tiara, King = crown+cross — over a large suit glyph (consistent with number cards).
      Regenerated all 52 + back; legible at ~60px table size and elegant enlarged.
- [x] Verified in-browser across the three games on mobile (375px) and desktop; no console errors.

## 8. Scores + Action History polish — ✅ DONE (2026-07-25)

- [x] **Super 4 gets a progress bar.** Its scoreboard now matches Super Seven: colour swatch,
      host crown, name, score, and the green→red `.sb-bar` strip — here filling toward
      `exit_score` (a negative score = doing well = empty bar).
- [x] **Names never wrap or overrun.** New shared helper `core/format.js` `SS.shortName()`:
      two words → "First L" (full first + last initial), long single name → clipped with "…".
      Applied to every scores row, opponent seat, and the self card-pile name across all three
      games, with CSS ellipsis as a backstop. The redundant "(you)" text became a compact `you`
      pill so the name keeps its width. The action-log actor name is shortened too.
- [x] **Mobile layout: stack Scores over Action History full-width** (they were side-by-side and
      too narrow — names clipped, log lines wrapped 3–4×). Full width → names fit and log lines
      sit in one or two rows. Desktop keeps the 280px side column.
- [x] **Action History is compact & thinner** — switched from the wide handwritten face to the
      body font at 0.78rem / weight 400, tighter padding, line-height and list gap.
- [x] Verified across all three games on mobile (375px) + desktop; no console errors.

---

## Super 4 — game-specific notes & ideas

(Backlog for when we actively iterate on Super 4. Add detail as we decide direction.)

- [ ] **Bot depth.** `ai.py` is a fair memory heuristic but never attempts opponent-card
      matches during a match window (it only matches its own known cards) and uses a fixed
      `STOP_THRESHOLD`. Room to make Stop timing and matching smarter.
- [ ] **Reconnection test.** DESIGN/plan mark a dedicated multi-client reconnect test as a
      follow-up — the `known`-set restore is unit-tested at room level but not end-to-end.
- [ ] **Match-window UX.** Confirm the two-step "select cards → choose transfer cards" flow is
      intuitive under the live timer; consider clearer affordances / countdown feedback.
- [ ] (placeholder — add the specific Super 4 changes we want to make here.)

---

## Guardrails (don't regress these)

- Single worker only — in-memory room state; `python3 app.py` (eventlet), never multi-worker.
- Hidden information is server-authoritative: never send a card face for a position the
  recipient doesn't legitimately `known`. Peeks go to the acting socket only.
- Adding a game = register a Room class + settings + a table bundle. No shared-core surgery;
  if a core change seems required, treat it as a seam fix and re-verify the other games.
- Don't touch the frozen `super_seven_cards-main` project.
