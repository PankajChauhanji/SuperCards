import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Bluff: the host's in-game "Shuffle seats".

The promise is narrow and every part is checked here:
  * it never re-seats mid-play — at a fresh round (pile empty, no rank locked)
    it applies at once, otherwise it waits for the pile to clear (a resolved
    Show or a full pass);
  * whoever is about to lead keeps the lead; only neighbours change;
  * the same players keep the same hands and finishing places;
  * pressing again while it is queued cancels it.
A random-play fuzz then presses it at random moments and checks the game still
reaches its end with every invariant intact.
"""
import random

from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.states import STATE_IN_TURN, STATE_GAME_END

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


def make(n=5):
    room = Room("SHUF", "p0", dict(DEFAULT_SETTINGS))
    for i in range(n):
        room.register_player("p%d" % i, "P%d" % i).connected = True
    room.start_round()
    return room


def hands(room):
    return {u: sorted(c.id for c in room.players[u].hand) for u in room.players}


# ---- fresh round: applies at once, leader keeps the lead ----
random.seed(1)
room = make()
leader = room.current_turn_id()
before_hands = hands(room)
result = room.request_shuffle()
check(result == "applied" and room.seat_shuffles == 1 and not room.shuffle_pending,
      "pressed at a fresh round: seats shuffle at once")
check(room.current_turn_id() == leader, "the player about to lead still leads")
check(sorted(room.turn_order) == ["p0", "p1", "p2", "p3", "p4"], "the same five players are seated")
check(hands(room) == before_hands, "nobody's hand changes")
check(room.public_round_state()["seat_shuffles"] == 1, "the public state reports the shuffle")

# ---- mid-round: queued, nothing moves until the pile clears ----
room = make()
lead = room.current_turn_id()
card = room.players[lead].hand[0]
room.apply_play(lead, [card], "7")
order = list(room.turn_order)
result = room.request_shuffle()
check(result == "pending" and room.shuffle_pending and room.turn_order == order,
      "pressed mid-round: queued, the seating does not move")
check(room.public_round_state()["shuffle_pending"] is True, "everyone can see it is queued")

# ...a Show settles the round: applied, the Show's winner leads.
challenger = room.current_turn_id()
show = room.apply_show(challenger)
room.resolve_show(show)
check(room.seat_shuffles == 1 and not room.shuffle_pending, "after the Show resolves the shuffle is applied")
check(room.current_turn_id() == show["winner"] or room.is_finished(show["winner"]),
      "the Show's winner leads the fresh round")
check(room.target_rank is None and room.last_play is None and not room.center_pile,
      "it happened at a fresh round: empty pile, no locked rank")

# ---- queued, then everyone passes: applied at the sweep ----
room = make(3)
lead = room.current_turn_id()
room.apply_play(lead, [room.players[lead].hand[0]], "5")
room.request_shuffle()
room.apply_pass(room.current_turn_id())
check(room.shuffle_pending and room.seat_shuffles == 0, "one pass is not a fresh round yet")
room.apply_pass(room.current_turn_id())
check(room.seat_shuffles == 1 and room.current_turn_id() == lead,
      "everyone passed: pile swept, shuffle applied, the last player to play leads")

# ---- cancel ----
room = make()
lead = room.current_turn_id()
room.apply_play(lead, [room.players[lead].hand[0]], "9")
room.request_shuffle()
check(room.request_shuffle() == "cancelled" and not room.shuffle_pending,
      "pressing again while queued cancels it")
room.apply_pass(room.current_turn_id())
check(room.seat_shuffles == 0, "a cancelled shuffle never applies")

# ---- never outside a game; reset on rematch ----
room = make(2)
room.state = STATE_GAME_END
room.game_over = True
check(room.request_shuffle() == "cancelled" and room.seat_shuffles == 0, "no shuffle once the game is over")
room = make()
room.request_shuffle()
room.reset_for_rematch()
check(room.seat_shuffles == 0 and not room.shuffle_pending, "a rematch clears shuffle state")

# ---- without the button, nothing changes ----
room = make()
check(room.turn_order == ["p0", "p1", "p2", "p3", "p4"] and room.seat_shuffles == 0,
      "nobody presses it: join-order seating as before")

# ---- random play with random presses ----
rng = random.Random(5)
bad = []
finished = 0
applied = 0
for game_no in range(120):
    random.seed(game_no)
    n = rng.randint(2, 6)
    room = make(n)
    players = set(room.players)
    for step in range(3000):
        if room.state != STATE_IN_TURN:
            break
        if rng.random() < 0.08:
            room.request_shuffle()
        uid = room.current_turn_id()
        hand = room.players[uid].hand
        roll = rng.random()
        if room.last_play and room.last_play["user_id"] != uid and roll < 0.25:
            room.resolve_show(room.apply_show(uid))
        elif hand and roll < 0.85:
            cap = len(hand) if rng.random() < 0.2 else min(4, len(hand))
            sel = rng.sample(list(hand), rng.randint(1, cap))
            room.apply_play(uid, sel, room.target_rank or rng.choice(["A", "7", "K"]))
        else:
            room.apply_pass(uid)
        if set(room.turn_order) != players:
            bad.append("game %d: seating lost or gained a player" % game_no); break
        if room.state == STATE_IN_TURN and room._out_of_play(room.current_turn_id()):
            bad.append("game %d: the turn sits with a finished player" % game_no); break
        total = sum(len(p.hand) for p in room.players.values()) + len(room.center_pile) + len(room.dead_pile)
        if total != 52:
            bad.append("game %d: cards not conserved (%d)" % (game_no, total)); break
    applied += room.seat_shuffles
    finished += room.state == STATE_GAME_END
check(not bad, "random play with random shuffles: seating, turns and cards stay valid%s"
      % ("" if not bad else " (%s)" % bad[0]))
check(finished == 120, "all 120 games still reach the end (%d)" % finished)
check(applied > 50, "shuffles were really exercised (%d applied)" % applied)

print("\n%d/%d bluff shuffle checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
