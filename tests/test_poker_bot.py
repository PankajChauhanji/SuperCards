import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker bot: always legal, plays whole games, and never sees hidden cards."""
import random

from game.core.cards import Card
from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.poker import ai
from game.poker.room import Room, PHASE_RUNOUT
from game.poker.settings import DEFAULT_SETTINGS

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


class Blindfold:
    """A room as one bot is allowed to see it.

    The deck, the burns and every other player's hole cards are simply absent —
    reading them raises — so a bot that peeks fails this test loudly instead of
    quietly playing better than it should.
    """
    FORBIDDEN = {"deck", "burns"}

    def __init__(self, room, me):
        object.__setattr__(self, "_room", room)
        object.__setattr__(self, "_me", me)

    def __getattr__(self, name):
        if name in Blindfold.FORBIDDEN:
            raise AssertionError("bot read room.%s" % name)
        value = getattr(self._room, name)
        if name == "hole":
            return {self._me: value.get(self._me, [])}
        return value


def make_room(n, **settings):
    s = dict(DEFAULT_SETTINGS)
    s.update(settings)
    room = Room("BOTS", "b0", s)
    for i in range(n):
        p = room.register_player("b%d" % i, "Bot %d" % i)
        p.connected = True
        p.is_bot = True
    return room


# ---- equity sanity ----
rng = random.Random(3)
aces = [Card(1, "S"), Card(1, "H")]
junk = [Card(7, "C"), Card(2, "D")]
eq_aces = ai.equity(aces, [], 1, samples=600, rng=rng)
eq_junk = ai.equity(junk, [], 1, samples=600, rng=rng)
check(0.75 < eq_aces < 0.92, "pocket aces win roughly 85%% heads-up (got %.2f)" % eq_aces)
check(eq_junk < 0.45, "7-2 offsuit is an underdog (got %.2f)" % eq_junk)
nuts = ai.equity([Card(1, "S"), Card(13, "S")],
                 [Card(12, "S"), Card(11, "S"), Card(10, "S")], 2, samples=200, rng=rng)
check(nuts == 1.0, "a made royal flush always wins")

# ---- whole games, bots only, through the blindfold ----
rng = random.Random(11)
illegal = []
peeked = []
finished = 0
for game_no in range(40):
    n = rng.randint(2, 6)
    room = make_room(n, rounds=rng.randint(2, 8))
    room.start_round()
    for _ in range(3000):
        if room.state == STATE_GAME_END:
            break
        if room.state == STATE_ROUND_END:
            room.start_round()
            continue
        if room.phase == PHASE_RUNOUT:
            room.step_runout()
            continue
        uid = room.current_turn_id()
        try:
            move = ai.decide_move(Blindfold(room, uid), uid, rng=rng)
        except AssertionError as exc:
            peeked.append(str(exc))
            break
        try:
            room.act(uid, move["action"], move["amount"])
        except ValueError as exc:
            illegal.append("%s %s: %s" % (move["action"], move["amount"], exc))
            room.act(uid, "fold")
    if room.state == STATE_GAME_END:
        finished += 1

check(not peeked, "bots never read the deck, burns or another player's cards%s"
      % ("" if not peeked else " (%s)" % peeked[0]))
check(not illegal, "every bot move was legal%s" % ("" if not illegal else " (%s)" % illegal[0]))
check(finished == 40, "40 bot-only games all finished (%d/40)" % finished)

# ---- the bot is not a calling station: it folds junk to a big bet ----
folds = 0
for trial in range(30):
    room = make_room(2)
    room._pick_first_button = lambda e: e[0]
    room.start_round()
    room.hole["b1"] = [Card(7, "C"), Card(2, "D")]
    room.hole["b0"] = [Card(9, "H"), Card(9, "S")]
    room.act("b0", "raise", 600_000)
    move = ai.decide_move(Blindfold(room, "b1"), "b1", rng=random.Random(trial))
    folds += move["action"] == "fold"
check(folds >= 25, "facing a 600k raise with 7-2, the bot folds nearly always (%d/30)" % folds)

check(1.0 <= ai.bot_delay() <= 3.5, "bot thinking time is human-ish")

print("\n%d/%d bot checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
