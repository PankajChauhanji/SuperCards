import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 room: deal/preview, knowledge model, draw/keep/discard/match-own, no leaks."""
from game.core.cards import Card
from game.super_four.room import Room, PHASE_DRAW, PHASE_DECIDE, PHASE_POWER, PHASE_PREVIEW
from game.super_four.settings import DEFAULT_SETTINGS, SLOTS

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

def fresh(uids, begin=True):
    # match_window=0 so discards advance directly (turn mechanics under test here;
    # the cross-player match window has its own suite, test_s4_match.py).
    s = dict(DEFAULT_SETTINGS); s["match_window"] = 0
    r = Room("T", uids[0], s)
    for u in uids:
        r.register_player(u, u); r.players[u].connected = True
    r.start_round()
    if begin:
        r.begin_play()
    return r

# ---- deal + preview + knowledge ----
r = fresh(["A", "B"], begin=False)
check(len(r.slots["A"]) == SLOTS and len(r.slots["B"]) == SLOTS, "each player dealt 4 slots")
check(len(r.draw_pile) == 52 - 8, "draw pile = 52 - 8 after deal")
check(r.current_turn_id() == "A" and r.phase == PHASE_PREVIEW, "round begins in the private preview phase")

pa = r.private_view("A")
check(len(pa["known"]) == 2 and all(k["owner"] == "A" for k in pa["known"]),
      "A previews exactly their own two cards")
check({k["slot"] for k in pa["known"]} == {0, 1}, "A previews slots 0 and 1")
pb = r.private_view("B")
check(all(k["owner"] != "A" for k in pb["known"]),
      "LEAK CHECK: B never sees any of A's cards at deal")
check(r.begin_play() and r.phase == PHASE_DRAW, "host ends preview and starts the first turn")
check(r.private_view("A")["known"] == [], "LEAK CHECK: preview faces are not resent after play begins")

# ---- draw is private to the active player ----
r = fresh(["A", "B"])
r.draw_pile = [Card(5, "S")]
res = r.draw("A")
check(res and res["card"].rank == 5 and r.phase == PHASE_DECIDE, "A draws 5S -> decide phase")
check(r.public_round_state()["drawn"] is None, "drawn card is absent from public round state")
check(r.private_view("A")["drawn"]["rank"] == 5 and r.private_view("B")["drawn"] is None,
      "LEAK CHECK: only drawer receives the drawn face")
check(r.draw("B") is None, "B cannot draw out of turn / phase")

# ---- keep: swap into slot, old to center, replacement remains hidden ----
r = fresh(["A", "B"])
old = r.slots["A"][2]
r.draw_pile = [Card(9, "S")]  # rank 9 but kept -> no power
r.draw("A")
ok = r.keep("A", 2)
check(ok and r.slots["A"][2].rank == 9, "kept card now in slot 2")
check(r.center is old, "old slot-2 card moved to center")
check(r.current_turn_id() == "B" and r.phase == PHASE_DRAW, "turn advanced to B after keep")
check(not any(k["owner"] == "A" and k["slot"] == 2 for k in r.private_view("B")["known"]),
      "LEAK CHECK: B does not learn A's kept card")

# ---- discard non-power advances; discard power enters power phase ----
r = fresh(["A", "B"])
r.draw_pile = [Card(3, "S")]
r.draw("A"); out = r.discard("A")
check(out["power_rank"] is None and r.center.rank == 3, "discarded 3 -> center, no power")
check(r.current_turn_id() == "B" and r.phase == PHASE_DRAW, "turn advanced after plain discard")

r = fresh(["A", "B"])
r.draw_pile = [Card(9, "S")]
r.draw("A"); out = r.discard("A")
check(out["power_rank"] == 9 and r.phase == PHASE_POWER, "discarded 9 -> power phase")
check(r.pending_power == {"by": "A", "rank": 9}, "pending_power recorded")
check(r.current_turn_id() == "A", "turn does NOT advance while a power is pending")

# ---- match own: success empties the slot ----
r = fresh(["A", "B"])
r.slots["A"][0] = Card(6, "D")
r.draw_pile = [Card(6, "S")]
r.draw("A"); m = r.match_own("A", 0)
check(m["success"] and r.slots["A"][0] is None, "correct own-match empties slot 0")
check(r.current_turn_id() == "B", "turn advances after successful own-match")

# ---- match own: failure stays hidden + penalty ----
r = fresh(["A", "B"])
r.slots["A"][1] = Card(8, "D")
r.draw_pile = [Card(2, "S"), Card(4, "C")]  # draw 4C (top=pop last)... set order
r.draw_pile = [Card(4, "C"), Card(2, "S")]  # pop() -> 2S drawn; penalty pops 4C
r.draw("A"); m = r.match_own("A", 1)
check(not m["success"], "wrong own-match reported as failure")
check(r.slots["A"][1] is not None and r.slots["A"][1].rank == 8, "wrong-matched card returned to slot")
check(len(r.slots["A"]) == SLOTS + 1, "penalty card appended (slot count grows)")
check(not any(k["owner"] == "A" and k["slot"] == 1 for k in r.private_view("B")["known"]),
      "LEAK CHECK: failed match does not reveal that card")
check(r.current_turn_id() == "B", "turn advances after failed own-match")

# ---- public state never carries hidden faces ----
r = fresh(["A", "B"])
ps = r.public_round_state()
check(all(isinstance(p["slots"], list) and all(isinstance(x, bool) for x in p["slots"])
          for p in ps["players"]),
      "public players expose slot occupancy as booleans only (no faces)")

# ---- timeout strikes: at the limit a player is benched to spectator ----
r = fresh(["A", "B", "C"])
r.settings["timeout_limit"] = 2
cur = r.current_turn_id()
info = r.timeout_strike(cur)
check(not info["removed"] and info["timeout_count"] == 1 and not r.players[cur].is_spectator,
      "first missed turn only counts a strike")
cards_before = len(r.draw_pile) + len(r.discard_pile)
held = sum(1 for c in r.slots[cur] if c is not None)
info = r.timeout_strike(cur)
check(info["removed"] and r.players[cur].is_spectator,
      "second missed turn benches the player to spectator")
check(cur not in r.turn_order and r.slots[cur] == [],
      "benched player leaves the rotation and their cards leave play")
check(len(r.draw_pile) + len(r.discard_pile) == cards_before + held,
      "benched player's cards go back to the pile (nothing lost)")
check(r.state == "IN_TURN" and r.current_turn_id() in r.turn_order and r.phase == PHASE_DRAW,
      "round continues with the next player on turn")
check(all(o != cur for ks in r.known.values() for (o, _s) in ks),
      "all knowledge about the benched player's positions is dropped")

# benched player can be admitted back like any spectator (clean slate)
p = r.players[cur]
p.pending_join = True
survivors = list(r.turn_order)
r.slots[survivors[0]] = [Card(1, "S"), None, None, None]
r.slots[survivors[1]] = [Card(9, "S"), None, None, None]
r.first_orbit_complete = True
r.turn_index = 0
r.call_stop(survivors[0])
r.draw_pile.append(Card(3, "C"))
r.draw(survivors[1]); r.discard(survivors[1])   # final orbit ends -> finalize
check(not p.is_spectator and p.timeout_count == 0,
      "admitted-back player becomes active at round end with a clean timeout slate")

# with 2 players, benching one finalizes the round immediately
r = fresh(["A", "B"])
r.settings["timeout_limit"] = 1
info = r.timeout_strike(r.current_turn_id())
check(info["removed"] and r.state in ("ROUND_END", "GAME_END"),
      "benching the second-to-last player ends the round")

# a Stop caller is never benched mid-final-orbit
r = fresh(["A", "B", "C"])
r.settings["timeout_limit"] = 1
r.first_orbit_complete = True
caller = r.current_turn_id()
r.call_stop(caller)
info = r.timeout_strike(caller)
check(not info["removed"] and not r.players[caller].is_spectator,
      "the Stop caller cannot be benched by strikes")

print("\n%d/%d Super 4 room checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
