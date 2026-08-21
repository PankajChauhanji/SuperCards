import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Socket smoke test for ALL THREE games — the suite's biggest blind spot.

Every existing socket test drives Super Seven. Bluff and Super 4 had no
end-to-end socket coverage at all, so any change to their handler modules could
only be caught by a human opening a browser. That is a bad place for a
play-tested app to be, and it is exactly the risk introduced by routing every
handler's ``emit`` through sockets/audience.py.

This walks each game through create → enter → start → private deal → one real
action, asserting the server stays healthy and the leak guard does not fire. It
is intentionally shallow: the per-game engine tests cover the rules, and what is
missing here is *wiring* — that the handlers are reachable, the private deal
lands, and the state broadcast comes back.

Needs a server on 5005; run_tests.py starts one (with LEAK_GUARD=raise, so a
guard false-positive shows up here as a failure rather than a log line).
"""
import time

import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def wait_for(state, key, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if state.get(key) is not None:
            return True
        time.sleep(0.1)
    return False


def play(game_type, private_event, action):
    """Drive one game end to end. `action(client, code, uid, state)` makes a move."""
    tag = "[%s]" % game_type
    uid = "smoke-%s" % game_type
    cli = socketio.Client()
    state = {}

    for event in ("room_created", "room_joined", "round_start", "error",
                  private_event, "table_state", "s4_state"):
        cli.on(event, handler=lambda data, e=event: state.__setitem__(e, data or {}))

    try:
        cli.connect(BASE, wait_timeout=10)
        cli.emit("create_solo", {"name": "Smoke", "user_id": uid,
                                 "game_type": game_type})
        log(wait_for(state, "room_created"), "%s solo room created" % tag)
        code = (state.get("room_created") or {}).get("code")
        if not code:
            log(False, "%s no room code — aborting this game" % tag)
            return

        cli.emit("enter_room", {"code": code, "name": "Smoke", "user_id": uid})
        log(wait_for(state, "room_joined"), "%s entered the room" % tag)
        joined = state.get("room_joined") or {}
        log(joined.get("game_type") == game_type,
            "%s room_joined reports the right game_type" % tag)

        cli.emit("start_game", {"code": code, "user_id": uid})
        log(wait_for(state, "round_start"), "%s round started" % tag)

        # The private deal is the whole point of the presenter hook: if the
        # audience migration broke targeting, this is what stops arriving.
        log(wait_for(state, private_event),
            "%s received its private deal (%s)" % (tag, private_event))

        log(state.get("error") is None,
            "%s no error emitted during setup%s"
            % (tag, "" if state.get("error") is None
               else " (got %r)" % state["error"]))

        # One real action through the game's own handler.
        before = dict(state)
        action(cli, code, uid, state)
        time.sleep(1.2)
        moved = (state.get("table_state") != before.get("table_state")
                 or state.get("s4_state") != before.get("s4_state")
                 or state.get(private_event) != before.get(private_event))
        log(moved, "%s the table advanced after an action" % tag)
        log(state.get("error") is None,
            "%s no error after acting%s"
            % (tag, "" if state.get("error") is None
               else " (got %r)" % state["error"]))
    finally:
        try:
            cli.emit("quit_room", {"code": code, "user_id": uid})
        except Exception:
            pass
        try:
            cli.disconnect()
        except Exception:
            pass


# ---- Super Seven: throw one card from the dealt hand ----
def seven_action(cli, code, uid, state):
    hand = (state.get("your_hand") or {}).get("cards") or []
    if hand:
        cli.emit("play_cards", {"code": code, "user_id": uid,
                                "card_ids": [hand[0]["id"]]})


# ---- Bluff: lead off by declaring a rank ----
def bluff_action(cli, code, uid, state):
    hand = (state.get("your_hand") or {}).get("cards") or []
    if hand:
        cli.emit("bluff_play", {"code": code, "user_id": uid,
                                "card_ids": [hand[0]["id"]],
                                "declared_rank": hand[0]["code"]})


# ---- Super 4: end the preview, then draw ----
def four_action(cli, code, uid, state):
    cli.emit("s4_begin_play", {"code": code, "user_id": uid})
    time.sleep(0.6)
    cli.emit("s4_draw", {"code": code, "user_id": uid})


print("Socket smoke across all three games\n")
play("super_seven", "your_hand", seven_action)
print()
play("bluff", "your_hand", bluff_action)
print()
play("super_four", "your_view", four_action)

print("\n%d/%d all-games socket checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
