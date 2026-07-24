import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 3 socket test: Stop gating and round-end over the wire."""
import time, socketio

BASE = "http://localhost:5005"
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


def client(store):
    c = socketio.Client()
    c.on("room_created", lambda d: store.update(code=d["code"]))
    c.on("join_ok", lambda d: store.update(code=d["code"]))
    c.on("round_start", lambda d: store.update(table=d))
    c.on("table_state", lambda d: store.update(table=d))
    c.on("your_hand", lambda d: store.update(hand=d["cards"]))
    c.on("round_end", lambda d: store.update(round_end=d))
    c.on("error", lambda d: store.update(error=d["message"]))
    return c


A, B = {}, {}
ca, cb = client(A), client(B)
ca.connect(BASE); cb.connect(BASE); time.sleep(0.3)
ca.emit("create_room", {"name": "A", "user_id": "A", "settings": {}}); time.sleep(0.3)
code = A["code"]
cb.emit("join_room", {"code": code, "name": "B", "user_id": "B"}); time.sleep(0.2)
ca.emit("enter_room", {"code": code, "name": "A", "user_id": "A"}); time.sleep(0.1)
cb.emit("enter_room", {"code": code, "name": "B", "user_id": "B"}); time.sleep(0.2)
ca.emit("start_game", {"code": code, "user_id": "A"}); time.sleep(0.5)

stores = {"A": A, "B": B}
clients = {"A": ca, "B": cb}

def current():
    return A["table"]["current_turn"]

# Stop during the first orbit is rejected.
cur = current()
stores[cur]["error"] = None
clients[cur].emit("call_stop", {"code": code, "user_id": cur})
time.sleep(0.3)
check(stores[cur]["error"] == "Stop can't be called during the first orbit.",
      "Stop is blocked during the first orbit")
check("round_end" not in A, "no round ended during first orbit")

# Play one full orbit: each player does a single discard + draw.
for _ in range(2):
    cur = current()
    hand = stores[cur]["hand"]
    clients[cur].emit("play_cards", {"code": code, "user_id": cur, "card_ids": [hand[0]["id"]]})
    time.sleep(0.3)
    clients[cur].emit("draw_card", {"code": code, "user_id": cur})
    time.sleep(0.3)

check(A["table"]["first_orbit_complete"] is True, "first orbit completes after both players act")

# Now the current player calls Stop successfully.
cur = current()
clients[cur].emit("call_stop", {"code": code, "user_id": cur})
time.sleep(0.4)
re = A.get("round_end")
check(re is not None, "round_end broadcast after a valid Stop")
check(re["caller"] == cur, "round_end names the caller")
check(len(re["results"]) == 2, "round_end reveals all participants")
check(all("hand" in r and isinstance(r["hand"], list) for r in re["results"]),
      "every result reveals the player's hand")
check(all("round_score" in r and "total_score" in r for r in re["results"]),
      "results carry round and total scores")
# Caller's score equals either total-5 (win) or total+40 (caught) — both >=0.
caller_row = next(r for r in re["results"] if r["user_id"] == cur)
ht = caller_row["hand_total"]
ok_score = caller_row["round_score"] in (max(ht - 5, 0), ht + 40)
check(ok_score, "caller score matches win or caught formula")

# Both clients received the same round_end.
check(B.get("round_end") is not None, "the other player also receives round_end")

ca.disconnect(); cb.disconnect(); time.sleep(0.2)
print("\n%d/%d socket checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
