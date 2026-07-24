import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 2 socket test: turn actions and rejections over the wire."""
import time, socketio

BASE = "http://localhost:5005"
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


def client(store):
    c = socketio.Client()
    store["events"] = []
    c.on("room_created", lambda d: store.update(code=d["code"]))
    c.on("join_ok", lambda d: store.update(code=d["code"]))
    c.on("round_start", lambda d: store.update(table=d))
    c.on("table_state", lambda d: store.update(table=d))
    c.on("your_hand", lambda d: store.update(hand=d["cards"]))
    c.on("cards_played", lambda d: store.setdefault("plays", []).append(d))
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

cur = A["table"]["current_turn"]
other = "B" if cur == "A" else "A"
cur_store = A if cur == "A" else B
oth_store = A if other == "A" else B
cur_client = ca if cur == "A" else cb
oth_client = ca if other == "A" else cb
print("current turn:", cur)

# Wrong player tries to play -> rejected.
oth_store["error"] = None
oth_client.emit("play_cards", {"code": code, "user_id": other,
                               "card_ids": [oth_store["hand"][0]["id"]]})
time.sleep(0.3)
check(oth_store["error"] == "It's not your turn.", "non-current player's throw is rejected")

# Current player throws a card not in hand -> rejected.
cur_store["error"] = None
cur_client.emit("play_cards", {"code": code, "user_id": cur, "card_ids": ["ZZ"]})
time.sleep(0.3)
check(cur_store["error"] == "Those cards aren't in your hand.", "bogus card id rejected")

# Current player makes a legal single discard.
first_card = cur_store["hand"][0]["id"]
cur_client.emit("play_cards", {"code": code, "user_id": cur, "card_ids": [first_card]})
time.sleep(0.4)
check(A["table"]["awaiting_draw"] is True, "single discard puts table in awaiting_draw")
check(A["table"]["current_turn"] == cur, "turn stays on thrower until they draw")
check(any(p["action_type"] == "single" for p in cur_store.get("plays", [])),
      "cards_played announced the single")
check(first_card not in {c["id"] for c in cur_store["hand"]}, "thrown card removed from hand")

# Can't throw again before drawing.
cur_store["error"] = None
cur_client.emit("play_cards", {"code": code, "user_id": cur,
                               "card_ids": [cur_store["hand"][0]["id"]]})
time.sleep(0.3)
check(cur_store["error"] == "Draw a card before playing again.", "second throw blocked until draw")

# Draw -> turn passes.
deck_before = A["table"]["deck_count"]
cur_client.emit("draw_card", {"code": code, "user_id": cur})
time.sleep(0.4)
check(A["table"]["awaiting_draw"] is False, "drawing clears awaiting_draw")
check(A["table"]["current_turn"] == other, "turn passes to the other player after draw")
check(A["table"]["deck_count"] == deck_before - 1, "deck count dropped by one")
check(len(cur_store["hand"]) == 7, "thrower is back to 7 cards")

# Now the other player can act; wrong player (previous) is rejected.
cur_store["error"] = None
cur_client.emit("play_cards", {"code": code, "user_id": cur,
                               "card_ids": [cur_store["hand"][0]["id"]]})
time.sleep(0.3)
check(cur_store["error"] == "It's not your turn.", "previous player can't act out of turn")

ca.disconnect(); cb.disconnect(); time.sleep(0.2)
print("\n%d/%d socket checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
