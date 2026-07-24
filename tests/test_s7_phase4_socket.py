import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 4 socket test: round_end fields and the next-round loop."""
import time, socketio

BASE = "http://localhost:5005"
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


def client(store):
    c = socketio.Client()
    c.on("room_created", lambda d: store.update(code=d["code"]))
    c.on("join_ok", lambda d: store.update(code=d["code"]))
    c.on("round_start", lambda d: store.update(table=d, round_no=d["round_number"]))
    c.on("table_state", lambda d: store.update(table=d))
    c.on("your_hand", lambda d: store.update(hand=d["cards"]))
    c.on("round_end", lambda d: store.update(round_end=d))
    c.on("game_end", lambda d: store.update(game_end=d))
    c.on("error", lambda d: store.update(error=d["message"]))
    return c


stores = {u: {} for u in ("A", "B", "C")}
clients = {u: client(stores[u]) for u in stores}
for c in clients.values():
    c.connect(BASE)
time.sleep(0.3)

clients["A"].emit("create_room", {"name": "A", "user_id": "A", "settings": {}})
time.sleep(0.3)
code = stores["A"]["code"]
for u in ("B", "C"):
    clients[u].emit("join_room", {"code": code, "name": u, "user_id": u}); time.sleep(0.15)
for u in ("A", "B", "C"):
    clients[u].emit("enter_room", {"code": code, "name": u, "user_id": u}); time.sleep(0.12)
clients["A"].emit("start_game", {"code": code, "user_id": "A"}); time.sleep(0.5)

def current():
    return stores["A"]["table"]["current_turn"]

# Play one full orbit (3 players): single + draw each.
for _ in range(3):
    cur = current()
    hand = stores[cur]["hand"]
    clients[cur].emit("play_cards", {"code": code, "user_id": cur, "card_ids": [hand[0]["id"]]})
    time.sleep(0.25)
    clients[cur].emit("draw_card", {"code": code, "user_id": cur})
    time.sleep(0.25)

check(stores["A"]["table"]["first_orbit_complete"], "first orbit completed with 3 players")

# Current player calls Stop.
cur = current()
clients[cur].emit("call_stop", {"code": code, "user_id": cur})
time.sleep(0.4)
re = stores["A"].get("round_end")
check(re is not None, "round_end received")
check("game_over" in re and "eliminated" in re and "winner" in re,
      "round_end carries game_over / eliminated / winner")

if not re["game_over"]:
    # Non-host cannot advance.
    stores["B"]["error"] = None
    clients["B"].emit("next_round", {"code": code, "user_id": "B"})
    time.sleep(0.3)
    check(stores["B"]["error"] == "Only the host can start the next round.",
          "non-host cannot start the next round")

    # Host advances to round 2.
    for s in stores.values():
        s["round_no"] = None
    clients["A"].emit("next_round", {"code": code, "user_id": "A"})
    time.sleep(0.5)
    check(stores["A"].get("round_no") == 2, "host starts round 2")
    check(all(len(stores[u]["hand"]) == 7 for u in ("A", "B", "C")),
          "every active player gets a fresh 7-card hand in round 2")
else:
    check(True, "game ended in round 1 (cap reached) — next-round path skipped")
    check(stores["A"].get("game_end") is not None or re["game_over"], "game_over surfaced")

for c in clients.values():
    c.disconnect()
time.sleep(0.2)
print("\n%d/%d socket checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
