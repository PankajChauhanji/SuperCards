import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 Stop: first-orbit gate, final orbit, reveal, scoring outcome."""
from game.core.cards import Card
from game.super_four.room import Room
from game.core.states import STATE_IN_TURN, STATE_ROUND_END
from game.super_four.settings import DEFAULT_SETTINGS

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

def fresh(uids):
    s = dict(DEFAULT_SETTINGS); s["match_window"] = 0  # isolate Stop/turn mechanics
    r = Room("T", uids[0], s)
    for u in uids:
        r.register_player(u, u); r.players[u].connected = True
    r.start_round()
    return r

# ---- Stop is blocked during the first orbit ----
r = fresh(["A", "B"])
check(r.call_stop("A") is None, "cannot call Stop during the first orbit")

# ---- caller strictly lowest -> wins after final orbit ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(1, "S"), Card(2, "S"), None, None]   # total 3
r.slots["B"] = [Card(5, "S"), Card(6, "S"), None, None]   # total 11
r.first_orbit_complete = True
r.turn_index = 0  # A to act
check(r.current_turn_id() == "A", "A on turn")
res = r.call_stop("A")
check(res and r.stop_caller == "A", "A calls Stop")
check(r.state == STATE_IN_TURN and r.current_turn_id() == "B", "B gets one final turn")
# B takes its final turn (discard a non-power card, slots unchanged)
r.draw_pile = [Card(3, "C")]
r.draw("B"); r.discard("B")
check(r.state == STATE_ROUND_END, "round finalizes when play returns to caller")
pay = r.round_end_payload()
check(pay["winner"] == "A" and pay["caller_won"], "A strictly lowest -> caller wins")
check(pay["totals"] == {"A": 3, "B": 11}, "totals computed correctly")
check(len(pay["reveal"]["A"]) == 4 and pay["reveal"]["B"][0]["rank"] == 5,
      "reveal exposes every slot at round end")

# ---- caller NOT lowest -> caught ----
r = fresh(["A", "B"])
r.slots["A"] = [Card(5, "S"), Card(6, "S"), None, None]   # total 11
r.slots["B"] = [Card(1, "S"), Card(2, "S"), None, None]   # total 3
r.first_orbit_complete = True
r.turn_index = 0
r.call_stop("A")
r.draw_pile = [Card(3, "C")]
r.draw("B"); r.discard("B")
pay = r.round_end_payload()
check(pay["winner"] == "B" and not pay["caller_won"], "A not lowest -> caught, B wins")

# ---- cumulative scoring accrues (lower is better) ----
check(r.players["A"].total_score == 11 and r.players["B"].total_score == 3,
      "cumulative totals updated after the round")

# ---- rematch resets ----
r.reset_for_rematch()
check(r.players["A"].total_score == 0 and r.state == "LOBBY", "rematch clears scores and returns to lobby")

print("\n%d/%d Super 4 stop checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
