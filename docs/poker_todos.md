# Poker (Texas Hold'em) — Build TODOs

Working checklist for adding Poker as the platform's 4th game. We work through it **point by
point, in order**. A phase is only started once the one before it is signed off.

- **Rules:** [`docs/poker_rules.md`](poker_rules.md) is the source of truth for gameplay.
- **Platform rules still apply** (see the Guardrails at the end of `todos.md`):
  - one process only;
  - the server decides who sees which cards;
  - adding a game means *registering* it, never editing shared logic;
  - any number written in both code and docs is pinned by a test.
- **Reuse first:** cards/deck, lobby, room lifecycle, seats, scores panel, mobile sheet,
  reactions, themes, deck choice, rules modal, winner podium, bots and the turn-timer
  director are all shared already. Poker plugs into them; it does not fork them.
- **Rule of two:** chips, pots and betting stay inside `game/poker/` until a second betting
  game exists (e.g. Teen Patti). Only then do they move to `game/core/`.

Status key: `[ ]` todo · `[~]` in progress / awaiting review · `[x]` done

---

## Phase 1 — Rules

- [x] 1.1 Write `docs/poker_rules.md`: settings, round flow, actions, pots, hand ranking,
      game end, medals, timers, hidden information.
- [x] 1.2 Review with the owner; resolve every item under "Open questions".
- [x] 1.3 Freeze v1 rules (any later change is a dated entry in the rules doc).

## Phase 2 — UI definition (design only, no code)

- [x] 2.1 Write `docs/poker_ui.md`: the screen-by-screen spec.
- [x] 2.2 Home tile + brand: name, symbol (`static/img/poker_symbol.svg`, same card-emblem
      style as the others), accent colour.
- [x] 2.3 Lobby settings fields (shared `core/lobby.js` schema): starting coins, rounds,
      turn timer, timeout limit, blinds-double-every.
- [x] 2.4 Table layout, desktop and mobile:
      - board (5 cards) and pot(s);
      - seats showing stack, current bet, dealer/SB/BB markers, folded/all-in/sitting-out
        states, turn ring (shared `core/seats.js`);
      - your hole cards.
- [x] 2.5 Action bar: Fold / Check / Call / Bet / Raise / All-in, a bet slider with presets
      (½ pot, pot, all-in), a "you can check for free" warning on Fold, and a mobile layout.
- [x] 2.6 Showdown + round end: card reveal, winning hand name, pot split, the pause before
      the next round.
- [x] 2.7 Game end: shared winner podium with final chips and net +/-.
- [x] 2.8 Chip number formatting (compact on the table, full amount on hover/tap).
- [x] 2.9 Rules modal content: `static/rules/poker/{en,hi}.html`.
- [~] 2.10 Review with the owner and sign off. The owner asked to go straight to
      development, so the spec was built as written and is awaiting a look at the real screens.

## Phase 3 — Backend engine (`game/poker/`, no sockets)

- [x] 3.1 `settings.py`: MIN/MAX players, DEFAULT_SETTINGS, SETTINGS_BOUNDS, rule constants.
- [x] 3.2 `evaluator.py`: best 5 of 7, all 9 categories, kickers, ace-low straight, ties.
- [x] 3.3 `pots.py`: main/side pot construction, eligibility, splits, odd chip, uncalled bet
      returned.
- [x] 3.4 `room.py`: the state machine for a round.
      - Covers: button/blinds, dealing, betting stages, the min-raise rule, the incomplete
        all-in rule, the all-in runout, showdown, busting, game end, rankings.
      - Satisfies `RoomProtocol`.
- [x] 3.5 Sit-out / timeout behaviour and quitting mid-round.
- [x] 3.6 Late joiners: spectator, admitted at the next round with the average stack.
- [x] 3.7 `visibility.py`: the definition of what is public, used by the audience guard and
      the leak fuzzer.
- [x] 3.8 `ai.py`: bot. On every street it simulates random opponent hands to estimate its
      chance of winning and weighs that against the pot odds; a separate pre-flop chart turned
      out to be unnecessary. It sees only its own hole cards.
- [x] 3.9 Register in `game/core/registry.py`. It was registered once the client existed, so
      it went straight to `ready=True`.

## Phase 4 — Engine tests

- [x] 4.1 Evaluator: every category, kicker ties, wheel, board plays, split.
- [x] 4.2 Pots: 2/3/4-way all-ins at different sizes, folded contributors, odd chip.
- [x] 4.3 Betting: min bet/raise, incomplete all-in does not reopen betting, BB option,
      heads-up order.
- [x] 4.4 Round/game flow: fold-win, showdown, runout, bust, round limit, last player
      standing, rankings + ties.
- [x] 4.5 Leak tests: `test_leak_fuzz.py` covers poker (hole cards, deck, burns, folded
      hands).
- [x] 4.6 `test_settings_docs.py` claims for every number stated in the rules doc / HTML.
- [x] 4.7 `test_platform_contract.py` green for poker.

## Phase 5 — Socket layer

- [x] 5.1 `sockets/gameplay/poker.py`: one `poker_action` event (fold / check / call / bet /
      raise / allin) plus `poker_back` and `poker_next_round`, all guarded on `game_type`.
- [x] 5.2 Presenter: deal hook (hole cards to own socket only) + resync hook (reconnect at
      every state).
- [x] 5.3 Director ticker: turn timeout (auto-check else fold), bot turns, round-end pause →
      next round.
- [x] 5.4 Socket e2e test in `test_all_games_socket.py` + a multi-client poker test.

## Phase 6 — Frontend build

- [x] 6.1 `templates/games/poker/{branding,table,scripts}.html`.
- [x] 6.2 `static/js/poker/game.js` (+ `table.js` if it grows), wired to the shared core
      modules.
- [x] 6.3 Poker table CSS (felt themes shared; poker-only styles scoped).
- [x] 6.4 Rules HTML en/hi, home tile, symbol SVG.
- [x] 6.5 In-browser verification at the desktop pane width and on a 375px phone, checking
      computed visibility rather than just that nodes exist (the §11/§18 lesson). No console
      errors. The 1847px wide-screen layout is shared and was not re-measured for poker.

## Phase 7 — Release

- [x] 7.1 `run_tests.py` exits 0.
- [x] 7.2 `ready=True`; `sw.js` cache bumped v6 → v7.
- [x] 7.3 README game section + a dated entry in `todos.md`.
- [ ] 7.4 Play-test with real players; feed fixes back here.

---

## Notes / decisions log

**2026-10-05**
- **Rules agreed.** The owner's answers:
  * a round-summary popup between rounds, with every player's coins left;
  * the host starts the next round, or it starts by itself after 30s;
  * up to 20 players;
  * 10 rounds by default;
  * K/M on the table and Lakh/Crore in the Hindi rules;
  * a "Blinds double every N rounds" setting, off by default;
  * late joiners seated with the average stack.
- **Built and verified** phases 2–7.3 in one pass. The full write-up is `todos.md` §21.
- **Shared code touched (additive only):**
  * `sockets/director.py`, a `states=` option on `register_ticker`;
  * the home picker (`index.html`, `lobby.css`);
  * `core/waking.js` tips;
  * the `sw.js` cache version.
- **Design choices made while building, beyond the rules doc:**
  * one `poker_action` event carries every decision, rather than one event per button;
  * the bot estimates its chance of winning from up to 4 simulated opponents, 240 samples
    per decision, about 10 ms;
  * the scores panel's running net counts coins in the current pot as still the player's;
  * the phone action bar gets symmetric side padding so it clears the fixed reaction dock.
- **Still open:** 7.4, a real play-test with friends on real phones. Things to watch:
  * the bot's aggression level;
  * whether 30s turns feel right at a 20-seat table;
  * the seat arc at 8+ opponents on a 375px phone. This is a known pre-existing limit
    (todos §14c) and poker inherits it.

**2026-10-05 — first play-test feedback (owner)**
- [x] Browser `confirm()` dialogs replaced by small bubbles anchored to the button (All-in,
      and Fold when checking is free).
- [x] Hole cards sometimes appeared late.
  * **Causes:** the private deal was sent only once, card images were fetched on first
    use, and a new round could briefly show the previous round's cards.
  * **Fix:**
    * every table update now re-sends your hand, tagged with its round number;
    * the client deals face down until your cards arrive, then flips them once the image is
      decoded;
    * a stale copy from the previous round is ignored;
    * the deck images are preloaded.
- [x] The card-count badge made no sense in poker.
  * The seat circle is now the money: a gauge of the stack vs. coins received, with the
    amount written in it.
  * The badge became a money pouch (gold when up, flat when down).
  * Two mini face-down cards show who is still in.
- [x] The pot is a growing pile of gold coins.
- [x] Coins fly from a seat to the pot on every bet, and from the pot to the winner at
      round end, with a chip clink.
- [x] **Extras from Claude:**
  * your hand's name under your cards;
  * the winning five highlighted on the board;
  * the payout plays before the summary opens;
  * Check / Fold and Check pre-actions.

**2026-10-06**
- [x] Hand-rankings cheat sheet in the Coins card, collapsed by default and client-only
      (`static/js/poker/rankings.js`).
  * **Bug found while building it:** inside the phone sheet the Coins card is a
    fixed-height column, so the open sheet squeezed the coins list to 0px. The two now
    share the height and scroll separately.
- [ ] Big-table layout (two rows of seats on phones at 8+ opponents): skipped for now, at
      the owner's call.
- [x] **Hand hints are a host setting, off by default** (owner's call: one rule for the
      whole table, not a per-player switch).
  * With hints off, the server sends no hand name or rankings row at all.
  * With hints on, each player sees "Your hand: …" under their cards, a gold chip in the
    Hand rankings header, and their row highlighted; the card opens straight onto that row.
  * The lobby switch uses a new, additive `{type: "toggle"}` field in the shared
    `core/lobby.js`. Super Seven, Super Four and Bluff pass no type, so their settings
    render and save exactly as before (checked in the browser).
- [x] **Hand-rankings card moved out of the Coins card** (owner feedback: hard to scroll,
      sometimes not at all).
  * It is now its own 🃏 button with one panel and one scroll area: docked on the felt on
    desktop, all ten rows fit without scrolling; a bottom sheet on a phone.
  * The side column and the phone sheet are back to Coins + Action History.
- [x] **Hand hints checked end to end.** Two problems made it look broken:
  * the switch did nothing until "Save settings" was pressed; it now saves the moment it is
    flipped;
  * before the flop an unpaired hand showed nothing; with hints on it is now "High Card,
    King".
  * `test_poker_socket.py` pins both directions with two real clients: off sends no hand
    names, on sends each player their own.
- [x] Hand-rankings cards enlarged (46×64 desktop, 52×73 phone) and rows reflowed to two
      lines; the panel scrolls inside, never taller than the table or the window.
- [x] Fixed a flaky room test: "equal coins share a place" guessed at a random deal and
      failed about 3% of runs when everyone ended level. It now uses rigged cards for three
      cases.

