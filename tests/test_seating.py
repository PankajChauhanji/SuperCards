import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Shuffle seats: the shared helper, and every game dealing in the shuffled order.

The feature rests on one fact about the codebase — each variant builds its turn
order from ``room.players`` in insertion order — so this file pins that fact for
all four games. If a future variant derived its order some other way, the host's
checkbox would silently do nothing for it; this is where that would show up.
"""
import random

from game.core import registry, seating

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


def make(game_type, n=5):
    spec = registry.get(game_type)
    room = spec.room_class("SEAT", "p0", dict(spec.default_settings))
    room.game_type = game_type
    for i in range(n):
        room.register_player("p%d" % i, "P%d" % i).connected = True
    return room


# ---- the helper itself ----
room = make("super_seven")
before = dict(room.players)
ids_before = list(room.players)
order = seating.shuffle_seats(room, random.Random(4))
check(set(room.players) == set(ids_before) and all(room.players[u] is before[u] for u in before),
      "shuffling keeps exactly the same Player objects")
check([p["user_id"] for p in order] == list(room.players),
      "the returned public order is the room's new order")
check(all(set(p) == {"user_id", "name"} for p in order), "the public order carries names and ids only")
colors = {u: p.color_index for u, p in room.players.items()}
check(colors == {u: p.color_index for u, p in before.items()}, "player colours do not change")
roster = room.players
seating.shuffle_seats(room)
check(room.players is roster, "the roster dict is reordered in place, not replaced")

seen = set()
for seed in range(40):
    r = make("bluff")
    seating.shuffle_seats(r, random.Random(seed))
    seen.add(tuple(r.players))
check(len(seen) > 20, "shuffles actually vary (%d distinct orders in 40)" % len(seen))

r = make("super_seven")
r.players["p2"].is_spectator = True
r.players["p3"].eliminated = True
check([p["user_id"] for p in seating.public_order(r)] == ["p0", "p1", "p4"],
      "the public order lists only players at the table")

# ---- every game deals its turn order in the shuffled seating ----
for game_type in ("super_seven", "bluff", "super_four", "poker"):
    room = make(game_type)
    seating.shuffle_seats(room, random.Random(11))
    shuffled = list(room.players)
    room.start_round()
    if game_type == "poker":
        order = room.seats
    else:
        order = room.turn_order
    check(order == shuffled,
          "[%s] the dealt order follows the shuffled seating" % game_type)

# Between rounds (Super Seven's round-summary option): the next deal uses it too.
room = make("super_seven")
room.start_round()
first = list(room.turn_order)
room.state = "ROUND_END"
seating.shuffle_seats(room, random.Random(99))
room.start_round()
check(room.turn_order == list(room.players) and set(room.turn_order) == set(first),
      "[super_seven] a shuffle between rounds re-seats the next round")

# Unticked, nothing changes: seating stays in join order.
room = make("bluff")
room.start_round()
check(room.turn_order == ["p0", "p1", "p2", "p3", "p4"], "without a shuffle, seating is join order as before")

print("\n%d/%d seating checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
