import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 table matching: first correct reaction wins, wrong attempts penalise."""
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
    r.begin_play()
    return r

# ---- a non-power discard opens a match window ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), Card(4, "S"), Card(5, "S")]
r.slots["B"] = [Card(6, "D"), Card(3, "H"), Card(9, "C"), Card(10, "C")]
r.draw_pile = [Card(3, "D")]  # A will draw and discard a 3
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH and r.match_card.rank == 3, "discard opens a match window on the 3")
check(r.match_window.discarder == "A", "discarder recorded")
check(r._can_attempt_match("A"), "the discarder may react to their own table discard")

# ---- own-match success closes the window and advances ----
res = r.match_center_own("B", 1)  # B slot1 is a 3
check(res and res["success"] and r.slots["B"][1] is None, "B matches own 3 -> slot emptied")
check(r.phase == PHASE_DRAW and r.current_turn_id() == "B", "window closes, turn advances to B")

# ---- first throw resolves: a WRONG throw takes a penalty AND closes the window ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), None, None]
r.slots["B"] = [Card(6, "D"), Card(9, "H"), None, None]  # 4 slot entries
r.draw_pile = [Card(7, "S"), Card(3, "D")]  # pop -> 3D drawn; penalty pop -> 7S
r.draw("A"); r.discard("A")
res = r.match_center_own("B", 0)  # B slot0 is 6, not 3 -> wrong
check(not res["success"] and r.phase == PHASE_DRAW,
      "wrong throw closes the window (only the first thrower is judged)")
check(len(r.slots["B"]) == 5, "wrong matcher takes a penalty card (5th slot entry appended)")
check(r.slots["B"][0].rank == 6, "wrong selected card stays hidden in its slot")
check(r.react_match("A", [{"owner": "A", "slot": 1}], []) is None,
      "everyone else is too late once the window is resolved")

# ---- pass declines the window without consuming it ----
r = fresh(["A", "B", "C"])
r.slots["B"] = [Card(2, "H"), Card(9, "H"), None, None]
r.slots["C"] = [Card(2, "C"), Card(9, "C"), None, None]
r.draw_pile = [Card(2, "S")]
r.draw("A"); r.discard("A")
check(r.match_decline("B"), "B can pass on the window")
check(not r._can_attempt_match("B"), "after passing, B may no longer throw")
res = r.react_match("C", [{"owner": "C", "slot": 0}], [])
check(res and res["success"], "another player can still take the window after a pass")

# ---- opponent-match success: reactor chooses which own card to transfer ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(2, "S"), Card(3, "S"), Card(4, "S"), None]  # A slot2 = 4
r.slots["B"] = [Card(1, "D"), Card(11, "H"), None, None]         # B highest = J(11) at slot1
r.draw_pile = [Card(4, "D")]  # A draws & discards a 4
r.draw("A"); r.discard("A")
res = r.react_match("B", [{"owner": "A", "slot": 2}], [
    {"target_owner": "A", "target_slot": 2, "from_slot": 0},
])
check(res and res["success"], "B matches A's 4 (opponent match)")
check(r.slots["A"][2] is not None and r.slots["A"][2].rank == 1, "A's slot refilled with B's chosen card")
check(r.slots["B"][0] is None, "B gave away the card they selected")
check(r.phase == PHASE_DRAW, "window closes after a successful opponent match")

# ---- window expiry advances with no match ----
r = fresh(["A", "B"])
r.draw_pile = [Card(2, "S")]
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH, "window open")
r.match_window.deadline = 0  # force expiry
check(r.expire_match_window() and r.phase == PHASE_DRAW, "expired window advances the turn")

# ---- match_window = 0 disables the window entirely ----
r = fresh(["A", "B"], window=0)
r.draw_pile = [Card(2, "S")]
r.draw("A"); r.discard("A")
check(r.phase == PHASE_DRAW and r.current_turn_id() == "B", "window disabled -> discard advances directly")

# ---- the NEXT player's draw closes the window early ----
r = fresh(["A", "B", "C"])
r.draw_pile = [Card(9, "H"), Card(2, "S")]  # A draws/discards the 2; 9H left for B
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH, "window open after A's discard")
check(r.public_round_state()["match"]["next_player"] == "B", "public match state names the next player")
res = r.draw("C")
check(res is None and r.phase == PHASE_MATCH, "a non-next player cannot draw through the window")
res = r.draw("B")
check(res is not None and res["card"].rank == 9, "next player's draw closes the window and draws")
check(r.phase == "decide" and r.drawn_by == "B", "B is now in their decide phase")
check(r.match_window is None and r.match_card is None, "window state fully cleared")

# ---- the NEXT player's Stop also closes the window ----
r = fresh(["A", "B"])
r.first_orbit_complete = True
r.draw_pile = [Card(4, "C"), Card(2, "S")]  # deck must not run dry (that finalizes)
r.draw("A"); r.discard("A")
check(r.phase == PHASE_MATCH, "window open before Stop")
res = r.call_stop("B")
check(res is not None and r.stop_caller == "B", "next player's Stop closes the window and registers")

print("\n%d/%d Super 4 match checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
