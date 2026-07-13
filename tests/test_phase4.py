import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 4 engine + director tests (no sockets)."""
import time
from game.super_seven.room import Room, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.core.cards import Card
from sockets import director

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

SETTINGS = {"win_discount": 5, "stop_penalty": 40, "max_score": 100, "turn_timer": 40, "timeout_limit": 3}


def fresh_room(uids):
    r = Room("T", uids[0], dict(SETTINGS))
    for u in uids:
        r.register_player(u, u)
        r.players[u].connected = True
    return r


# ---- starting drawer rotates each round ----
r = fresh_room(["A", "B", "C"])
r.start_round()
first1 = r.current_turn_id()
# Force the round to end and start another.
r.end_round(None)
r.start_round()
first2 = r.current_turn_id()
check(first1 == "A", "round 1 leads off with the first player")
check(first2 == "B", "round 2 rotates the starting drawer")

# ---- elimination at the cap + winner ----
r = fresh_room(["A", "B"])
r.start_round()
r.players["A"].hand = [Card(2, "S")]      # 2
r.players["B"].hand = [Card(13, "S"), Card(13, "H")]  # 26
r.players["A"].total_score = 0
r.players["B"].total_score = 90
r.turn_order = ["A", "B"]
res = r.end_round("A")               # A calls, A lowest -> A wins (2-5 -> 0); B +26 -> 116
check(r.players["B"].eliminated, "player crossing the cap is eliminated")
check(r.game_over and r.winner == "A", "game ends with the survivor as winner")
check(r.state == STATE_GAME_END, "state becomes GAME_END")

# ---- survivor tiebreaker: everyone crosses in the same round ----
r = fresh_room(["A", "B"])
r.start_round()
r.turn_order = ["A", "B"]
r.players["A"].total_score = 98
r.players["B"].total_score = 99
r.players["A"].hand = [Card(5, "S")]   # +5 -> 103
r.players["B"].hand = [Card(5, "H")]   # +5 -> 104 (but caught logic aside, both cross)
res = r.end_round(None)                # auto-end, both add hand totals
check(r.players["A"].total_score >= 100 and r.players["B"].total_score >= 100, "both crossed the cap")
check(r.winner == "A" and r.players["A"].eliminated is False, "lowest total survives as winner")
check(r.players["B"].eliminated, "the higher total is eliminated")

# ---- force_timeout: auto-discard highest + draw ----
r = fresh_room(["A", "B"])
r.start_round()
r.players["A"].hand = [Card(3, "S"), Card(13, "H"), Card(7, "D")]
r.draw_pile = [Card(9, "C")]
r.turn_order = ["A", "B"]; r.turn_index = 0; r.state = STATE_IN_TURN
info = r.force_timeout("A")
check(info["timeout_count"] == 1 and not info["removed"], "first timeout counts, no removal")
check(Card(13, "H").id not in {c.id for c in r.players["A"].hand}, "auto-discard dropped the highest card (K)")
check(r.current_turn_id() == "B", "turn advanced after auto-play")

# ---- force_timeout: removal on the limit, ends game if one remains ----
r = fresh_room(["A", "B"])
r.start_round()
r.turn_order = ["A", "B"]; r.turn_index = 0
r.players["A"].timeout_count = 2          # next timeout is the third
r.players["A"].hand = [Card(4, "S")]
r.draw_pile = [Card(9, "C")]
info = r.force_timeout("A")
check(info["removed"] and r.players["A"].eliminated, "hitting the limit removes the player")
check(r.game_over and r.winner == "B", "removal leaving one player ends the game")

# ---- is_timed_out / turn_seconds_left ----
r = fresh_room(["A", "B"])
r.start_round()
check(r.turn_seconds_left() is not None and r.turn_seconds_left() <= 40, "seconds-left is reported in play")
r.turn_start_ts = time.time() - 100
check(r.is_timed_out(), "a stale turn is detected as timed out")

# ---- director tick drives a timeout and broadcasts ----
class FakeSock:
    def __init__(self): self.emits = []
    def emit(self, event, data=None, to=None): self.emits.append((event, data, to))

class FakeMgr:
    def __init__(self, rooms): self.rooms = rooms

r = fresh_room(["A", "B"])
r.start_round()
r.players[r.current_turn_id()].hand = [Card(6, "S"), Card(2, "H")]
r.draw_pile = [Card(9, "C")]
r.turn_start_ts = time.time() - 100        # already expired
fs = FakeSock()
director._tick(fs, FakeMgr({"T": r}))
events = [e[0] for e in fs.emits]
check("player_timed_out" in events, "director emits player_timed_out on expiry")
check("table_state" in events, "director broadcasts the new table state")

print("\n%d/%d Phase 4 checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
