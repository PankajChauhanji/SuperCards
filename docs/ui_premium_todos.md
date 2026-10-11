# Premium UI — build TODOs

Goal: make Super Cards look and feel like a professional product rather than a personal
project. **No new games, no database, no rule changes.** Only presentation, layout and flow.
Agreed with the owner on 2026-10-11; developed on the `beta` branch, one commit per phase.

**Ground rules (from the Poker build, still apply):**
- Super Seven and Bluff are play-tested by 100+ regular players. Nothing they have learned
  moves without a reason: the action buttons, the hand and the turn order stay where they are.
- Shared-code edits stay additive where possible; game bundles keep their public APIs
  (`SS.themes.*`, `SS.deck.*`, `SS.viewMode.*`, `SS.Lobby.*`, `SS.showToast`).
- `.venv/bin/python run_tests.py` green before and after every phase.
- Every phase is checked in the browser for **all four games**, at desktop width and on a
  375px phone, measuring computed visibility rather than counting nodes (todos §11/§14b).
- `sw.js` cache bumped once per phase that changes shared JS/CSS (todos §18 deploy note).
- Undecided choices are marked **[decision]** so the owner can overrule them.

Status key: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase 1 — Quick wins — ✅ DONE (2026-10-11)

- [x] 1.1 **Footer off the room pages.** The GitHub / Email / LinkedIn / Star footer is gone
      from every game page. The home page keeps a slim footer: brand, Install app,
      and an "About" link that opens a small credits dialog (the GitHub and
      contact links live there). **[decision]** credits kept, just not on the table.
- [x] 1.2 **One icon set.** A single inline SVG sprite (`partials/icons.html`, thin-line,
      24px grid, `currentColor`) and an `SS.icon(name)` helper for JS-built markup. Every
      emoji used as *chrome* is replaced: topbar, settings, scores / history headings, Add
      bot, Shuffle seats, the floating buttons, pile labels, install dialog, rules dialog.
      Emoji stay where they are *content*: the reactions panel and floating reactions.
- [x] 1.3 **Settings sheet instead of a toolbar.** The topbar keeps only: brand, round chip,
      sound, rules and a ⚙ settings button. Settings opens a sheet (right-hand drawer on
      desktop, bottom sheet on phones) with: Table theme (host; colour swatches instead of
      emoji), Card deck, Hand view, Sound, Install app, Leave game. The phone hamburger
      menu goes away — the gear is the one way in at every width.
- [x] 1.4 **Round chip only during a game.** It no longer says "Round 1" in the lobby.
- [x] 1.5 **Toasts that mean something.** Errors red, everything else neutral. "Settings
      saved" no longer looks like an error. `SS.showToast(msg, ms, kind)` stays
      backward-compatible.
- [x] 1.6 **Naming.** Full names everywhere a name is read: "Super Seven", "Super Four",
      "Bluff", "Poker". The 7 / 4 stay as the emblem glyphs. **[decision]**
- [x] 1.7 Fonts: drop the unused Patrick Hand download.
- [x] 1.8 Verify (all games, desktop + phone), suite green, `sw.js` bump, commit.

## Phase 2 — Design system — ✅ DONE (2026-10-11)

- [x] 2.1 **Tokens** in `base.css`: type scale, spacing scale, radii, elevation (shadows),
      motion durations/easing, z-index scale, semantic colours (success / warning / danger /
      info) next to the existing graphite palette. Tabular numerals for scores and timers.
- [x] 2.2 **Buttons:** primary / secondary / ghost / danger, three sizes, one focus ring,
      loading state. Existing class names (`btn-primary`, `btn-ghost`, …) keep working.
- [x] 2.3 **Controls:** switch (replaces native checkboxes such as Shuffle seats),
      segmented control, chip / badge set (fewer all-caps micro-badges).
- [x] 2.4 **Surfaces:** one card style, one modal style (header / body / footer), one sheet
      style shared by Settings and the phone table sheet.
- [x] 2.5 Inline-styled dialogs (rules, install, spectator admit) moved onto the system.
- [x] 2.6 Verify, suite, bump, commit.

## Phase 3 — Home & lobby — ✅ DONE (2026-10-11)

- [x] 3.1 **Home as a landing page:** brand + tagline, "Join a table" with a code box at the
      top (the room code is how most players arrive), larger game cards with each game's
      symbol art, player counts and a one-liner; primary actions under the selected game.
- [x] 3.2 **Remember the player:** "Playing as Riya · Change" instead of an empty name box
      on every visit.
- [x] 3.3 **Invite links that work:** `/?join=ABCD` pre-fills the code and asks only for a
      name when needed. The lobby's Share uses it.
- [x] 3.4 **Lobby as a waiting room:** room code with Copy / Share / WhatsApp, players as
      seats (avatar, name, host crown, online dot) with empty seats waiting to be filled,
      settings shown as a readable summary with **Edit** for the host, a sticky start bar
      (Add bot · Shuffle seats switch · Start game). Guests see who they are waiting for.
- [x] 3.5 **Avatars without a database:** each player picks a motif + colour (stored on the
      device, sent with their name). Shown in the lobby, seats, scores and podium. Bots get
      fixed ones. Default is the player's initial, so nobody is forced to choose.
- [x] 3.6 Verify, suite, bump, commit.

## Phase 4 — Table — ✅ DONE (2026-10-11)

- [x] 4.1 **Table surface:** rounded table with a rail, soft lighting / vignette and a faint
      Super Cards mark in the centre of the felt — for the Classic-frame themes. The
      signature themes keep their own frames.
- [x] 4.2 **Motion:** cards dealt into your hand at round start, thrown cards land in the
      centre, a turn hand-off pulse. All skipped under reduced motion.
- [x] 4.3 **Haptics:** a short vibration when your turn starts (phones), with a switch in
      Settings.
- [x] 4.4 **Round summary redesign:** a proper header (who won / who called), avatar rows,
      clear deltas, the host's action on the right.
- [x] 4.5 **Player panels:** Scores / History rows on the new system, with avatars in the
      Scores rows and on the podium (carried over from 3.5).
- [x] 4.6 Verify, suite, bump, commit.

---

## Notes / decisions log

**2026-10-11**
- Plan agreed with the owner ("develop all phases, phase-wise"; pushed to `beta` only).

**Phase 1 notes**
- **Icons:** 57 symbols in `partials/icons.html`, checked on a rendered contact sheet
  before use. `SS.icon()` lives in `core/icons.js` (loaded right after `socket.js` on
  both pages). Emoji kept only as *content*: the reactions panel, and the reaction
  button showing your last emoji (its double-tap re-sends it — a feature regulars use).
- **Settings sheet:** `partials/settings_sheet.html` + `core/settings.js` +
  `css/settings.css`. The theme / deck / hand-view partials became its sections and
  kept their ids and `data-*` attributes, so `SS.themes`, `SS.deck`, `SS.viewMode`
  and every game bundle are unchanged. Guests now *see* the table theme (locked)
  instead of having it hidden. **[decision]** Leave table moved into the sheet; the
  Android back button still asks before leaving.
- **Theme swatches:** each theme's felt + rail colours sit on its button. The theme
  catalogue in `themes.js` lost its emoji, so `test_theme_assets.py` now matches
  `name:` instead of `icon:` (same check, new key).
- **Deck previews** carry `data-deck-fixed`, so `SS.deck.repaint()` leaves them alone —
  otherwise switching to Royal would have turned the Standard preview Royal too.
- **Bug found while building it:** the rules dialog's language buttons were selected
  with a page-wide `.lang-btn`, which would have caught the install dialog's buttons
  too once they shared the class. Scoped to `#rules-modal`.
- **Trap hit (again):** the browser kept old `table.css` / `home.js` after a reload, so
  a working change looked broken (todos §12). Verified only after forcing a refetch.
- Dev server for checks: `.claude/launch.json` → `super-cards-dev` (port 5051,
  `ROOM_PERSIST=0`, `FLASK_DEBUG=1`), so it never touches the owner's own server or its
  room snapshot. `.room_snapshot` added to `.gitignore`.
- Verified: home (desktop, About dialog), lobby, all four tables on desktop, Super Seven
  and Bluff on a 375px phone, the sheet as a drawer and as a bottom sheet (no horizontal
  overflow), rules from the sheet, neutral / success toasts. Suite 47 / 45 / 2 unscored.
- Noted for phase 2: Bluff's native "Select Rank" `<select>`, Super Four's purple
  "Start play" button, the spectator-admit dialog's inline styles, `confirm()` dialogs.

**Phase 2 notes**
- **Tokens** (`base.css :root`): type scale, 4px spacing, radii, three elevations, motion
  curves, semantic colours, one `--focus-ring`, and a documented z-index ladder.
  Tabular numerals on scores, timers and chips; Inter's open digits (`cv05`, `ss01`).
- **Buttons:** `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-danger` (+ `.solid`)
  / `.btn-solo`, `.btn-sm` / `.btn-lg`, `.is-loading`. Same class names as before, so no
  markup had to change. One `:focus-visible` ring for buttons and links; fields keep
  their gold border instead (a ring on a text box read as an error).
- **Fields:** a styled `<select>` (Bluff's rank picker was the white browser default).
- **Badges** are sentence-case pills ("Turn", "Next", "Host", "You") instead of
  all-caps micro-labels.
- **Dialogs:** one look (blurred backdrop, rise-in, actions bottom-right). New
  `core/dialog.js` → `SS.confirm()` replaces `window.confirm()` for Leave table, the
  Android back button and Remove player. Focus lands on Cancel, so a stray Enter
  never confirms something destructive.
- **Fixed in passing (todos §22):** the floating reaction button (z 61) drew on top of
  every dialog (z 50), and on narrow phones covered the round summary's button.
  Dialogs now sit at z 85, above the dock and the phone sheet.
- Spectator-admit dialog rebuilt on the system (no inline styles); Super Four's purple
  accents (turn ring, drawn card, buttons) moved onto the app palette; the phone
  Scores / History sheet's tabs use the same segmented control as Settings.
- Verified: confirm dialog (Bluff), rank select computed styles, Super Four table +
  buttons, spectator dialog open / close. Suite 47 / 45 / 2 unscored.

**Phase 3 notes**
- **Home** (`index.html`, `home.js`, new `css/home.css`): a nav with the logo and a
  player chip, a short pitch, *Join a table* beside it (first on phones), and *Start a
  table* with four game cards (symbol art, one-liner, player count from the registry —
  `app.py` now passes `min_players` / `max_players`). Old home rules removed from
  `base.css` / `lobby.css` / `reactions.css` so nothing stale competes.
- **Remembered player:** name + avatar live on the device (`Identity.avatar()` beside
  `Identity.name()`). A first visit is never blocked by an empty name box: pressing
  Create / Practice / Join asks for a name in the player dialog and then carries on.
- **Invite links:** the lobby shares `/?join=CODE` (Share link / WhatsApp). And a bare
  `/room/CODE` link opened by someone who has not joined now lands on that same join
  screen: `enter_room` answers `error(..., reason="not_in_room")`, `core/socket.js`
  redirects. `sockets/common.error()` gained the optional `reason`.
- **Waiting-room lobby** (`game.html`, `core/lobby.js` rewritten, `lobby.css`): invite
  card (code, Copy / Share / WhatsApp), seats with avatars, online dot, host / you badges
  and open seats, table rules as a readable summary for everyone (Indian digit grouping,
  On / Off) with **Edit** for the host, a start bar that is pinned to the bottom on
  phones. Start is disabled with a reason below the game's minimum players
  (`window.MIN_PLAYERS`, from `app.py`). Guests see "Waiting for <host> to start".
  Same `SS.Lobby` API and the same element ids the bundles look up, so no game changed.
- **Avatars** (`game/core/avatars.py`): a motif name, validated server-side, stored on
  `Player.avatar`, in every game's `public_players()`. **[decision]** the colour stays
  the player's existing identity colour (seats / scores / log already use it); only the
  motif is chosen. Bots have fixed motifs. Shown in the lobby seats, the table seats
  (`core/seats.js`, via `SS.avatarFace()`), the bot picker and the home chip.
  `tests/test_avatars.py` (25 checks): unknown values become "", the JS and server lists
  match, every motif has an icon, every game carries it, the socket path, the redirect.
- **Bugs found while building it:**
  * Super Seven's round chip came back in the lobby because `Table.render` is also
    reached from the shared repaint hook there; it now shows only during a round.
  * My lobby rewrite deleted the `.badge` rules that sat inside the old lobby block —
    caught on the first screenshot, restored.
  * The seats re-render on every roster change, so an entrance animation replayed every
    time anyone joined; dropped.
- Verified: home desktop + phone, invite state, player dialog, lobby desktop + phone
  (host, rules editor, guest view), the full invite flow from a fresh browser identity
  (room link → join screen → name prompt → lobby), avatars on the table. Suite 48 / 46 /
  2 unscored.

**Phase 4 notes**
- **Classic table** (`themes.css`): the five palette themes share one geometry — 30px
  corners (22px on phones), a padded rail and a thin rim drawn as box-shadow rings
  *outside* the border (so the felt keeps its width and nothing inside moves), light
  from above with a vignette, and a faint ring-and-spade emblem behind the cards
  (`isolation: isolate` + `z-index: -1`). Each theme now sets only its cloth, `--rim`
  and `--rail`. The twelve signature themes are untouched. The emblem is SVG geometry,
  so `test_theme_assets.py` audits it like the others.
- **Motion** (`core/motion.js` + `table.css`): the first hand after a round starts is
  dealt in card by card; a throw lands in the centre (both games already rebuild the
  pile only when it changes, so it plays once per throw, newest four cards only); your
  seat sends out a soft halo when the turn reaches you. Animations sit on the card
  images, never the slots (the fan positions slots with transforms), with fill mode
  `backwards` so a selected card's raise is never overridden. All off under
  reduced-motion.
- **Haptics:** a short double buzz when your turn starts, riding on
  `SS.sound.turnPing()`, which every game already calls at exactly that moment. Works
  even when sound is muted; has its own Settings switch, offered only on touch devices
  (desktop Chrome exposes `navigator.vibrate` and silently ignores it).
- **Round summary:** gold top edge, one card per player with avatar, a points-change
  pill (green when nothing was added) and the total. Super Seven and Poker rows.
- **Player panels:** the Scores rows' colour square became a mini avatar in all four
  games; the podium shows each player's avatar (standings rows now carry `avatar` and
  `color` — additive keys in all four rooms).
- Verified with a real Super Seven game driven to the end from the page: deal
  animation fired, summary rendered with avatars and pills, podium with avatars. Bluff
  on a 375px phone: rounded table, no horizontal overflow. Suite 48 / 46 / 2 unscored.
- **Still open (pre-existing, not introduced here):** at 375px Bluff's Throw / Pass /
  Show row is a little wider than the felt, so Show sits partly under the floating
  buttons (todos §21c). Not verifiable here: vibration on a real phone.

## Follow-up — owner feedback (2026-10-11) — ✅ DONE

- [x] **"Practice with bots" → "Play with computer"** on the home page; the lobby's
      button is "Add computer".
- [x] **Table theme is personal**, like the card deck and hand view: each player picks
      their own felt in Settings and it changes only their screen. `core/themes.js`
      stores it on the device (`super_cards_theme`) and applies it whenever a game calls
      `SS.themes.apply()`, ignoring the room's old shared theme — so no game bundle
      changed. Nothing is sent to the server any more; the server's
      `change_table_theme` handler and `table_theme` field are now unused but left in
      place (harmless, and removing them is a separate server cleanup).
- [x] **Host vs player settings, simplified:** the Settings sheet is personal settings
      only, for everyone (sound, vibrate, deck, hand view, theme, rules, install, leave).
      Host-only controls live where they act and are shown only to the host: table
      rules (Edit), Add computer, remove player, shuffle seats, Start / Next round,
      letting spectators in. Checked from a guest's seat: none of them appear.
- [x] **Room links go straight to the room.** Share / WhatsApp now send the room's own
      address (`/room/CODE`). Opening it without being seated shows a join card on that
      page (`partials/join_gate.html`, `core/join_gate.js`): the game, who is hosting,
      the room code, a name box (pre-filled if the device knows you), an optional
      avatar, and **Join table** — which seats you and brings the room up behind the
      card, with no reload, no game picker and no code to type. A game already in
      progress says you will watch until the host lets you in.
  * Old `/?join=CODE` links redirect to `/room/CODE`.
  * A link to a closed room lands on the home page with "Table ABCD has closed…"
    instead of a silent redirect (`/?gone=CODE`).
  * The Android back button on the join card just goes home (there is nothing to
    leave yet).
  * The avatar list moved to `SS.AVATARS` in `core/icons.js`, shared by the home page
    and the join card; `test_avatars.py` checks it against the server's list.
- Verified in the browser at 375px: a fresh visitor opening `/room/CODE` → join card →
  name + avatar → seated in the lobby (host's seat and theirs, "Waiting for <host>");
  the guest's theme choice applies locally and emits nothing; the `/?join=` redirect;
  the closed-room message. Suite 48 / 46 / 2 unscored. `sw.js` v12 → v13.

- **Action history: kept as it is (owner's call, 2026-10-11).** Discussed hiding it on
  desktop behind a "Scores | History" tab; decided to leave it visible for now. It
  carries real game information in Bluff (passes, throw counts, Show results) and
  Poker (bets per street). Revisit only if players ask.
