import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""End-to-end Phase 0 test: two socket clients run the full lobby flow."""
import time
import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + msg)


# ---- Host client ----
host = socketio.Client()
host_state = {}

@host.on("room_created")
def _rc(data):
    host_state["code"] = data["code"]

@host.on("room_joined")
def _rj(data):
    host_state["joined"] = data

@host.on("player_list")
def _pl(data):
    host_state["players"] = data["players"]
    host_state["host_id"] = data["host_id"]

@host.on("round_start")
def _gs(_):
    host_state["started"] = True

@host.on("error")
def _he(data):
    host_state["error"] = data["message"]


# ---- Joiner client ----
joiner = socketio.Client()
join_state = {}

@joiner.on("join_ok")
def _jok(data):
    join_state["code"] = data["code"]

@joiner.on("room_joined")
def _jrj(data):
    join_state["joined"] = data

@joiner.on("player_list")
def _jpl(data):
    join_state["players"] = data["players"]

@joiner.on("round_start")
def _jgs(_):
    join_state["started"] = True

@joiner.on("error")
def _je(data):
    join_state["error"] = data["message"]


host.connect(BASE)
joiner.connect(BASE)
time.sleep(0.3)

# 1. Host creates a room (settings include a custom max_score).
host.emit("create_room", {"name": "Riya", "user_id": "host-1",
                          "settings": {"max_score": 80, "turn_timer": 30}})
time.sleep(0.4)
log("code" in host_state and len(host_state["code"]) == 4, "host receives 4-letter room code")
code = host_state.get("code")

# 2. Host enters the room (game-page attach).
host.emit("enter_room", {"code": code, "name": "Riya", "user_id": "host-1"})
time.sleep(0.4)
log(host_state.get("joined", {}).get("host_id") == "host-1", "host is marked host on enter")
log(host_state.get("joined", {}).get("settings", {}).get("max_score") == 80,
    "custom setting (max_score=80) preserved")

# 3. Joiner validates+registers, then enters.
joiner.emit("join_room", {"code": code, "name": "Sam", "user_id": "join-2"})
time.sleep(0.4)
log(join_state.get("code") == code, "joiner gets join_ok with the code")
joiner.emit("enter_room", {"code": code, "name": "Sam", "user_id": "join-2"})
time.sleep(0.5)

# 4. Both clients should now see two connected players (rosters sync).
hp = host_state.get("players", [])
jp = join_state.get("players", [])
log(len(hp) == 2, "host sees 2 players in roster")
log(len(jp) == 2, "joiner sees 2 players in roster")
log(all(p["connected"] for p in hp), "all players show connected")

# 5. Non-host cannot start.
joiner.emit("start_game", {"code": code, "user_id": "join-2"})
time.sleep(0.3)
log(join_state.get("error") == "Only the host can start the game.",
    "non-host start is rejected")
log(not host_state.get("started"), "game not started by non-host")

# 6. Host starts -> the round is dealt; both clients receive round_start.
host.emit("start_game", {"code": code, "user_id": "host-1"})
time.sleep(0.4)
log(host_state.get("started") is True, "host receives round_start on game start")
log(join_state.get("started") is True, "joiner receives round_start on game start")

# 7. Joining an unknown room errors cleanly.
joiner.emit("join_room", {"code": "QQQQ", "name": "X", "user_id": "ghost"})
time.sleep(0.3)
log(join_state.get("error") == "No room with that code.", "unknown room code rejected")

host.disconnect()
joiner.disconnect()
time.sleep(0.2)

print("\n%d/%d checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
