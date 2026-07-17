import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 powers: peek own/opp, blind swap, king look+swap; knowledge correctness."""
from game.core.cards import Card
from game.super_four.room import Room, PHASE_POWER, PHASE_DRAW
from game.super_four.settings import DEFAULT_SETTINGS

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

def fresh(uids):
    s = dict(DEFAULT_SETTINGS); s["match_window"] = 0  # isolate power/turn mechanics
    r = Room("T", uids[0], s)
    for u in uids:
        r.register_player(u, u); r.players[u].connected = True
    r.start_round()
    r.begin_play()
    # deterministic slots
    r.slots["A"] = [Card(2, "S"), Card(3, "S"), Card(4, "S"), Card(5, "S")]
    r.slots["B"] = [Card(9, "D"), Card(10, "D"), Card(11, "D"), Card(12, "D")]
    r.known = {"A": set(), "B": set()}
    return r

def knows(r, viewer, owner, slot):
    return (owner, slot) in r.known.get(viewer, set())

# ---- 7/8 peek own ----
r = fresh(["A", "B"])
r.draw_pile = [Card(7, "C")]
r.draw("A"); r.discard("A")
res = r.power_peek_own("A", 3)
check(res and res["peeked"]["card"]["rank"] == 5, "peek own returns the card (5S) privately")
check(knows(r, "A", "A", 3), "A now knows their slot 3")
check(not knows(r, "B", "A", 3), "LEAK CHECK: B does not learn A's peeked card")
check(r.current_turn_id() == "B" and r.phase == PHASE_DRAW, "turn ends after power")

# ---- 9/10 peek opp ----
r = fresh(["A", "B"])
r.draw_pile = [Card(9, "C")]
r.draw("A"); r.discard("A")
res = r.power_peek_opp("A", "B", 2)
check(res and res["peeked"]["card"]["rank"] == 11, "peek opp returns B's slot 2 (11D)")
check(knows(r, "A", "B", 2), "A now knows B's slot 2")
check(not knows(r, "B", "B", 2), "B still doesn't know their own slot 2 (only A peeked)")

# ---- 11/12 blind swap: no reveal, knowledge follows cards ----
r = fresh(["A", "B"])
r.known = {"A": {("A", 0)}, "B": set()}   # A knows its slot 0 (the 2S)
r.draw_pile = [Card(11, "C")]
r.draw("A"); r.discard("A")
res = r.power_blind_swap("A", 0, "B", 0)
check(res is not None, "blind swap resolves")
check(r.slots["A"][0].rank == 9 and r.slots["B"][0].rank == 2, "cards swapped between A0 and B0")
check(not knows(r, "A", "A", 0), "A no longer knows its slot 0 (new unknown card arrived)")
check(knows(r, "A", "B", 0), "A's knowledge of the 2S moved with it to B0")
check(not knows(r, "A", "B", 0) is False, "sanity")
check(not knows(r, "B", "B", 0) and not knows(r, "B", "A", 0),
      "LEAK CHECK: blind swap reveals nothing to B")

# ---- 13 King: look both (private) then swap ----
r = fresh(["A", "B"])
r.draw_pile = [Card(13, "S")]  # King of Spades (13, no -1 here; just the power)
r.draw("A"); r.discard("A")
look = r.power_king_look("A", 1, "B", 3)
check(look and len(look["looked"]) == 2, "king look returns both cards")
check(knows(r, "A", "A", 1) and knows(r, "A", "B", 3), "A learns both looked positions")
check(r.phase == PHASE_POWER, "still in power phase awaiting king decision")
dec = r.power_king_decide("A", True)
check(dec and dec["swapped"], "king decides to swap")
check(r.slots["A"][1].rank == 12 and r.slots["B"][3].rank == 3, "king swap applied (A1<->B3)")
check(knows(r, "A", "A", 1) and knows(r, "A", "B", 3), "A still knows both after swap")
check(r.current_turn_id() == "B" and r.phase == PHASE_DRAW, "turn ends after king")

# ---- king: choose NOT to swap ----
r = fresh(["A", "B"])
r.draw_pile = [Card(13, "C")]
r.draw("A"); r.discard("A")
r.power_king_look("A", 0, "B", 0)
before_a, before_b = r.slots["A"][0].rank, r.slots["B"][0].rank
r.power_king_decide("A", False)
check(r.slots["A"][0].rank == before_a and r.slots["B"][0].rank == before_b,
      "king no-swap leaves cards in place")

# ---- power validation: wrong actor / wrong kind rejected ----
r = fresh(["A", "B"])
r.draw_pile = [Card(7, "C")]
r.draw("A"); r.discard("A")
check(r.power_peek_own("B", 0) is None, "opponent cannot resolve A's power")
check(r.power_peek_opp("A", "B", 0) is None, "wrong power kind (peek_opp on a 7) rejected")

# ---- swap powers need one of YOUR OWN cards too (empty-hand freeze regression) ----
r = fresh(["A", "B"])
r.slots["A"] = [None, None, None, None]      # A matched everything away
r.draw_pile = [Card(11, "C")]                # Jack -> blind swap
r.draw("A")
res = r.discard("A")
check(res is not None and res["power_rank"] is None and r.phase == PHASE_DRAW,
      "J discarded with no own cards -> no power phase, turn advances (no freeze)")

r = fresh(["A", "B"])
r.slots["A"] = [None, None, None, None]
r.draw_pile = [Card(13, "C")]                # King
r.draw("A")
res = r.discard("A")
check(res is not None and res["power_rank"] is None and r.phase == PHASE_DRAW,
      "King discarded with no own cards -> no power phase (no freeze)")

r = fresh(["A", "B"])
r.slots["A"] = [None, None, None, None]
r.draw_pile = [Card(9, "C")]                 # 9 -> peek opponent, still fine with empty hand
r.draw("A")
res = r.discard("A")
check(res is not None and res["power_rank"] == 9,
      "peek-opponent power still fires with an empty own hand")

# ---- powers are optional: the actor may skip instead of using one ----
r = fresh(["A", "B"])
r.draw_pile = [Card(11, "C")]                # Jack -> blind swap pending
r.draw("A"); r.discard("A")
check(r.phase == PHASE_POWER, "J discard opens the power phase")
check(not r.power_skip("B"), "only the acting player may skip the power")
check(r.power_skip("A"), "actor skips the swap voluntarily")
check(r.phase == PHASE_DRAW and r.current_turn_id() == "B",
      "skip ends the power phase and the turn advances")
check(r.slots["A"][0] is not None and r.slots["A"][0].rank == 2,
      "no swap happened — slots untouched after skip")

r = fresh(["A", "B"])
r.draw_pile = [Card(13, "C")]                # King is skippable too
r.draw("A"); r.discard("A")
check(r.power_skip("A") and r.phase == PHASE_DRAW, "King power skipped without looking")

print("\n%d/%d Super 4 power checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
