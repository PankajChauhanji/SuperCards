import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Podium ordering at game end.

The game-over podium used to show only the round's own participants (built
from round_end's per-round `results`, which drops anyone eliminated in an
earlier round). It should show everyone: the winner first, then evicted
players ordered by how recently they went out, ties within the same round
broken by how far past the score cap they landed.
"""
from game.super_seven.room import Room
from game.super_seven.settings import DEFAULT_SETTINGS

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def make_room():
    room = Room("T1", "A", dict(DEFAULT_SETTINGS))
    for uid in ("A", "B", "C", "D"):
        room.register_player(uid, uid)
    return room


# B is evicted in round 1; C and D both cross the cap in round 2, D by a
# bigger margin than C; A survives as the winner.
room = make_room()
room.round_number = 1
room.players["B"].eliminated = True
room.players["B"].total_score = 105
room.elim_round["B"] = 1

room.round_number = 2
room.players["C"].eliminated = True
room.players["C"].total_score = 101
room.elim_round["C"] = 2

room.players["D"].eliminated = True
room.players["D"].total_score = 140
room.elim_round["D"] = 2

room.players["A"].total_score = 40

order = [r["user_id"] for r in room.standings()]
check(order == ["A", "C", "D", "B"],
      "winner first, most-recently-evicted next, same-round ties by lower "
      "overshoot (got %r)" % order)
check(len(order) == 4, "every player appears, not just the round's own participants")

# ---- round_end_payload carries full standings once the game is over -------
room.turn_order = []
room.game_over = True
room.winner = "A"
payload = room.round_end_payload({"totals": {}})
check(payload["standings"] is not None,
      "round_end_payload carries standings when the game has ended")
check([r["user_id"] for r in payload["standings"]] == order,
      "and they match the full podium order")

mid_game = make_room()
mid_game.turn_order = []
mid_game.game_over = False
mid_payload = mid_game.round_end_payload({"totals": {}})
check(mid_payload["standings"] is None,
      "round_end_payload carries no standings for an ordinary (non-final) round")


print("\n%d/%d standings checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
