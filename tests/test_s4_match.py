import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 cross-player matching: window open/close, own/opp match, penalties, expiry."""
from game.core.cards import Card
from game.super_four.room import Room, PHASE_MATCH, PHASE_DRAW
from game.super_four.settings import DEFAULT_SETTINGS

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

def fresh(uids, window=5):
    s = dict(DEFAULT_SETTINGS); s["match_window"] = window
    r = Room("T", uids[0], s)
    for u in uids:
        r.register_player(u, u); r.players[u].connected = True
    r.start_round()
    return r

# ---- a non-power discard opens a match window ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), Card(4, "S"), Card(5, "S")]
r.slots["B"] = [Card(6, "D"), Card(3, "H"), Card(9, "C"), Card(10, "C")]
r.draw_pile = [Card(3, "D")]  # A will draw and discard a 3
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH and r.match_card.rank == 3, "discard opens a match window on the 3")
check(r.match_discarder == "A", "discarder recorded")
check(r.match_center_own("A", 1) is None, "the discarder cannot match their own discard")

# ---- own-match success closes the window and advances ----
res = r.match_center_own("B", 1)  # B slot1 is a 3
check(res and res["success"] and r.slots["B"][1] is None, "B matches own 3 -> slot emptied")
check(r.phase == PHASE_DRAW and r.current_turn_id() == "B", "window closes, turn advances to B")

# ---- own-match failure: penalty + reveal, window stays open ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), None, None]
r.slots["B"] = [Card(6, "D"), Card(9, "H"), None, None]  # 4 slot entries
r.draw_pile = [Card(7, "S"), Card(3, "D")]  # pop -> 3D drawn; penalty pop -> 7S
r.draw("A"); r.discard("A")
res = r.match_center_own("B", 0)  # B slot0 is 6, not 3 -> wrong
check(not res["success"] and r.phase == PHASE_MATCH, "wrong match keeps window open")
check(len(r.slots["B"]) == 5, "wrong matcher takes a penalty card (5th slot entry appended)")
check("B" in r.match_attempted and r.match_center_own("B", 1) is None, "one attempt per player per window")

# ---- opponent-match success: their card removed, you give your highest ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), Card(4, "S"), None]  # A slot2 = 4
r.slots["B"] = [Card(1, "D"), Card(11, "H"), None, None]         # B highest = J(11) at slot1
r.draw_pile = [Card(4, "D")]  # A draws & discards a 4
r.draw("A"); r.discard("A")
res = r.match_center_opp("B", "A", 2)  # match A's slot2 (a 4)
check(res and res["success"], "B matches A's 4 (opponent match)")
check(r.slots["A"][2] is not None and r.slots["A"][2].rank == 11, "A's slot refilled with B's given (highest) card")
check(r.slots["B"][1] is None, "B gave away their highest card (slot emptied)")
check(r.phase == PHASE_DRAW, "window closes after a successful opponent match")

# ---- window expiry advances with no match ----
r = fresh(["A", "B"])
r.draw_pile = [Card(2, "S")]
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH, "window open")
r.match_deadline = 0  # force expiry
check(r.expire_match_window() and r.phase == PHASE_DRAW, "expired window advances the turn")

# ---- match_window = 0 disables the window entirely ----
r = fresh(["A", "B"], window=0)
r.draw_pile = [Card(2, "S")]
r.draw("A"); r.discard("A")
check(r.phase == PHASE_DRAW and r.current_turn_id() == "B", "window disabled -> discard advances directly")

print("\n%d/%d Super 4 match checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
