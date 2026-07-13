import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 3 engine tests: first-orbit gating and round-end scoring (no sockets)."""
from game.super_seven.room import Room, STATE_IN_TURN, STATE_ROUND_END
from game.core.cards import Card
from game.super_seven.rules import infer_action

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

SETTINGS = {"win_discount": 5, "stop_penalty": 40, "max_score": 100, "turn_timer": 40, "timeout_limit": 3}


def make_room(hands, draw_pile=None, safe=()):
    r = Room("TEST", list(hands)[0], SETTINGS)
    for uid in hands:
        r.register_player(uid, uid)
        r.players[uid].connected = True
        r.players[uid].hand = list(hands[uid])
        r.players[uid].is_safe = uid in safe
    r.draw_pile = list(draw_pile or [Card(9, "C")] * 10)
    r.turn_order = list(hands)
    r.turn_index = 0
    r.initial_active = len([u for u in hands if u not in safe])
    r.state = STATE_IN_TURN
    return r


def throw(room, uid, ids):
    mapped_ids = [cid if "#" in cid else f"{cid}#0" for cid in ids]
    cards = room.card_objects(uid, mapped_ids)
    action = infer_action([c.rank for c in cards], room.center_rank_set())
    return room.apply_throw(uid, cards, action)


# ---- first orbit gating ----
r = make_room({
    "A": [Card(9, "C"), Card(2, "H")],
    "B": [Card(9, "S"), Card(2, "S")],
})
check(not r.first_orbit_complete, "first orbit incomplete at round start")
throw(r, "A", ["9C"]); r.draw_one("A")           # A's turn done
check(not r.first_orbit_complete, "still incomplete after only A has played")
throw(r, "B", ["2S"]); r.draw_one("B")           # B's turn done
check(r.first_orbit_complete, "first orbit complete after every player has had a turn")
check(r.current_turn_id() == "A", "turn returns to A after the first orbit")

# ---- end_round: caller wins ----
r = make_room({
    "A": [Card(5, "S"), Card(3, "H")],   # 8 (caller, lowest)
    "B": [Card(10, "S"), Card(2, "H")],  # 12
})
res = r.end_round("A")
check(r.state == STATE_ROUND_END, "end_round moves to ROUND_END")
check(not res["caught"], "lowest caller wins")
check(r.players["A"].round_score == 3, "winner round score is 8-5=3")
check(r.players["A"].total_score == 3, "winner total accumulates")
check(r.players["B"].round_score == 12 and r.players["B"].total_score == 12, "loser scores hand")

# ---- end_round: caught ----
r = make_room({
    "A": [Card(10, "S")],   # 10 (caller)
    "B": [Card(4, "S")],    # 4 (lower -> catches)
})
res = r.end_round("A")
check(res["caught"], "caller is caught when someone is lower")
check(r.players["A"].round_score == 50, "caught caller scores 10+40")

# ---- Stop called with safe players present (ignored in comparison) ----
r = make_room({
    "A": [Card(2, "S")],   # caller, total 2
    "B": [],               # safe at 0
}, safe={"B"})
res = r.end_round("A")
check(not res["caught"], "caller wins when they are the only non-safe player left")
check(r.players["A"].round_score == 0, "winner scores 0 (total 2 - discount 5 floors at 0)")
check(r.players["B"].round_score == 0, "safe player scores 0")

# ---- auto-end when everyone is safe ----
r = make_room({"A": [], "B": []}, safe={"A", "B"})
check(r.active_count() == 0, "no active players when all are safe")
res = r.end_round(None)
check(r.players["A"].round_score == 0 and r.players["B"].round_score == 0, "auto-end scores all 0")

print("\n%d/%d engine checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
