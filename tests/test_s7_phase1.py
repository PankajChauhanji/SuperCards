import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 1 test: privacy-correct dealing and reconnect.

Verifies hands are dealt correctly, the shared snapshot leaks no card faces,
each player privately receives only their own hand, and a mid-round reconnect
restores the same hand.
"""
import time
import json
import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + msg)


def make_client(store):
    c = socketio.Client()
    store["events"] = []  # (event_name, raw_json) for privacy scanning

    @c.on("room_created")
    def _rc(d): store["code"] = d["code"]

    @c.on("join_ok")
    def _jok(d): store["code"] = d["code"]

    @c.on("round_start")
    def _rs(d):
        store["round_start"] = d
        store["events"].append(("round_start", json.dumps(d)))

    @c.on("your_hand")
    def _yh(d):
        store["hand"] = d["cards"]
        store["events"].append(("your_hand", json.dumps(d)))

    @c.on("player_list")
    def _pl(d):
        store["events"].append(("player_list", json.dumps(d)))

    @c.on("room_joined")
    def _rj(d):
        store["events"].append(("room_joined", json.dumps(d)))

    @c.on("error")
    def _e(d): store["error"] = d["message"]

    return c


# Three players to exercise the deal arithmetic.
A, B, C = {}, {}, {}
ca, cb, cc = make_client(A), make_client(B), make_client(C)
ca.connect(BASE); cb.connect(BASE); cc.connect(BASE)
time.sleep(0.3)

ca.emit("create_room", {"name": "A", "user_id": "A", "settings": {}})
time.sleep(0.3)
code = A["code"]
for c, s, uid in [(ca, A, "A"), (cb, B, "B"), (cc, C, "C")]:
    if uid != "A":
        c.emit("join_room", {"code": code, "name": uid, "user_id": uid})
        time.sleep(0.15)
    c.emit("enter_room", {"code": code, "name": uid, "user_id": uid})
    time.sleep(0.15)

# Host starts -> deal.
ca.emit("start_game", {"code": code, "user_id": "A"})
time.sleep(0.6)

# --- deal correctness ---
rs = A.get("round_start", {})
log(bool(rs), "round_start broadcast received")
log(rs.get("deck_count") == 52 - 3 * 7, "deck_count = 31 after dealing 3x7")
log(rs.get("current_turn") in ("A", "B", "C"), "a current turn is set")
log(rs.get("round_number") == 1, "round number is 1")
log(rs.get("center") == [], "center starts empty")
counts = {p["user_id"]: p["card_count"] for p in rs.get("players", [])}
log(all(counts.get(u) == 7 for u in ("A", "B", "C")), "every player shows 7 cards")

# --- each got a private hand of 7 ---
log(len(A.get("hand", [])) == 7, "A received 7 private cards")
log(len(B.get("hand", [])) == 7, "B received 7 private cards")
log(len(C.get("hand", [])) == 7, "C received 7 private cards")

ha = {c["id"] for c in A["hand"]}
hb = {c["id"] for c in B["hand"]}
hc = {c["id"] for c in C["hand"]}
log(len(ha | hb | hc) == 21, "all 21 dealt cards are distinct (no duplicates)")

# --- PRIVACY: no client ever saw another player's exact cards ---
def saw_any(store, foreign_ids):
    blob = "\n".join(raw for _, raw in store["events"])
    return any(('"id": "%s"' % cid) in blob or ('"%s"' % cid) in blob for cid in foreign_ids)

# A's event stream must not contain B's or C's specific card ids.
leak_to_a = saw_any(A, hb | hc)
leak_to_b = saw_any(B, ha | hc)
log(not leak_to_a, "A's payloads contain none of B/C's card faces")
log(not leak_to_b, "B's payloads contain none of A/C's card faces")

# round_start.players must carry counts only, never a 'cards'/'hand' field.
sample = rs.get("players", [{}])[0]
log("cards" not in sample and "hand" not in sample,
    "public player view exposes no hand field")

# --- mid-round reconnect restores same hand ---
B2 = {}
cb2 = make_client(B2)
cb2.connect(BASE)
time.sleep(0.2)
cb2.emit("enter_room", {"code": code, "name": "B", "user_id": "B"})
time.sleep(0.5)
log(len(B2.get("hand", [])) == 7, "reconnecting B gets a hand again")
log({c["id"] for c in B2["hand"]} == hb, "reconnected hand is identical")
log(bool(B2.get("round_start")), "reconnecting B gets the table snapshot")

for c in (ca, cb, cc, cb2):
    c.disconnect()
time.sleep(0.2)

print("\n%d/%d checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
