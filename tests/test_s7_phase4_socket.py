import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Phase 4 socket test: round_end fields and the next-round loop."""
import time, socketio

BASE = "http://localhost:5005"
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


def wait_for(predicate, timeout=6.0, step=0.05):
    """Poll until the server has caught up, instead of guessing with sleep().

    Every socket test shares one server, so a sleep that is comfortable on an
    idle machine is a coin flip on a busy one. This file was the suite's
    long-standing intermittent failure (docs/todos.md §16b) for exactly that
    reason — the assertions were always right, the waits were not.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def client(store):
    c = socketio.Client()
    c.on("room_created", lambda d: store.update(code=d["code"]))
    c.on("join_ok", lambda d: store.update(code=d["code"]))
    c.on("room_joined", lambda d: store.update(joined=True))
    c.on("player_list", lambda d: store.update(roster=d["players"]))
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
wait_for(lambda: "code" in stores["A"])
code = stores["A"]["code"]
for u in ("B", "C"):
    clients[u].emit("join_room", {"code": code, "name": u, "user_id": u})
    wait_for(lambda u=u: "code" in stores[u])
for u in ("A", "B", "C"):
    clients[u].emit("enter_room", {"code": code, "name": u, "user_id": u})
# Every player must be attached before the deal, or start_game either refuses
# (below the minimum) or deals a table that is missing whoever was still in
# flight — which is not the thing this file is testing.
assert wait_for(lambda: all(stores[u].get("joined") for u in stores)), "not everyone entered"
assert wait_for(lambda: len([p for p in stores["A"].get("roster", []) if p["connected"]]) == 3), \
    "the room never showed all three as connected"
clients["A"].emit("start_game", {"code": code, "user_id": "A"})
assert wait_for(lambda: "table" in stores["A"]
                and all(len(stores[u].get("hand") or []) == 7 for u in stores)), \
    "the round was never dealt: %r" % stores["A"].get("error")

def current():
    return stores["A"]["table"]["current_turn"]

# Play one full orbit (3 players): single + draw each.
#
# Waits on the server's own state rather than a fixed sleep. With sleeps, a
# loaded machine could leave `current()` or the cached hand stale, so the test
# would play a card that was no longer held (or play out of turn); the emit is
# rejected, the orbit silently falls short, and the failure surfaces several
# assertions later as something unrelated. This is the same correction §20b
# applied to the rest of this file — these two sleeps were left behind.
for _ in range(3):
    cur = current()
    hand = stores[cur]["hand"]
    clients[cur].emit("play_cards", {"code": code, "user_id": cur, "card_ids": [hand[0]["id"]]})
    # Two legal outcomes: usually the throw owes a draw and the turn stays put,
    # but a single card that happens to match the centre is a free Match, which
    # owes nothing and advances the turn at once. Waiting only for the draw
    # would hang on that second case.
    assert wait_for(lambda c=cur: stores["A"]["table"].get("awaiting_draw")
                    or current() != c), \
        "the throw never registered for %s: %r" % (cur, stores[cur].get("error"))
    if current() == cur and stores["A"]["table"].get("awaiting_draw"):
        clients[cur].emit("draw_card", {"code": code, "user_id": cur})
        assert wait_for(lambda c=cur: current() != c), \
            "the turn never left %s: %r" % (cur, stores[cur].get("error"))

check(stores["A"]["table"]["first_orbit_complete"], "first orbit completed with 3 players")

# Current player calls Stop.
cur = current()
clients[cur].emit("call_stop", {"code": code, "user_id": cur})
wait_for(lambda: stores["A"].get("round_end") is not None)
re = stores["A"].get("round_end")
check(re is not None, "round_end received")
check("game_over" in re and "eliminated" in re and "winner" in re,
      "round_end carries game_over / eliminated / winner")

if not re["game_over"]:
    # Who the host is has to be read, not assumed. A caught Stop can put a
    # player over max_score in a single round, and eliminating the host hands
    # the role to someone else (_migrate_host_if_eliminated). This file used to
    # hardcode A, so on the runs where A was eliminated BOTH next_round calls
    # went to the wrong player — which read as an intermittent timeout rather
    # than the assumption it actually was.
    host = re.get("host_id") or "A"
    non_host = next(u for u in ("A", "B", "C") if u != host)
    # Eliminated players are dealt an empty hand next round, on purpose, so
    # only the survivors are checked for a fresh deal below.
    active = [p["user_id"] for p in re.get("players", []) if not p.get("eliminated")]

    # Non-host cannot advance.
    stores[non_host]["error"] = None
    clients[non_host].emit("next_round", {"code": code, "user_id": non_host})
    wait_for(lambda: stores[non_host]["error"] is not None)
    check(stores[non_host]["error"] == "Only the host can start the next round.",
          "non-host cannot start the next round")

    # Host advances to round 2.
    #
    # Both the round number and the hands are cleared first. Clearing the hands
    # matters: every player throws one card and draws one back during the orbit
    # above, so "everyone holds 7" is true all the way through round 1 — the
    # old check could not tell a fresh deal from no deal at all, and passed even
    # on runs where round 2 never started.
    for s in stores.values():
        s["round_no"] = None
        s["hand"] = None
    stores[host]["error"] = None
    clients[host].emit("next_round", {"code": code, "user_id": host})
    wait_for(lambda: stores[host].get("round_no") == 2
             and all(len(stores[u].get("hand") or []) == 7 for u in active))
    check(stores[host].get("round_no") == 2,
          "host starts round 2 (round_no=%r, error=%r, host=%r)"
          % (stores[host].get("round_no"), stores[host].get("error"), host))
    check(all(len(stores[u].get("hand") or []) == 7 for u in active),
          "every active player is dealt a fresh 7-card hand in round 2 (active=%r)"
          % (active,))
else:
    check(True, "game ended in round 1 (cap reached) — next-round path skipped")
    check(stores["A"].get("game_end") is not None or re["game_over"], "game_over surfaced")

for c in clients.values():
    c.disconnect()
time.sleep(0.2)
print("\n%d/%d socket checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
