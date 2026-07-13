import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game.super_seven.room import Room, STATE_IN_TURN, PICK_SECONDS
from game.core.cards import Card
from sockets import director

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

SETTINGS = {"win_discount": 5, "stop_penalty": 40, "max_score": 100, "turn_timer": 40, "timeout_limit": 3}

def fresh(uids):
    r = Room("T", uids[0], dict(SETTINGS))
    for u in uids:
        r.register_player(u, u); r.players[u].connected = True
    return r

# ---- pick timer: stamped on a discard, cleared by the draw ----
r = fresh(["A", "B"]); r.start_round()
cur = r.current_turn_id()
r.players[cur].hand = [Card(7, "S"), Card(9, "H")]
r.apply_throw(cur, [Card(7, "S")], "single")
check(r.awaiting_draw and r.awaiting_draw_ts > 0, "discard starts the pick timer")
check(r.pick_seconds_left() is not None and r.pick_seconds_left() <= PICK_SECONDS, "pick seconds reported")
check(not r.pick_timed_out(), "pick not timed out immediately")
r.awaiting_draw_ts = time.time() - (PICK_SECONDS + 1)
check(r.pick_timed_out(), "pick times out after the grace period")

# ---- director auto-picks WITHOUT a penalty (no timeout increment) ----
class FakeSock:
    def __init__(self): self.emits = []
    def emit(self, ev, data=None, to=None): self.emits.append((ev, data, to))
class FakeMgr:
    def __init__(self, rooms): self.rooms = rooms

r = fresh(["A", "B"]); r.start_round()
cur = r.current_turn_id()
r.players[cur].hand = [Card(7, "S"), Card(9, "H")]
r.draw_pile = [Card(3, "C")]
tc_before = r.players[cur].timeout_count
r.apply_throw(cur, [Card(7, "S")], "single")   # owes a draw
r.awaiting_draw_ts = time.time() - (PICK_SECONDS + 1)  # pick expired
fs = FakeSock()
director._tick(fs, FakeMgr({"T": r}))
evs = [e[0] for e in fs.emits]
check("auto_picked" in evs, "director emits auto_picked when the pick timer expires")
check(not r.awaiting_draw, "auto-pick clears the owed draw")
check(r.players[cur].timeout_count == tc_before, "auto-pick does NOT count as a timeout (no penalty)")
check(r.current_turn_id() != cur, "turn advances after the auto-pick")

# ---- turn timer does NOT fire while a draw is owed (pick timer governs) ----
r = fresh(["A", "B"]); r.start_round()
cur = r.current_turn_id()
r.players[cur].hand = [Card(7, "S"), Card(9, "H")]
r.draw_pile = [Card(3, "C")]
r.apply_throw(cur, [Card(7, "S")], "single")     # awaiting draw
r.turn_start_ts = time.time() - 999               # turn clock long expired
r.awaiting_draw_ts = time.time()                  # but pick timer fresh
fs = FakeSock()
director._tick(fs, FakeMgr({"T": r}))
evs = [e[0] for e in fs.emits]
check("player_timed_out" not in evs, "no penalised timeout while a draw is owed")
check(r.players[cur].timeout_count == 0, "no timeout counted while awaiting draw")

print("\n%d/%d Batch-1 engine checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
