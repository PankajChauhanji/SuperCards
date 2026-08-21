import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Randomized hidden-information leak harness for all three games.

Hand-written tests cover the cases someone thought of. This one plays thousands
of random-but-legal games and, after *every single action*, re-derives what each
viewer is legitimately allowed to know and asserts that no view hands them
anything more. It is aimed squarely at the guardrail that matters most:

    the server must never send a card face to a player who has not earned it.

Why fuzz rather than more unit tests: the leak-prone rules are combinatorial.
Super 4's "knowledge follows the card through a swap" is the clearest example —
a King look on two positions followed by a blind swap of one of them, twice, is
not a case anyone enumerates by hand, but it is three random actions here.

How a leak is detected
----------------------
Every ``Card`` reaches a client through ``Card.to_dict()``, so a serialized card
is precisely "a dict carrying both ``rank`` and ``suit``". ``walk_cards()`` finds
them at any depth and reports the payload path, which makes a failure directly
actionable instead of just "something leaked". Because detection keys on that
dict shape rather than on strings, a player literally named "AS" or a theme
called "KD" cannot produce a false positive.

Per game, two oracles say what is allowed:
  * ``public_ids(room)``   — card faces the rules put on the table for everyone.
  * ``private_ids(room,v)`` — additionally allowed in v's own private payload.
Anything else appearing in a payload is a leak.

Scope (deliberate, and stated so it is not mistaken for more than it is)
-----------------------------------------------------------------------
Only the **in-play** phase is asserted (``state == IN_TURN``). Round end and
game end reveal every hand by design, so they are not leaks and are skipped.
This harness checks the *view builders* — what a payload contains. It does not
check *audience routing*, i.e. that a private payload was emitted to one socket
rather than the room; that is the emit chokepoint's job (sockets/audience.py).
The two together are what actually closes the guardrail.
"""
import random
import traceback

from game.core.states import STATE_IN_TURN
from game.core.visibility import EVERYTHING

# Games × steps per game. Chosen to run in a few seconds while still reaching
# deep states (Super 4 needs ~15 actions before swaps start compounding).
GAMES_PER_VARIANT = 40
STEPS_PER_GAME = 70
PLAYER_COUNTS = (2, 3, 4)

results = []
failures = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


# ── leak detection ───────────────────────────────────────────────────────

def walk_cards(node, path=""):
    """Yield (card_id, path) for every serialized Card anywhere in a payload."""
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str):
            yield node.get("id") or "%s%s" % (node["rank"], node["suit"]), path or "<root>"
            return  # cards do not nest inside cards
        for key, val in node.items():
            yield from walk_cards(val, "%s.%s" % (path, key) if path else str(key))
    elif isinstance(node, (list, tuple)):
        for idx, val in enumerate(node):
            yield from walk_cards(val, "%s[%d]" % (path, idx))


def scan(payload, allowed, label, viewer, ctx):
    """Return a list of human-readable leak descriptions (empty == clean)."""
    found = []
    for card_id, path in walk_cards(payload):
        if card_id not in allowed:
            found.append(
                "%s: %s leaked %s at %s (viewer=%s, %s)"
                % (ctx["variant"], label, card_id, path, viewer, ctx["where"])
            )
    return found


# ── per-game adapters ────────────────────────────────────────────────────

class SevenFuzz:
    """Super Seven: hands are secret, the center throw is face-up and public."""

    variant = "Super Seven"

    def build(self, rng, n):
        from game.super_seven.room import Room
        from game.super_seven.settings import DEFAULT_SETTINGS
        room = Room("FUZZ", "u0", dict(DEFAULT_SETTINGS))
        uids = ["u%d" % i for i in range(n)]
        for i, uid in enumerate(uids):
            player = room.register_player(uid, "P%d" % i)
            player.connected = True
        room.start_round()
        return room, uids

    def step(self, room, rng):
        from game.super_seven.rules import infer_action
        uid = room.current_turn_id()
        if uid is None:
            return None
        if room.awaiting_draw:
            room.draw_one(uid)
            return "draw"
        hand = list(room.players[uid].hand)
        if not hand:
            return None
        center = room.center_rank_set()
        # Prefer a random legal multi-card play; fall back to a single, which is
        # always legal. Trying subsets keeps combos and matches in the mix.
        for _ in range(12):
            size = rng.randint(1, min(4, len(hand)))
            sel = rng.sample(hand, size)
            action = infer_action([c.rank for c in sel], center)
            if action:
                room.apply_throw(uid, sel, action)
                return action
        sel = [rng.choice(hand)]
        action = infer_action([c.rank for c in sel], center) or "single"
        room.apply_throw(uid, sel, action)
        return action

    def public_ids(self, room):
        from game.super_seven.visibility import public_card_ids
        return public_card_ids(room)

    def private_ids(self, room, viewer):
        pub = self.public_ids(room)
        if pub is EVERYTHING:
            return pub
        return pub | {c.id for c in room.players[viewer].hand}

    def views(self, room, viewer):
        return [
            ("public_round_state", room.public_round_state(), False),
            ("public_players", room.public_players(), False),
            ("hand_for", room.hand_for(viewer), True),
        ]


class BluffFuzz:
    """Bluff: nothing is face-up. The whole point is that the pile stays hidden.

    So the public oracle is the *empty set* — a single card face in any public
    payload is a leak, because seeing the pile makes every Show call trivially
    correct and the game unplayable.
    """

    variant = "Bluff"

    def build(self, rng, n):
        from game.bluff.room import Room
        from game.bluff.settings import DEFAULT_SETTINGS
        room = Room("FUZZ", "u0", dict(DEFAULT_SETTINGS))
        uids = ["u%d" % i for i in range(n)]
        for i, uid in enumerate(uids):
            player = room.register_player(uid, "P%d" % i)
            player.connected = True
        room.start_round()
        return room, uids

    def step(self, room, rng):
        from game.core.cards import RANKS, rank_code
        if getattr(room, "game_over", False):
            return None
        uid = room.current_turn_id()
        if uid is None:
            return None
        roll = rng.random()
        can_show = room.last_play and room.last_play["user_id"] != uid
        if can_show and roll < 0.25:
            result = room.apply_show(uid)
            if result:
                # A Show may reveal ONLY the cards of the play being challenged,
                # never the buried pile. Assert that here: it is the one moment
                # Bluff intentionally exposes faces, so its blast radius matters.
                claimed = {c.id for c in room.last_play["cards"]}
                revealed = {c["id"] for c in result.get("revealed_cards", [])}
                extra = revealed - claimed
                if extra:
                    raise AssertionError(
                        "Show revealed cards beyond the challenged play: %s" % sorted(extra)
                    )
                room.resolve_show(result)
            return "show"
        hand = room.players[uid].hand
        if hand and roll < 0.9:
            size = rng.randint(1, min(4, len(hand)))
            sel = rng.sample(list(hand), size)
            declared = room.target_rank or rank_code(rng.choice(RANKS))
            room.apply_play(uid, sel, declared)
            return "play"
        room.apply_pass(uid)
        return "pass"

    def public_ids(self, room):
        from game.bluff.visibility import public_card_ids
        return public_card_ids(room)

    def private_ids(self, room, viewer):
        pub = self.public_ids(room)
        if pub is EVERYTHING:
            return pub
        return pub | {c.id for c in room.players[viewer].hand}

    def views(self, room, viewer):
        return [
            ("public_round_state", room.public_round_state(), False),
            ("public_players", room.public_players(), False),
            ("hand_for", room.hand_for(viewer), True),
        ]


class FourFuzz:
    """Super 4: four face-down slots, per-viewer knowledge, powers and swaps.

    The strict rule (DESIGN.md): a player sees their own preview cards only while
    the preview window is open, and a drawn card only if they drew it. Peeks are
    delivered as one-shot targeted events, NOT replayed into private_view — so
    private_view must not contain a peeked card even though the viewer "knows" it.
    """

    variant = "Super 4"

    def build(self, rng, n):
        from game.super_four.room import Room
        from game.super_four.settings import DEFAULT_SETTINGS
        room = Room("FUZZ", "u0", dict(DEFAULT_SETTINGS))
        uids = ["u%d" % i for i in range(n)]
        for i, uid in enumerate(uids):
            player = room.register_player(uid, "P%d" % i)
            player.connected = True
        room.start_round()
        return room, uids

    def _opponent(self, room, uid, rng):
        others = [u for u in room.turn_order if u != uid and room.slots.get(u)]
        return rng.choice(others) if others else None

    def _filled_slot(self, room, uid, rng):
        cards = room.slots.get(uid) or []
        idxs = [i for i, c in enumerate(cards) if c is not None]
        return rng.choice(idxs) if idxs else None

    def step(self, room, rng):
        from game.super_four.room import (
            PHASE_DRAW, PHASE_DECIDE, PHASE_POWER, PHASE_MATCH, PHASE_PREVIEW,
        )
        phase = room.phase

        if phase == PHASE_PREVIEW:
            if rng.random() < 0.5:
                room.begin_play()
            else:
                room.expire_preview()
            return "preview_end"

        if phase == PHASE_MATCH:
            # Either someone reacts to the face-up discard, or the window lapses.
            if rng.random() < 0.5:
                actor = rng.choice(list(room.turn_order))
                slot = self._filled_slot(room, actor, rng)
                if slot is not None and rng.random() < 0.5:
                    room.match_center_own(actor, slot)
                else:
                    room.match_decline(actor)
                return "match_react"
            room.expire_match_window()
            return "match_expire"

        if phase == PHASE_POWER:
            pending = room.pending_power or {}
            actor, rank = pending.get("by"), pending.get("rank")
            if actor is None:
                room.expire_match_window()
                return "power_stuck"
            if rng.random() < 0.25:
                room.power_skip(actor)
                return "power_skip"
            own = self._filled_slot(room, actor, rng)
            opp = self._opponent(room, actor, rng)
            opp_slot = self._filled_slot(room, opp, rng) if opp else None
            if rank in (7, 8) and own is not None:
                room.power_peek_own(actor, own)
            elif rank in (9, 10) and opp and opp_slot is not None:
                room.power_peek_opp(actor, opp, opp_slot)
            elif rank in (11, 12) and own is not None and opp and opp_slot is not None:
                room.power_blind_swap(actor, own, opp, opp_slot)
            elif rank == 13 and own is not None and opp and opp_slot is not None:
                room.power_king_look(actor, own, opp, opp_slot)
                room.power_king_decide(actor, rng.random() < 0.5)
            else:
                room.power_skip(actor)
            return "power_%s" % rank

        uid = room.current_turn_id()
        if uid is None:
            return None

        if phase == PHASE_DRAW:
            if room.first_orbit_complete and rng.random() < 0.06:
                if room.call_stop(uid):
                    return "stop"
            room.draw(uid)
            return "draw"

        if phase == PHASE_DECIDE:
            roll = rng.random()
            slot = self._filled_slot(room, uid, rng)
            if roll < 0.4 and slot is not None:
                room.keep(uid, slot)
                return "keep"
            if roll < 0.6 and slot is not None:
                room.match_own(uid, slot)
                return "match_own"
            room.discard(uid)
            return "discard"

        return None

    def public_ids(self, room):
        from game.super_four.visibility import public_card_ids
        return public_card_ids(room)

    def private_ids(self, room, viewer):
        import time as _time
        from game.super_four.room import PHASE_PREVIEW
        ids = self.public_ids(room)
        if ids is EVERYTHING:
            return ids
        ids = set(ids)
        # Own preview cards, and ONLY while the preview window is genuinely open.
        if room.phase == PHASE_PREVIEW and _time.time() < room.preview_deadline:
            for (owner, slot) in room.known.get(viewer, set()):
                if owner != viewer:
                    continue
                cards = room.slots.get(owner) or []
                if slot < len(cards) and cards[slot] is not None:
                    ids.add(cards[slot].id)
        # The card you just drew is yours to see.
        if room.drawn is not None and room.drawn_by == viewer:
            ids.add(room.drawn.id)
        return ids

    def views(self, room, viewer):
        return [
            ("public_round_state", room.public_round_state(), False),
            ("public_players", room.public_players(), False),
            ("private_view", room.private_view(viewer), True),
        ]


# ── the fuzz loop ────────────────────────────────────────────────────────

def fuzz(adapter):
    """Play many random games, checking every view after every action."""
    leaks = []
    crashes = []
    steps_done = 0
    states_seen = set()

    for game_no in range(GAMES_PER_VARIANT):
        seed = game_no
        rng = random.Random(seed)
        n = PLAYER_COUNTS[game_no % len(PLAYER_COUNTS)]
        try:
            room, uids = adapter.build(rng, n)
        except Exception:
            crashes.append("seed=%d players=%d build failed:\n%s"
                           % (seed, n, traceback.format_exc()))
            continue

        for step_no in range(STEPS_PER_GAME):
            if room.state != STATE_IN_TURN:
                break
            try:
                action = adapter.step(room, rng)
            except AssertionError as exc:
                leaks.append("seed=%d step=%d: %s" % (seed, step_no, exc))
                break
            except Exception:
                crashes.append("seed=%d step=%d players=%d crashed:\n%s"
                               % (seed, step_no, n, traceback.format_exc()))
                break
            if action is None:
                break
            steps_done += 1
            states_seen.add("%s/%s" % (room.state, getattr(room, "phase", "-")))

            if room.state != STATE_IN_TURN:
                break  # round/game end reveals legitimately; out of scope

            ctx = {"variant": adapter.variant,
                   "where": "seed=%d step=%d after=%s" % (seed, step_no, action)}
            try:
                pub = adapter.public_ids(room)
                for viewer in uids:
                    priv = adapter.private_ids(room, viewer)
                    for label, payload, is_private in adapter.views(room, viewer):
                        allowed = priv if is_private else pub
                        leaks.extend(scan(payload, allowed, label, viewer, ctx))
            except Exception:
                crashes.append("seed=%d step=%d view build crashed:\n%s"
                               % (seed, step_no, traceback.format_exc()))
                break
            if leaks:
                break
        if leaks or crashes:
            break

    return leaks, crashes, steps_done, states_seen


print("Hidden-information fuzz — %d games x %d steps per variant\n"
      % (GAMES_PER_VARIANT, STEPS_PER_GAME))

# Super Seven first: it is the most-played game, so it is the one a leak would
# hurt most. Bluff next, then Super 4.
for adapter in (SevenFuzz(), BluffFuzz(), FourFuzz()):
    leaks, crashes, steps, states = fuzz(adapter)
    label = "%s: no hidden-card leak across %d random actions" % (adapter.variant, steps)
    check(not leaks and not crashes, label)
    if steps == 0:
        check(False, "%s: fuzzer never advanced a single action (driver broken)"
              % adapter.variant)
    for line in leaks[:6]:
        print("    LEAK  " + line)
    for line in crashes[:3]:
        print("    CRASH " + line)
    if not leaks and not crashes:
        print("      states exercised: %s" % ", ".join(sorted(states)))

print("\n%d/%d leak-fuzz checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
