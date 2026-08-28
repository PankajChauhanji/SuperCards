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

## 9. Android app (TWA) + mobile hardening — ✅ DONE (2026-08-08)

Packaged the site as an installable Android app and closed the gaps that only
show up once it runs as an app rather than a browser tab. See
`docs/discussion_future_installation.md` for why TWA was chosen over Capacitor.

**Android wrapper** — new `twa/` folder (see `twa/README.md`):
- [x] Signed APK + AAB via Bubblewrap, package `com.pankajchauhan.supercards`.
      The APK holds **no app code** — it opens the live site, so a server deploy
      updates the app with no rebuild.
- [x] `/.well-known/assetlinks.json` route in `app.py`, driven by
      `TWA_PACKAGE_NAME` / `TWA_SHA256_FINGERPRINT` in `config.py`. Verified the
      served fingerprint matches the APK's signing certificate exactly.
- [x] Keystore lives **outside the repo** at `~/android-toolchain/keys/` and is
      gitignored. Losing it means no in-place updates — back it up.

**Install experience** — `beforeinstallprompt` was never handled, so install was
manual-instructions-only:
- [x] New `core/install.js`: real one-tap **Install now** button; platform-filtered
      steps (Android users no longer scroll past iPhone steps); install entry
      points hide once installed. Loaded from `<head>` — Chrome fires
      `beforeinstallprompt` early enough to beat a bottom-of-body script.

**Mobile hardening:**
- [x] `core/connection.js` — Android freezes a backgrounded WebView's network, so
      a resumed phone holds a socket that only *looks* alive. Forces the check on
      `visibilitychange`/`focus`/`online` and shows a "Reconnecting…" banner.
      State resync was already free (every bundle re-emits `enter_room` on connect).
- [x] `core/wakelock.js` — Screen Wake Lock so the phone stops sleeping while you
      wait out an opponent's turn. Re-acquires on every return to visibility, since
      the browser always releases it on hide. Room pages only.
- [x] `core/quit.js` — Android back button now routes through the same confirm as
      the Quit button via a sentinel history entry. Previously back dropped you out
      of a live game silently, with no browser chrome to fall back on.
- [x] `css/safe-area.css` — the pages set `viewport-fit=cover` but **nothing used
      `env(safe-area-inset-*)`**, so content could sit under the notch and gesture
      bar. Must load **last**: it re-states paddings owned by `lobby.css`/`table.css`/
      `reactions.css`, and would lose on source order anywhere earlier.

**Cold-start experience** — the free tier sleeps and takes ~20-50s to wake, which
as an *app* reads as broken rather than slow:
- [x] `sw.js` was making it worse: `networkFirst` waits on the network, and a
      sleeping host doesn't *fail*, it stalls — so the SW blocked for the whole
      nap instead of using its cache. The landing page now races the network
      against a 2.5s timeout and paints from cache. Room pages stay strictly
      network-first: a 4-char room code gets reused, and a stale one would boot
      the player into the wrong game's bundle.
- [x] `core/waking.js` + styles — a cached shell that can't reach the server looks
      broken, so a branded screen covers the first connect: dealing-card animation,
      rotating per-game tips, an honest "the server naps when idle" note after 9s,
      and a Reload button after 45s. Appears only after 1.2s, so a warm server never
      flashes it. Reconnects mid-session stay with `connection.js`'s lighter banner.
- [x] Verified by stopping the server outright: page still painted from cache,
      overlay appeared, tips rotated, and it tore down cleanly when the server
      returned. No flash on a warm load; mobile 375px fits with no overflow.

**Bug found in passing:** `core/socket.js` did `window.SS = {...}` — a hard
overwrite that silently wiped any module registered before it. Every other core
module merges; this one was the outlier. Now merges too.

- [x] Verified across all three games: modules register, back guard arms, banner
      appears on transport drop and clears on reconnect, no console errors.

> **Not verified on real hardware yet:** the native install prompt and the wake
> lock both need a real device (an automated browser reports the page as hidden,
> which correctly refuses a wake lock). Logic is unit-verified with stubs.

## 10. Hardening: enforce the guardrails instead of documenting them — ✅ DONE (2026-08-20)

The four guardrails at the bottom of this file were prose, upheld by memory. Each is now
enforced by something that fails. No gameplay behaviour changed.

**One command to run everything** — `run_tests.py`:
- [x] `tests/` had grown four different shapes of test file and no runner, so "the suite is
      green" meant someone ran a dozen files by hand. One command now runs all of them,
      boots and tears down its own server for the socket tests, **frees the port**, and
      returns a single exit code.
- [x] Found `test_s7_batch1.py` **silently dead**: pytest-shaped (`def test_batch()` with
      `assert all(results)`) but with no `__main__` guard, so running it did nothing and
      exited 0. It has now actually run for the first time — and passes.
- [x] `test_bluff_logic.py` had 2 real failures, both **stale assertions**: Show is
      deliberately two-phase (`apply_show` decides, `resolve_show` moves the pile, so the
      client can animate the reveal) and the test asserted post-resolution hands after only
      the first phase. Production wires both phases correctly (`sockets/gameplay/bluff.py`
      111→119 human, 224→231 bot); the test was fixed, not the code.
- [x] `test_bluff_9.py` / `test_bluff_deep.py` are print-only exploration scripts with no
      assertions. They are reported as **UNSCORED** every run rather than counted green —
      a test that cannot fail is not coverage.

**Hidden information — from discipline to enforcement** (the highest-severity guardrail):
- [x] `tests/test_leak_fuzz.py` — plays ~7,300 random-but-legal actions across all three
      games and, after every action, re-derives what each viewer may know and asserts no
      view exceeds it. Detection keys on the `Card.to_dict()` shape (a dict with `rank` and
      `suit`), so a player named "AS" cannot false-positive. Verified by injecting four real
      leaks, including the subtle one — replaying a *peeked* card into `private_view`, which
      only the strict preview-window rule catches. All four were caught.
- [x] `sockets/audience.py` — the ~55 emit sites relied on the author remembering
      `to=player.sid` over `to=room.code`; one slip broadcasts a hand and **nothing fails**.
      Every emit now routes through one guard that scans room-wide payloads against the
      game's public set. Zero call-site churn: handlers import `emit` from here instead of
      flask_socketio (one line per module) and `socketio.emit` is wrapped for the
      director/bot paths.
- [x] Fails safe by design: **logs** in production (a false positive must never break a live
      game, and payloads are never rewritten), **raises** under FLASK_DEBUG and in the test
      suite. `LEAK_GUARD=raise|log|off` overrides.
- [x] `game/<variant>/visibility.py` — one definition of "publicly visible", shared by the
      guard and the fuzzer so they cannot drift. Bluff's is the strictest: the empty set,
      because seeing the pile does not merely help, it solves the game.

**The "adding a game is just a registration" claim, made executable:**
- [x] `tests/test_platform_contract.py` — 58 checks looping every registered game: full
      `RoomProtocol`, settings/bounds key parity, every default inside its own bounds,
      presenter dealer, director ticker, visibility oracle, template partials, rules HTML per
      language, and that every JS file `scripts.html` loads actually exists.
- [x] `app.py` hardcoded `ready = {...}`, so registering game #4 would have left it silently
      absent from the picker. Moved onto `GameSpec.ready`.
- [x] Surfaced a latent protocol mismatch: **Bluff has no `round_end_payload`** though
      `RoomProtocol` declares it. Not a live bug — Bluff never assigns `STATE_ROUND_END`, so
      `sockets/lobby.py:189` is unreachable for it. Rather than add dead code, `GameSpec`
      now carries `has_rounds`, and the contract test requires the method **iff** a game
      claims rounds (and requires its *absence* otherwise, so the flag can't be a get-out).

**Restarts no longer end live games** — `game/core/store.py`:
- [x] Rooms are snapshotted on SIGTERM and every 20s, and restored on boot. Clients already
      re-emit `enter_room` on connect, so recovery is close to invisible.
- [x] Pickle, deliberately: rooms are pure state machines, so it captures Super 4's per-viewer
      `known` sets and live `MatchWindow` with no per-game `to_dict`/`from_dict` pair for every
      future field to be forgotten in. Pickle's weakness is version skew, which lands exactly
      on the deploy case — so the snapshot is **gated on a fingerprint of the game/socket
      source**. Same code (crash, idle restart) → restore; changed code (deploy) → discarded
      and logged, because a table that looks right and plays wrong is worse than a fresh start.
- [x] Timestamps are rebased by the downtime, so a 3-minute outage doesn't eat the active
      player's turn. Stale sids/`connected` flags are cleared.
- [x] Bug caught in my own design while testing: `created_at` feeds only the empty-room
      reaper, and restored rooms start with nobody connected — so a room older than
      `EMPTY_ROOM_TTL` would be reaped moments after boot, destroying the very game the
      snapshot saved. Restore now resets it, granting a full reconnect window.
- [x] Verified end-to-end for real: mid-play room created over a socket, `SIGTERM`, restart,
      room still present and `/room/<code>` still serving. Plus 47 unit checks.

**Docs that can't drift:**
- [x] `README.md` documented `gunicorn -w 1` and `Procfile` used it, while `app.py`'s own
      docstring says gunicorn breaks `start_background_task()` and `render.yaml` correctly
      uses `python3 app.py` — three answers to "how do I start this", one contradicting the
      code. All aligned on the eventlet path.
- [x] `tests/test_settings_docs.py` — Super 4's tunables were restated in prose in three
      other files. Prose is right for a rules page, so the duplication is now *checked*
      rather than generated away: 21 claims pin each documented number to its registry
      default. Verified by changing `exit_score` in code — all three docs flagged as DRIFT.
- [x] Fixed `DESIGN.md` contradicting itself — its Rounds section still said "no cumulative
      elimination cap in v1" (the 2026-07-14 model) directly below a Scoring section
      describing `exit_score` elimination (the 2026-07-17 rewrite).

**Observability:**
- [x] `/healthz` — pid, uptime, room counts by game, connected players, and a per-process
      `boot_id`: two calls returning different ids means more than one process is serving,
      which is the split-room failure the single-worker rule exists to prevent. Counts only,
      never room codes — a code is the only credential needed to walk into someone's game.

**Closed the suite's biggest blind spot:**
- [x] Every pre-existing socket test drove Super Seven; Bluff and Super 4 had **no
      end-to-end socket coverage at all**. `tests/test_all_games_socket.py` walks all three
      through create → enter → start → private deal → a real action.

Suite: **29 files, 27 pass, 2 unscored, ports released.**

## 11. Mobile table sheet — Scores + History on demand — ✅ DONE (2026-08-20)

On phones the two collapsed panels cost **~104px above the felt before a card was dealt**,
and the seats already show every player's score — so most of that space was buying a
duplicate. Desktop is untouched: the side column is the right design there, and nothing in
this change applies above 720px.

**What it is.** One button in the existing reactions dock opens a bottom sheet with
**Scores / History** tabs. Considered and rejected: two separate FABs (three floating
targets crowding the bottom edge, where the hand fan and action bar already live) and a
permanent toggle strip under the header (still pays 32px rent forever for something glanced
at twice a round).

- [x] `static/js/core/table_sheet.js` + `static/css/table_sheet.css` — one shared component,
      **no per-game changes at all**. All three table partials already ship identical
      scoreboard markup and ids, so the component *relocates the existing*
      `#sb-players` / `#action-log` nodes into the sheet and puts them back on desktop.
      Every game keeps writing to the same ids and does not know it happened — no second
      copy of either panel to keep in step.
- [x] The button nests inside `.reaction-dock` rather than opening a new floating position:
      that corner is already the one spot proven clear of the hand tray on every felt (see
      the comment on `.reaction-dock` in reactions.css), and each game bundle already reveals
      the dock when the table appears, so show/hide timing comes for free. It sits *above*
      the reactions button, which keeps its established spot.
- [x] **Unread dot.** The real cost of hiding the log is attention, not space — off-screen,
      you stop noticing anything happened. A MutationObserver on `#action-log-list` raises a
      dot while the sheet is closed (or while Scores is showing); watching the list rather
      than hooking `action_log.js` means it keeps working for any future game.
- [x] **Turn-aware dismiss.** A sheet is welcome while you wait and wrong the moment you have
      to act, so it closes on the *transition* into your turn (`.my-seat.active`, set by
      core/seats.js from each game's own is-my-turn flag). Deliberately only on the
      transition: closing whenever it is your turn would make the sheet unopenable then.
      Super 4 renders its own seats and has no `#myseat`, so there it closes on the first tap
      outside — fine, since its action bar sits inside the felt rather than under the sheet.
- [x] Remembers the last tab per session: mostly Scores in Super 7, but History repeatedly
      during a contested Bluff round, and re-tapping every time would grate.
- [x] Verified in-browser at 375×812 for **all three games**: felt top moved 183 → 79
      (104px reclaimed), panels relocate, tabs switch, dot raises and clears, sheet dismisses
      by backdrop / close / Escape / turn arriving. Desktop re-checked at 1280px: panels back
      in `.scoreboard` in the original order, collapse headers restored, sheet and button gone.

**Bug found in review, fixed** — History opened completely empty while Scores worked:
- `action_log.js` collapses the log by default below 720px, and it does that on
  **DOMContentLoaded** — after `table_sheet.js` (a parse-time IIFE) has already adopted the
  panels and cleared the class. So the class went straight back on, and
  `.action-log.is-collapsed #action-log-list { display: none }` blanked the tab. Scores was
  unaffected only because `chrome.js` deliberately never auto-collapses it.
- Fixed in two layers, so ordering can no longer matter: `table_sheet.css` now outranks the
  collapsed rules inside `.ts-body` (one extra class, so it wins on specificity rather than
  source order), and `showTab()` clears the class on every switch instead of once at adopt.
  Verified the tab still renders with the class forcibly re-added afterwards.
- Same hazard existed for Scores from the other direction — collapse it on desktop, then
  narrow the window, and the class travels into the sheet. Covered by the same fix.
- **Process lesson:** the original check counted `#action-log-list li` in the DOM, which
  proves existence, not visibility — the entries were there the whole time at zero height.
  UI verification has to assert computed display / measured height, not node counts.

**Two things worth knowing for next time**
- The FAB needed its own `max-width: 640px` size override: `.reaction-fab` shrinks to 46px
  there, and two differently-sized circles in one right-aligned dock read as a mistake.
- Breakpoint tracking listens to `resize`/`orientationchange` as well as the matchMedia
  `change` event. A missed `change` leaves the panels stranded in the sheet while the empty
  desktop column still offsets the felt — a loud, confusing break. reactions.js hedges the
  same way for dock positioning.
- While testing: the service worker (`super-cards-v4`) serves cached JS, so a plain reload
  can run stale code and make a fixed change look broken. Unregister the SW and clear
  `caches` when verifying frontend edits locally.

## 12. Desktop composition: centre the table, rebuild the footer — ✅ DONE (2026-08-20)

The desktop table read as scattered. Measured at 1847px, the cause was mostly one thing:
`.table-view` was already centred (`max-width: 1400px; margin: 0 auto`), but `.scoreboard`
is absolutely positioned at its left edge and `.felt` is pushed right to clear it — so the
*page block* was centred while the felt, which is what the eye reads as "the table", sat
**152px right of screen centre**.

- [x] **The felt is now exactly centred** (measured off-by-0 at 1847px) by reserving an
      empty right gutter the same width as the Scores column, making the felt symmetric
      inside its container. And it got **wider, not narrower** — 1048px → 1104px — because
      the cap rises with it (`--page-max-wide`).
- [x] Gated at `min-width: 1700px` deliberately: below that the gutter would have to come
      out of the felt's own width. Verified no change at 1440px or 1280px (felt still 1048 /
      913), and the phone sheet from §11 is untouched.
- [x] **One set of page rails.** New variables in base.css (`--page-max`, `--page-max-wide`,
      `--side-col`, `--side-gap`, `--page-pad`) replace the literals that were duplicated
      across `.table-view` / `.scoreboard` / `.felt`. The footer's *contents* now mirror
      `.table-view`'s box model exactly, so the footer brand starts on the same line as the
      Scores column and the CTAs end on the same line as the felt. Verified at 1847 / 1440 /
      1280. That single alignment did most of the work along the bottom edge.
- [x] **Footer kept but rebuilt for a live table** (`body.room-page`, set in game.html —
      matching the `home-page` class index.html already used). Flat instead of gradient, no
      gold glow, 67px → 50px, smaller type, marketing tagline hidden. The install CTA
      becomes an outline pill here: its own code comment calls it "the one CTA allowed to be
      filled/loud", which is right on the landing page, but on a room page a filled-gold pill
      was the loudest element on screen — louder than the felt's frame and the turn
      indicator, which is backwards mid-decision.
- [x] **The landing page footer is byte-for-byte unchanged** — verified: gradient, gold glow,
      visible tagline, filled-gold install CTA all still present on `/`.

**Two cascade traps this walked into, both worth remembering**
- `padding-right` written in table.css was silently dropped: **safe-area.css loads last and
  owns the final word on `.table-view`'s horizontal padding**. The reserved gutter therefore
  lives in safe-area.css, cross-referenced from table.css. That file's header warns about
  this in the other direction; it cuts both ways.
- The footer rail was off by 16px at any width where the max-width was not binding, because
  `reactions.css` styles `.site-footer.compact` and loads *after* table.css — equal
  specificity, later source order. Fixed by matching `.compact` explicitly rather than by
  reordering files.

**Deliberately not done** (raised, not chosen): capping the felt narrower to match its
content (the ask was explicitly "don't shrink it"), regrouping the six topbar controls, and
spreading seats around the felt perimeter — that last one only pays off at 5+ players and
would look emptier at 2–3, so it should be a player-count-dependent layout if ever built.

> **Testing note:** Flask serves static CSS with a long `max-age`, so a plain reload can
> measure *stale* CSS — separate from the service-worker cache noted in §11. Bust the
> stylesheet URLs (or hard-reload) before trusting a "my CSS didn't apply" result.

## 13. Colour: graphite chrome + per-theme bloom — ✅ DONE (2026-08-20)

The app ships **fourteen** table themes (Casino Felt → Horror → Space Galaxy) and the chrome
was fixed dark green, so exactly one of the fourteen harmonised with its own frame.

- [x] **Chrome is now neutral graphite** (`:root` in base.css): `--bg #141516`,
      `--panel #212426`, `--line #35393c`, `--text #e9eaea`. `--gold`, `--accent` and
      `--turn` are unchanged — gold is load-bearing, not decorative (§7 redrew the J/Q/K as
      gold emblems and every felt frames itself in gold). The felt is now the only saturated
      surface on screen.
- [x] **Hue comes back as a bloom**, not a gradient sweep. A literal graphite→green→blue
      sweep was rejected because panels and text sit *on* it, so contrast would become a
      function of position. Instead `#theme-bloom` is a fixed, masked, `z-index: -1`,
      `pointer-events: none` layer *behind* all content, tinted by `--bloom`.
- [x] **All 14 themes get a hand-picked bloom** (bottom of themes.css) — one value each.
      Hand-picked rather than derived: Hacker wants acid cyan over near-black and Horror
      wants desaturated blood, and neither falls out of "darken the felt hue".
- [x] Verified in-browser: all 14 blooms match their intended value, and across every theme
      there is exactly **one** panel-text colour and **one** body-text colour — so contrast
      is audited once, not fourteen times. Layer confirmed behind content and click-through.
- [x] `body.chrome-classic` in base.css restores the original green palette for a
      side-by-side or a straight revert. Kept as real code so it cannot rot.

**Three traps hit while building this — all worth remembering**
1. **`transition: background-color` on a `var()`-derived colour silently freezes it in
   Chrome.** The variable updates, the paint does not, and the bloom sticks on whichever
   theme loaded first. Transitioning the registered custom property instead
   (`transition: --bloom`) produced no animation either (`getAnimations()` empty). There is
   now deliberately **no** transition, with a comment saying so — at ~10% alpha an instant
   switch is imperceptible. If anyone re-adds one, verify the bloom still tracks a theme
   change before believing it works.
2. **Chrome resolves `var()` inside a pseudo-element against the ROOT, not the originating
   element.** The bloom started as `body.room-page::after` and could never see
   `body.theme-x { --bloom }` — and `getComputedStyle(el, '::after')` reports the same wrong
   value, so the bug is invisible to measurement too. It is a real `<div id="theme-bloom">`
   for exactly this reason: correct in every browser, and assertable.
3. **Jinja caches compiled templates when `FLASK_DEBUG=0`** (`use_reloader=False` in app.py).
   A template edit needs a **server restart** — the running server served the old HTML with
   no bloom div while the file on disk clearly had it. Together with the service-worker cache
   (§11) and Flask's static `max-age` (§12), that is three separate caches that can each make
   a working change look broken locally.

**Deliberate follow-up, not done here:** the straggler sweep. ~35 hardcoded hexes and ~41
`rgba()` literals across the chrome stylesheets, plus 10 in `super_four/table.html` and the
6-colour player `PALETTE` duplicated in `action_log.js` and `seven/table.js`, are still
green-tinted and will not follow a variable change. Kept as a separate pass on purpose so
that if something looks wrong, it is obvious which change caused it.

## 14. Player seat: liquid gauge, one ring, name plate — ✅ DONE (2026-08-20)

The seat was encoding two unrelated meanings in the same visual channel: an inner
elimination ring (56px) and an outer turn-timer ring (62px), **3px apart**, both running
through the same `ringColor()` green→red ramp. A red outer arc ("act now") and a red inner
arc ("nearly eliminated") looked nearly identical — worst on phones at 50px / 44px.

- [x] **Elimination moved inside the avatar as a liquid gauge that drains.** Full and calm
      means healthy; near-empty means nearly out — a battery discharging rather than a tank
      filling with poison. New `GAUGE_STOPS` ramp starts on a calm blue at a clean score and
      then joins `RING_STOPS` exactly, so the gauge and the Scores panel bar stay one system
      at the dangerous end while the healthy state reads calm.
      Verified across the range: 0→100% blue, 20→80% green, 40→60% yellow, 60→40% orange,
      95→5% red, 100→0% red.
- [x] **The ring now means one thing only**: whose turn, and how long left. It already only
      existed on the active player's turn, so ring present = their turn is now unambiguous.
- [x] **Identity moved to the avatar rim** — a player-coloured fill would collide with the
      level's colour. Gauge avatars grew 46px → 52px (40px on phones) using the radius the
      deleted arc freed up.
- [x] **Waves only on your own seat.** Super Seven seats up to 20 players; animating every
      gauge would mean up to 40 perpetually rotating composited layers on a page that already
      holds a wake lock (§9). Verified: `av-wave` on the own seat, `none` on opponents. The
      animation that actually matters is the level *settling* when scores land at round end —
      a 700ms height transition, essentially free.
- [x] **One name plate instead of two floating text lines.** The translucent backing is
      load-bearing, not decoration: `--muted` on Casino Felt's upper gradient measures about
      **1.8:1**, and Red Casino and Sunset are no better, so legibility depended on which of
      the fourteen themes the host picked. One plate fixes all fourteen.
- [x] **Score no longer disappears on your turn.** `buildSeatEl` used to put score and timer
      in the *same* slot, so the number you were deciding against vanished exactly while you
      decided. Your own seat renders under the hand rather than into the arc, so it is not
      width-constrained and gets one wider row: `xenone · you · 0 pts · 38s`. Opponent seats
      are 74px (60px on phones) and keep the either/or — and only one seat is ever on the
      clock.
- [x] **Timer bug fixed.** `.opp-score.timer` was statically `var(--turn)` green while the
      ring reddened via `ringColor(1 - pct)` — at three seconds the ring was red and the
      number beneath it was calm green. The number now inherits the ring's current colour,
      and goes weight 800 under 5s. "left" dropped: redundant beside a depleting ring.
- [x] Verified at 1847px and 375px, on Super Seven and Bluff: 12-seat crowded arc has **no
      plate wider than its seat and zero adjacent overlaps**; safe players read full with a
      `0` badge; offline 0.5 / eliminated 0.4 dimming intact; no horizontal overflow.

### 14b. Seat refinements after first look — ✅ DONE (2026-08-20)

- [x] **Timer ring is now a 2px hairline** (was 5px on opponents and **8px** on your own
      seat). The cause was `.opp-ring`: a sized flex wrapper between the 62px outer and the
      avatar, so the arc showed from 62px all the way in. It is now a bare wrapper and the
      avatar sizes directly against the outer — 58px inside 62px on opponents, 62px inside
      66px on your own seat, 46/50 on phones. The reclaimed radius went to the face.
- [x] Root cause of a stubborn 44px avatar on phones: a leftover `.opp-ring { width: 44px }`
      in the mobile block. Being a flex container, it *shrank* the 46px avatar to fit.
      `.opp-avatar` now carries `flex: 0 0 auto` so no ancestor can squeeze the face again.
- [x] **Name plate is one horizontal row for every seat** — name left (flexing, ellipsised),
      score right. Stacked, the plate grew nearly as tall as the avatar and competed with it.
      Font dropped to 500 weight / 0.7rem: a label, not a heading.
- [x] **Plate width comes from the arc's real spacing.** `renderOpponentSeats` already had
      the geometry, so it sets `--plate-max` per render. This matters more than it sounds: a
      292px felt with 4 opponents leaves only **55px of pitch between seats that are 60px
      wide**, so any fixed comfortable width guarantees collisions. Verified 0 overlaps at
      2, 4 and 8 opponents on a 375px phone.
- [x] When the plate falls under 74px there is no room for name *and* score, so `.tight`
      drops the score and keeps the name — scores are in the Scores panel / sheet anyway.
      The live countdown is exempt: it outranks the name while a clock is running.
- [x] **Waves now on every gauge**, not just your own — an opponent's level looked like a
      flat block of colour. Cost is controlled by layer count instead: opponents get one
      rotating layer, your own seat two, and `.dense` (>10 seats) drops the animation
      entirely, so the worst case is ~10 layers rather than 40.
- [x] **Card count is a little card**, not a pill — card proportions, 3px corners, cream
      face, 7° tilt. Moved off gold, which is the chrome accent now; this is game state.

**Two CSS-comment mistakes I made, both worth the warning**
1. Appending prose to an existing comment block left orphaned text after the closing `*/`,
   which made the parser **discard the entire following rule**. It happened twice: once to
   `.seat-plate` (silently no background, no padding, no max-width) and once in base.css to
   `@property --bloom`. There is now a check for this — comment-delimiter balance plus
   orphaned prose — worth re-running after any CSS comment edit.
2. **That second one invalidated an earlier conclusion.** §13 recorded that
   `transition: --bloom` "created no animation either" — but `@property` had never parsed, so
   that test was meaningless. Re-tested with it genuinely registered: the transition
   *freezes the value* exactly like `transition: background-color` does. So the no-transition
   decision stands, now for a measured reason rather than a broken-stylesheet artifact.

**Three staleness traps, now all hit at least once:** service worker (§11), Flask static
`max-age` (§12), Jinja template cache (§13) — and this round added a fourth reminder that
**busting stylesheet URLs does not reload JS**; an edited `seats.js` needs a real page
reload. Also: checking `querySelector(...)` for presence is not checking visibility — the
same mistake as §11's empty History tab, made again here on the tight-mode score.

### 14c. Names actually fit now — ✅ DONE (2026-08-21)

Opponent names were still being cut ("Suryav…") because `SS.shortName` had a hard **12-char
cap** — "Suryavanshi C" is 13, so the cap clipped it to "Suryavanshi…" and threw away the
last initial, which is the half that distinguishes two players sharing a first name.

- [x] `shortName` cap 12 → **16**, and the last initial is now **protected**: letters come
      off the first name and the initial stays. "Chandrikaprasad Rao" → "Chandrikapra.. R".
- [x] **Two dots, not an ellipsis character.** At 11px a "…" reads as a smudge and costs the
      same width as two periods that look like periods.
- [x] Space bought back and spent on letters: opponent plates show the bare score (`68`, not
      `68 pts` — that label alone was ~22px, about four more letters of someone's name),
      padding 0.5→0.4rem, gap 0.35→0.28rem, name 0.7→0.68rem with -0.01em tracking. Your own
      seat keeps `pts`; it has the room.
- [x] **No more mid-word CSS chopping at any width.** When the arc is genuinely cramped the
      seat re-shortens *on purpose* via a character budget derived from the plate width:
      ≥9 chars keeps the "First.. L" shape, below that it spends the whole budget on real
      letters of the first name, because "Surya" beats "Su.. C" when only six glyphs fit.
- [x] Verified: desktop shows the full "Suryavanshi C" at 1, 3 and 6 opponents with no
      clipping; a 375px phone shows it in full at 2 and 3 opponents, "Suryavan" at 4 and
      "Suryav" at 6 — always whole words, zero plate overlaps, no horizontal overflow.

**Known pre-existing limit, not introduced here:** at 8+ opponents on a 375px phone the arc
gives each seat ~27px of pitch while the avatar alone is 46px, so the *seats themselves*
overlap regardless of the plate. That is the arc's own geometry; fixing it would mean
wrapping opponents onto a second row on narrow screens.

**Scope notes**
- Bluff passes `ringPct: null` and correctly gets **no gauge** — a permanently-full gauge
  would imply a health metric it does not have. It keeps the player-colour filled avatar, so
  the presence of a gauge is itself the signal that a game has an elimination score.
- **Super 4 is untouched**: it builds its own `.s4-seat` markup and never calls
  `SS.renderMySeat` / `renderOpponentSeats`. Giving it the same treatment is a separate job.
- Purely a rendering change — `ringPct` was already computed and passed. No server work, no
  protocol change, suite unaffected.

## 15. Card deck redesign — ✅ DONE (2026-08-21)

Rewrote `tools/generate_cards.py`. Decisions were made by **rendering the candidates and
looking at them** (cairosvg + Pillow, `--sheet`), not from taste.

**The finding that reframed the job.** The old deck drew suits as Unicode text —
`<text font-family="Georgia">♠</text>` — so the shapes came from the *viewer's* operating
system. Rendered outside a machine with those fonts, every suit is a **tofu box**; several
mobile browsers substitute the **colour emoji** face instead. The deck looked correct only
because the dev machine had the fonts. Suits are now geometry; ranks stay as `<text>` because
they are ASCII and every fallback font has them.

**Why v2 looked wrong, specifically:**
- Its **club had no top lobe** — the path traced upper-left, lower-left, lower-right,
  upper-right with a dip at top centre, so it read as a butterfly. Clubs are now three
  literal `<circle>` elements, so the lobe topology *cannot* be wrong.
- Its **spade and club stems were self-intersecting** (`M-5 12 L5 12 L2 25 L8 25 L8 29 …`),
  which under `nonzero` fill produced that anvil-pedestal with a notch bitten out.
- **Pips were cramped**: a 16.5-unit pip on a 24.6px row pitch, and 22.4px between columns
  for 18px-wide pips. Everything touched.
- Non-standard arrangements (a lopsided 7, a flat 2×5 ten) and five competing decorative
  systems per card (banner, wavy band, sparkles, oval watermark, double border).

**The constraint that drove the design:** the source is 180×252 but the largest a card is
**ever** drawn is **62px** (centre pile) — hand cards are 58/46, the round-end reveal is 38.
So detail finer than a third scale is imperceptible; v2 carried decoration at
`stroke-width="0.6" opacity="0.06"`, invisible by construction. And
`FAN_MIN_OVERLAP_RATIO = 0.25` means a fanned hand shows little more than corners, so the
**corner index does nearly all the work** and got the space.

- [x] Correct suit geometry, verified at 46px and 58px on green / red / near-black felt.
- [x] Opaque cream face — a **jelly/glass** candidate was built and rejected on evidence: on
      green felt the card body read green, on red felt pink, so card identity changed with
      the theme, and the rank index washed out at 46px. Rank and suit are the one thing that
      must never be ambiguous. The glossy treatment went to the **card back** instead, which
      carries no rank and is the most-seen card in the game.
- [x] "Modern royal" reached by **subtraction**: one gold outer frame (the ornament that
      survives 46px) and nothing inside it. Aces and courts get the gold edge, number cards a
      quiet warm one, so rank hierarchy reads before you read anything.
- [x] Court cards are gold **geometric emblems** (crown / coronet / shield), chosen because
      v2's figurative court art was the single weakest thing in the deck and no drawn face
      survives 46px. Distinct silhouettes so J/Q/K differ by shape alone.
- [x] Standard English pip layouts, one `PIP` constant and one band so spacing cannot drift.
- [x] `--out` flag so the generator can target a temp directory — the live deck was never
      overwritten until the result had been inspected. `--sheet` renders a contact sheet.
- [x] `tests/test_card_assets.py` — 9 checks: completeness derived from `game.core.cards`
      (not a hardcoded list), well-formed XML, correct viewBox, **no Unicode suit glyphs**,
      no external references, real geometry present, club built from circles, all text ASCII.
      Verified by restoring one pre-change card from git: it fails exactly the glyph checks.

### 15b. Deck v2 — the colourful deluxe deck — ✅ DONE (2026-08-21)

v2 is now a genuine second deck rather than a worse first one.

- [x] **It no longer overwrites the live deck.** The old v2 wrote into
      `static/img/cards`, the directory the whole app loads, so running it silently replaced
      the shipped deck. It now defaults to **`static/img/cards_v2/`** and takes `--out`.
      Nothing in the app points there yet: swapping decks is a deliberate copy, or a future
      setting.
- [x] **Shared suit geometry** — new `tools/card_art.py` holds one definition of each suit,
      imported by both generators, so the club-with-no-top-lobe and self-intersecting-stem
      bugs cannot reappear in either. Refactor verified the strong way: v1 was regenerated
      after the extraction and **0 of 53 files differed**.
- [x] **Four-colour suits** — spades ink, hearts red, diamonds blue, clubs green, with
      matching coloured borders and a faint suit tint on the face. Colourful *and* functional:
      suit becomes readable from colour alone, which matters when a fanned hand shows little
      more than corners. The clean deck stays two-colour for players who want tradition.
- [x] **Figurative court cards, single figure on a plinth.** A physical deck is double-ended
      so it reads the same whichever way you hold it; on a screen a card is never upside down,
      so that convention costs half the artwork area and buys nothing. Spending the whole card
      on one figure roughly **doubles the head size** (44px vs 32px in the source), which is
      what makes the three courts actually distinguishable. A small gold plinth with a suit
      medallion gives the portrait a base instead of floating mid-card.
- [x] **King, Queen and Jack differ on three axes**, not just headgear — the first attempt at
      a double-ended version made all three read nearly identically:
      - **King** — tall spiked crown with jewels, **beard**, epaulettes, gold centre placket.
      - **Queen** — low arched coronet with a pearl finial, **long hair falling past the
        shoulders**, pendant on a chain, softer shoulder line.
      - **Jack** — plumed cap (no jewelled band; he is not royalty), shoulder-length hair,
        diagonal sash.
      Hair colour differs too, so they stay separable when the crown is only a few pixels.

**Bug caught by rendering it:** the first attempt merged both busts into a dark blob. The
headgear was drawn at y −27…+2 while the head sat at cy −8 r 16, so **the crown covered the
face**, and the robes were wide enough to meet across the divider. Fixed by moving the
headgear above the crown of the head and narrowing the robe — the sort of thing only visible
by looking, which is why `--sheet` exists.

- [x] `tests/test_card_assets.py` now audits **both** decks with identical rules (18 checks),
      naming the deck in every message. `cards_v2` is optional-if-absent, but if it has been
      generated it gets no leniency — an alternative deck is no excuse for a font-dependent
      or broken one.

**Not done, deliberately:** licensed open-source court art (Byron Knoll's public-domain deck,
David Bellot's LGPL `svg-cards`). It remains a clean drop-in for the face panel, but at a
62px ceiling a beautifully drawn king is ~30px of face, so it buys little for a third-party
asset plus a licence obligation — and v2 now has its own figurative courts anyway.

## 16. Per-player deck choice — Royal / Standard — ✅ DONE (2026-08-21)

Both decks are now selectable from the topbar, per player.

- [x] `static/js/core/deck.js` + `templates/partials/deck_selector.html`, modelled on the
      hand-view control and reusing the theme selector's dropdown markup/CSS rather than
      inventing new chrome for the same "pick one of a few" shape.
- [x] **Per-device, not host-controlled and not synced.** Two players at the same table can
      each see the deck they prefer. Nothing about card *identity* changes — only which set of
      SVGs is fetched — so a deck swap can never desync anything or affect gameplay. (Contrast
      with the table theme, which is deliberately shared and host-picked.)
- [x] **Royal (`cards_v2`) is the default**; Standard (`cards`) is the traditional two-colour
      deck. Shown for all three games, unlike the hand-view control which hides for Super 4.
- [x] **One place knows where card art lives.** `SS.cardSrc(face)` replaced 9 hardcoded
      `/static/img/cards/` sites across `seven/table.js`, `seven/game.js`, `bluff/table.js`,
      `bluff/game.js` and `four/game.js`. A grep for `img/cards` in `static/js/` now returns
      only deck.js itself.
- [x] **Switching is instant.** `repaint()` rewrites the directory segment of any card image
      already in the DOM, which also picks up the two deck backs the table templates render
      server-side — so those needed no template change and any future card site is covered
      automatically.
- [x] `tests/test_card_assets.py` now treats **cards_v2 as required**, not optional: it is the
      default deck, so a missing one means broken images for everyone who has not opted out.
      `static/img/cards_v2/` must therefore be committed — it is no longer just build output.
- [x] Verified in-browser on all three games: default is Royal, switching rewrites every card
      (Super Seven 8 images, Bluff 26, Super 4 9) with **0 broken**, the choice survives a
      reload, and a *fresh* render after reload uses the stored deck — which is what proves
      the render path goes through the helper rather than only the repaint.
- [x] Service worker checked: `PRECACHE_URLS` does not list card paths, so neither deck is
      stale-cached by the SW.

### 16b. Royal really is the default, on phone and desktop — ✅ VERIFIED (2026-08-21)

Checked with `localStorage` cleared (a genuine first-time player) at **1440px and 375px**:
resolved default `royal`, label "Royal deck", every card served from `cards_v2`, and on mobile
the selector sits inside the collapsed hamburger where it is visible and hittable once opened.

**One flaw the check surfaced and fixed.** Both table templates hardcoded
`img/cards/back.svg` — the *Standard* back. So every default-deck player fetched the wrong
card back and had `deck.js` rewrite it: one wasted request and a possible flash of the wrong
art on a slow connection. Confirmed by `performance.getEntriesByType('resource')`, which
listed a `/img/cards/back.svg` fetch. The templates now render the default deck, and a
Standard-preferring player still gets corrected on load as before — the wasted fetch moved
from the majority to the minority.

- [x] `tests/test_card_assets.py` now pins this down: `core/deck.js` must declare `DEFAULT`,
      it must be `royal`, Royal must map to `cards_v2`, and **every** table template must
      render the default deck's back. Verified by reverting one template — it fails naming
      the offending game and the expected directory.

> Suite note: one socket test failed once during this work and passed on the next three runs,
> with nothing in its output but the harmless "websocket-client package not installed" notice.
> Treating it as a flake for now; worth watching rather than assuming it is gone.
>
> **Diagnosed in §20b (2026-08-28) — it was not a flake.** `run_tests.py` piped the test
> server's stdout and never read it, so once the log passed the ~64KB pipe buffer the OS
> blocked the server mid-run. Whichever socket test ran last then stopped receiving events.
> "Watch it rather than assume" was the right call; "treat it as timing" was not.

## 17. Mobile: state not updating without a full reload — ✅ FIXED (2026-08-21)

Reported from real phones (never reproducible in a desktop mobile-emulation view):
changing the card deck or the hand view did not apply until the page was reloaded, and after
switching apps and coming back a player could show as absent and be unable to act.

**Three separate bugs, one shared symptom.**

**1. `resume()` did nothing in exactly the case it was written for.** `core/connection.js`
guarded on `if (!socket.connected)` — but its own docstring describes the failure precisely:
a phone back from the pocket "comes back holding a socket the client still believes is open."
`socket.connected` reads **true** while the transport is already dead, so the guard was false
and nothing reconnected. Socket.IO cannot detect this locally.
- Fixed with an **application-level liveness probe**: a new ack-only `client_ping` handler in
  `sockets/connection.py`, and on becoming visible the client emits it and waits. No ack
  inside 2.5s ⇒ zombie ⇒ tear the socket down and rebuild. An ack ⇒ the socket is genuinely
  live, and it still resyncs, because a background gap can miss broadcasts.

**2. Resync was wired only to the `connect` event.** No reconnect meant no `enter_room`, and
`enter_room` is what re-attaches the sid server-side — which is what actually clears "player
is absent". Added `SS.onResync()`; all three game bundles register their `enter()`, and
returning to the foreground runs it whether or not a reconnect happened.

**3. The hand-view change was gated on `state === "IN_TURN"`.** `core/view_mode.js` only
re-rendered mid-turn, so a change made at round end, at game end, or in the lobby applied
**only after a page reload** — exactly the report. Now it calls the shared `SS.repaintUI()`
unconditionally. Deck switching does the same, so the JS-measured hand-fan geometry is rebuilt
rather than left stale after a src swap.

`SS.repaintUI()` also runs on foreground resume: a page frozen in the background can come back
with stale geometry, because the viewport may have resized (URL bar collapse) while the JS was
suspended and the fan layout is measured in JavaScript.

**Verified** — the probe paths, driven directly since the harness page is `visibilityState:
"hidden"` and would otherwise short-circuit `resume()` (an environment artifact, not a code
fault):
- healthy socket ⇒ probe acks ⇒ resync fires `enter_room` ⇒ `room_joined` observed, **sid
  unchanged** (no needless reconnect);
- zombie socket (probe emit swallowed so no ack) ⇒ rebuild ⇒ **sid changes** ⇒ `room_joined`
  ⇒ `/healthz players_connected` back to full;
- view mode and deck both apply instantly while `state === "GAME_END"` — the exact case the
  old `IN_TURN` guard blocked.

> **Not verifiable here, and worth checking on a real device:** a genuinely zombied socket
> cannot be reproduced in a desktop browser, because closing the transport there fires a clean
> `disconnect` and Socket.IO's own auto-reconnect handles it (confirmed: `engine.close()`
> recovered by itself in 1.2s). The probe is the mechanism for the case desktop never
> produces, so the real-phone background/foreground cycle is the test that matters.

**Deliberately not added:** a periodic background liveness poll. Socket.IO's own heartbeat
covers an active page, and polling on a timer would spend battery on a table that is idle
anyway. If zombie sockets still appear on a phone left open and untouched, that is the next
thing to try.

> **Superseded by §18 (2026-08-28).** They did, and it was. The premise above was wrong on
> its first clause: Socket.IO's heartbeat covers an active page only while the page's own
> timers run, and the case that matters is precisely the one where they did not. The
> "next thing to try" is now built — a 10s `client_sync` while visible, which is also how a
> client learns it has missed a broadcast.


## 18. State desync on real devices — five causes, one heartbeat — ✅ FIXED (2026-08-28)

Reported from actual phones and the installed app, occasionally desktop: mid-game a
player "just goes offline", their own screen stops updating, and **only a full page
refresh brings it back**. Never reproducible in a desktop mobile-emulation view — which
is the clue, because every cause below needs something only a real device does: freeze a
page's timers, drop a transport with no close frame, or take every player offline at once.

§17 fixed the same *symptom* and did not hold, so this started by reproducing rather than
re-reading. Five separate defects, all confirmed against a live server before any change:

**A. Super 4's reconnect path sent the wrong events — or none.** `sockets/lobby.py`
wrote its reconnect branch in Super Seven's vocabulary (`round_start` / `round_end` /
`game_end`) for *every* game, and gated round-end on `_last_result`, which only Super
Seven sets. Measured: `super_four state=ROUND_END reconnect-> NOTHING SENT`; at
`GAME_END` it sent `game_end`, which `four/game.js` does not listen for (it listens for
`s4_round_end`). **This is why refreshing did not help — the reload took the same dead
branch.** Fixed with `presenter.register_resync`: each game now answers the shared
reconnect in its own vocabulary, and the shared layer knows no game's event names.

**B. The empty-room reaper deleted live games.** `_reap_stale` compared `EMPTY_ROOM_TTL`
against `room.created_at` — the room's *age*, not how long it had been empty. So any room
older than 60s was eligible the instant its players were all momentarily disconnected,
with **zero grace**. On phones that is routine, not an edge case. Reproduced: a
ten-minute game, both players briefly offline, one unrelated `create_room` → gone. The
grace period now runs from when a room was first *seen* empty and resets the moment
anyone returns; a room nobody ever joined still counts as empty from creation, so the
abandoned-create case the reaper was written for is unchanged.

**C. `SS.repaintUI()` was a no-op in Super 4.** It called `window.Table.render(SS.view)`
— a shape only Super Seven and Bluff define. Super 4 renders its own table, so §17's
foreground repaint and the deck / hand-view repaint silently did nothing there. Replaced
with an `SS.onRepaint` registry each bundle fills in, so no shared code guesses at a
game's render entry point. Verified: repaint produces 15 DOM mutations in Super 4 where
it produced 0, and deck switching now applies instantly (0 broken images).

**D. Recovery depended entirely on `visibilitychange`.** That covers exactly one entry
point — the phone coming out of a pocket. A socket that died while the player was
*looking at the screen* (Wi-Fi/cellular handoff, a lift, a dropped poll) was never
re-checked at all, and there was no periodic poll: §17 recorded deliberately not adding
one. This report is that deferral coming due.

**E. The probe tore down healthy sockets.** Its 2.5s timeout was never cancelled, so
after the socket recovered on its own the stale timer still saw "no ack" and rebuilt the
connection — which the server reads as a real disconnect, so **the player flashed offline
to the whole table**. A self-inflicted copy of the reported symptom. The timer is now
cancelled on ack, on `connect`, and on `disconnect`.

**The mechanism** — `sockets/sync.py` + a rewritten `core/connection.js`:
- [x] While the page is visible the client sends `client_sync` every 10s carrying the last
      state version it has seen. The ack *arriving* proves the socket is alive end to end
      — silence means a zombie, so rebuild. `stale` means the server does not have this
      socket on file. `v` disagreeing means a broadcast was missed.
- [x] **The cure is always `enter_room`**, which already re-attaches and replays full
      state. The handler only diagnoses: repairing from there too would mean a second
      restoration path to keep in step with the first.
- [x] **Every room-wide broadcast is numbered**, in `sockets/audience.py` — the one point
      every emit already passes through, so a broadcast cannot be added without being
      numbered. Private payloads are not numbered (an answer to one socket is not a
      snapshot anyone can fall behind on) and do not burn a version. Numbering *every*
      room-wide emit, toasts included, is deliberate: an allow-list of "real" state events
      is exactly the kind of thing that drifts.
- [x] `tests/test_platform_contract.py` now requires a resync hook per game, so game #4
      cannot repeat defect A. `tests/test_state_sync.py` pins all of it — 23 checks.

**Verified in-browser on all three games**, not just reasoned about: healthy client stays
`stale:false` and never re-enters needlessly; a deliberately orphaned socket is reported
`stale:true` and **self-heals in one beat with no reload** (Super 4 and Bluff both
confirmed); one player's action advances both players' versions together (6 → 10);
repaint reaches every bundle (13/15/17 mutations for Seven/Four/Bluff); no console errors,
no new server exceptions. Suite: **32 files, 30 pass, 2 unscored**.

**Deploy note.** `sw.js` cache bumped `super-cards-v4` → `v5`. Static assets are
stale-while-revalidate, so without a bump a returning player runs the *previous* build's
JavaScript for a whole page load — and an old client against a new server is
indistinguishable, from the player's seat, from the bug this fixes. `client_ping` is kept
as a compatibility ack for exactly that one load, and can be deleted once no deployed
client emits it.

**Two things this cost me, worth remembering**
1. **Instrumenting the client broke the server.** Wrapping `socket.emit` as
   `(ev, data, cb) => orig(ev, data, cb)` appends an `undefined` third argument, which
   socket.io sends as a *second data argument* — `on_start() takes 1 positional argument
   but 2 were given`. Forward with rest args, or you debug your own probe.
2. **The §11 lesson, re-learned.** "Repaint did nothing" was measured by blanking the felt
   and watching for a rebuild — but that deleted the very containers `renderTable()`
   writes into, so it could not have rebuilt. A MutationObserver on an untouched DOM gave
   the real answer. Checking for presence still is not checking behaviour.


## 19. Results screen everywhere, and Bluff plays for places — ✅ DONE (2026-08-28)

Super Seven had a medal stand with a podium, tiered trophies and fireworks; the other two
games did not. Worse, Bluff **hung** at game over with no way forward, and it ended the
moment the first player shed their hand — so there was never anything to put on a podium
in the first place.

**Why Bluff hung, exactly.** `bluff/game.js` already called
`showGameOver(data.winner, data.standings)` — but `Room.game_end_payload()` never had a
`standings` key. `rows.find(...)` threw on `undefined`, the modal never opened, and the
game simply sat there with no Play again and no way home. One missing key, and the only
symptom was a dead screen. `showWinnerScreen` now treats a non-array `rows` as empty
rather than throwing, so a payload bug can never again present as a hung game.

**Bluff now plays for places, not a single winner.**
- [x] Shedding your last card banks a **place** instead of ending the game; everyone still
      holding cards plays on. `finish_order` on the room is the ranking.
- [x] A finish is only confirmed once the challenge window has closed — i.e. once an action
      has happened after yours, so you are no longer `last_play`. Get caught bluffing on
      your last cards and you pick the pile back up, exactly as the rules always said.
      A resolved Show confirms it immediately: nothing else can give those cards back.
- [x] The game ends at whichever comes first: **`PODIUM_PLACES` (3) players finished**, or
      **at most one player still holding cards**. That second rule is what ends a 2- or
      3-player table naturally, so the podium rule never has to special-case small games —
      heads-up is 1st and 2nd, three players fill all three places.
- [x] **Unfinished players rank by how many cards they hold, fewest first — the count, not
      the values.** In Bluff a card is a card; a player one turn from out is doing better
      than one nursing a dozen, however those dozen add up. Ties keep turn order so the
      list is stable between renders.
- [x] Finished players are skipped by the turn rotation, and the "everyone passed" sweep
      counts only players who can still act — including finished players there would mean
      the pile could never be swept.
- [x] Every exit path now routes through one `_maybe_end_game()`: a normal finish, a quit,
      and a timeout removal. Previously each had its own copy of the end condition and its
      own idea of who won.
- [x] Bug found while wiring it: the human `bluff_show` handler never checked for game end
      after `resolve_show`. Once a challenge could settle the game — which it now can — the
      room would have sat in STATE_GAME_END while clients were only told the table changed.
      Every other action path already checked; that one had never needed to.

**The winner screen is now genuinely shared.** Its own docstring claimed "used by every
variant" while only Super Seven called it.
- [x] Two optional parameters, so Super Seven's call is unchanged: `subtitle`, and
      `scoreText(row)` for what sits under each name. The hardcoded "last one standing" copy
      and "N pts" were Super Seven's elimination framing, wrong for a game that ends any
      other way.
- [x] **Bluff** shows `1st` / `2nd` / `3rd` for finished players and `N cards left` for the
      rest — the podium says what the game actually counted, instead of points it never had.
- [x] **Super 4** gets the podium at game over instead of a fifth round-end table, and with
      it a real Play again. Its round-end reveal stays for ordinary rounds, where explaining
      the scoring is the point. New `Room.standings()` mirrors Super Seven's, because both
      rank on a cumulative score where lower wins.
- [x] The Bluff scoreboard shows place-or-cards-left per player, so the live panel and the
      final podium rank on the same thing. Written as words, not a Unicode card glyph — §15
      established those resolve to whatever font the viewer happens to have.

**Verified in-browser and over sockets, not just reasoned about:** real 2-player and
4-player Bluff games driven to the finish (heads-up gave 1st/2nd; four players ran on past
two finishers and ended at three, with the last ranked below); the modal genuinely open
(`display: flex`, every place measuring non-zero height) with the risers stepping
140/110/90/74/60 by rank; confetti and bursts present; Play again returning all the way to
a clean lobby with places cleared. Super 4's podium confirmed on a real solo game, ordered
by lowest total. Super Seven re-checked on the shared defaults. Suite: **32 files, 30 pass,
2 unscored.**

**A test that had encoded the old rule.** `test_bluff_logic.py` asserted "first empty hand
ends the game" in two places. Those are now four tests describing the new rule — including
one pinning that ranking is on card *count* by giving one player a single 2 and another a
pair of Kings.

**Notes for next time**
- `PODIUM_PLACES` is a rule constant, not a host-selectable setting, so
  `tests/test_settings_docs.py` could not reach it — its claim table only reads
  `default_settings`. It now has a second table for module-level constants, and the 3 is
  pinned in `en.html`, `hi.html` and `docs/bluff_rules.md`.
- **The suite flake from §16b showed itself again, and now has an explanation:** the failing
  file is timing-sensitive over sockets, and it failed on the one run where a dev server was
  competing for the machine. Four consecutive runs before and after were green, and the file
  passed 6/6 four times in isolation. It was not touched by this work. If it recurs, the fix
  is in the test's waits, not the product.
- `bluff/game.js` still carries a `round_end` handler that can never fire — Bluff has
  `has_rounds=False` and no `round_end_payload`, so the event is unreachable. Harmless, but
  it now also implies a scoring model Bluff does not have. Worth deleting on the next pass
  through that file.


## 20. Computer players at a real table — ✅ DONE (2026-08-28)

A bot used to exist only in single-player mode: `create_solo` seated exactly one,
hardcoded as `bot_suryavanshi`. A host can now seat up to **five** from the lobby in any
room, which is what makes a three-friend table worth playing.

**The feature**
- [x] New shared `game/core/bots.py` — the roster (Suryavanshi, Rajveer, Meera, Anika:
      two male, two female), the cap, and identity allocation. It imports no game, and no
      game imports it; adding a variant does not touch it.
- [x] `add_bot` in `sockets/lobby.py`: host only, lobby only, bounded by both
      `bots.MAX_BOTS` **and** the game's own `MAX_PLAYERS` (so Bluff stops at 1 human + 5
      bots on its 6-seat table). Every refusal says which limit it hit.
- [x] **`create_solo` was rebuilt on the same helper**, so there is exactly one way a
      computer player enters a room rather than two that can drift.
- [x] **The cap is five and the roster is four**, so a profile has to be reusable. The
      repeat is numbered — `Meera` then `Meera 2` (`bot_meera_2`) — and the suffix search
      walks past *every* existing player, so a bot can never take the name or id of a
      human who happens to be called Meera. `bot_suryavanshi` keeps its original id, so an
      existing room snapshot still resolves.
- [x] Shared `core/lobby.js` gets the button and picker, so all three games have it from
      one implementation. It reuses the theme dropdown's shape rather than inventing a
      second popover for the same "pick one of a few" job, and opens *upward* because the
      row sits at the bottom of the lobby card.
- [x] **A bot can be removed again** — `kick_player` no longer refuses them, and the
      roster shows the control. No confirm dialog for a bot: seating one is a click, so
      un-seating one should be too.

**Two things that were only accidentally correct before, and are not any more**
- [x] **Bot scheduling was keyed by room** (`_bot_act_at[code]`). With one bot per room
      that was equivalent to keying by bot; with five it lets one bot inherit another's
      deadline, so the second bot in a rotation acts on the leftover schedule of the first
      instead of taking its own thinking time. Now keyed `(code, bot_id)` in all three
      games.
- [x] **Bots played on to an empty room.** With humans gone the room is already reapable,
      so every move until then is work nobody will ever see — taken from rooms that do
      have players, on a one-worker host. New shared `director.bots_should_act(room)`,
      called from each ticker's bot branch. It gates the *bot* branch only: pausing the
      human turn timer as well would leave `turn_start_ts` stale and time somebody out the
      moment they reconnected.
- [x] Stale claims corrected where the code no longer matched: `is_bot` was documented as
      "single-player mode only; never True in group games", `super_seven/ai.py` was headed
      "SINGLE-PLAYER MODE ONLY", and its Stop-calling notes described "the opponent"
      singular and a safe-player rule the code does not implement. The *code* was already
      right for a table of twenty — it loops every opponent and skips safe ones because
      they are out of the Stop race — so the docstring was the thing that was wrong.

**Verified:** 37 engine checks (`tests/test_bots.py`) and 17 socket checks
(`tests/test_bots_socket.py`) covering who may seat a bot and when, both caps, distinct
names, removal, and two humans + two bots actually playing in Super Seven and Bluff. In a
browser: the picker, the disabled-with-a-reason state at the cap, removal, and a real
1-human/4-bot Super Seven game where all four bots took a full orbit and play came back
round — plus Bluff with two bots.

### 20b. The suite's long-standing "flake" was a wedged server — ✅ FIXED (2026-08-28)

Adding a socket test made `test_s7_phase4_socket.py` fail *every* run. It had been
intermittent for weeks (§16b) and was written off as timing. It was not.

**`run_tests.py` gave the test server `stdout=PIPE` and never read it.** A pipe nobody
drains fills at ~64KB, and then the OS blocks the writer — so the *game server* froze
mid-run, holding every client. The only symptom is that whichever socket test happens to
run last stops receiving events, which reads exactly like a flaky test.

Measured: a full socket sequence writes **72.7KB** of request log. Before this feature it
was just under the buffer; 20s of extra traffic pushed it over, which is why a new test
elsewhere "broke" an unrelated one.

- [x] The runner now drains the server's output on a daemon thread into a bounded deque,
      so the server can never block and the tail is still available if boot fails.
- [x] Two remaining races in `test_s7_phase4_socket.py` fixed by waiting for the condition
      instead of sleeping a guessed interval — including one where `start_game` was emitted
      without waiting for all three players to attach, so the deal could miss whoever was
      still in flight. The assertions were always right; the waits were not.
- [x] **Five consecutive green suite runs**, where before the fix it failed roughly one run
      in three. Suite: **34 files, 32 pass, 2 unscored.**

**The lesson worth keeping:** a test that fails "sometimes, and more often when unrelated
work is added" is not automatically a flaky test. Here the added work was only a *dose* —
the failure was a fixed byte budget in the harness, and it would have gone on being blamed
on timing indefinitely.


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

Each one now names what enforces it — see §10. A guardrail nobody can violate beats a
guardrail everybody remembers.

- **Single worker only** — in-memory room state; `python3 app.py` (eventlet), never
  multi-worker, never gunicorn (it breaks `start_background_task`). *Enforced:* `app.py`
  refuses to boot into an occupied port; `/healthz` `boot_id` detects a split brain.
- **Hidden information is server-authoritative** — never send a card face for a position the
  recipient hasn't earned; peeks go to the acting socket only. *Enforced:*
  `sockets/audience.py` guards every emit, `tests/test_leak_fuzz.py` fuzzes the view builders,
  `game/<variant>/visibility.py` is the single definition of "public".
- **Adding a game = register a Room class + settings + a table bundle.** No shared-core
  surgery; if a core change seems required, treat it as a seam fix and re-verify the other
  games. *Enforced:* `tests/test_platform_contract.py`. Note the honest wording — new games
  *register* into shared hooks (presenter, director, audience); they never *edit* shared logic.
- **A number in both code and prose is a bug waiting to happen** — generate it or test it.
  *Enforced:* `tests/test_settings_docs.py`.
- **Before anything merges to `main`:** `env_seven/bin/python run_tests.py` must exit 0. That
  is the gate; `main` is the deploy target and `beta_test` is where work happens.
  *(Replaces the old "don't touch the frozen `super_seven_cards-main` project" guardrail,
  which described a world where that project was live production and this was the risky
  rewrite. Both branches are now stable and play-tested, and that project is not in this
  repo.)*
