import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Leaving, or losing the host, while a round summary is up.

Production bug (2026-10-11): a six-player Super Seven table could not start
round 2. Two defects combined:

1. A player who quit while the round summary was showing was removed from
   ``room.players`` but left in ``turn_order``, so ``round_end_payload`` raised
   KeyError. The quit broadcast died half-way, and every later reconnect or
   refresh raised again — those players landed on a lobby whose Start game the
   server refuses, and a reload took the same path.
2. The host's socket dropping (a refresh, a locked phone) moves the host role
   to someone else. The client-side footers are covered in the JS; here the
   server half is pinned: whoever the server names host can deal.

The engine half runs for every game that has a round summary. The socket half
drives Super Seven in-process through the real handlers (Flask-SocketIO's test
client), so it needs no live server.
"""
os.environ.setdefault("LEAK_GUARD", "raise")

import random

from game.core import registry
from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


def make(game_type, n):
    spec = registry.get(game_type)
    room = spec.room_class("QUIT", "p0", dict(spec.default_settings))
    room.game_type = game_type
    for i in range(n):
        room.register_player("p%d" % i, "P%d" % i).connected = True
    return room


def to_round_end(room):
    """Drive a fresh round to its summary by the game's own rules."""
    if room.game_type == "super_seven":
        room.end_round(None)
    elif room.game_type == "super_four":
        room._finalize_round()
    elif room.game_type == "poker":
        while room.state == STATE_IN_TURN:
            room.act(room.current_turn_id(), "fold")


def summary_views(room, viewer):
    """Everything a reconnect or a quit broadcast builds at a round summary."""
    views = [room.public_round_state(), room.public_players()]
    if hasattr(room, "private_view"):
        views.append(room.private_view(viewer))
    if room.state == STATE_ROUND_END:
        if room.game_type == "super_seven":
            views.append(room.round_end_payload(room._last_result))
        else:
            views.append(room.round_end_payload())
    if room.state == STATE_GAME_END:
        views.append(room.game_end_payload())
    return views


# ---- engine: every game with a round summary ----
for game_type in ("super_seven", "super_four", "poker"):
    for seed in range(20):
        rng = random.Random(seed)
        room = make(game_type, 6)
        room.start_round()
        to_round_end(room)
        if room.state != STATE_ROUND_END:
            continue
        quitter = rng.choice([u for u in room.players if u != room.host_id])
        room.remove_participant(quitter)
        try:
            for viewer in room.players:
                summary_views(room, viewer)
            ok = True
        except Exception as exc:  # noqa: BLE001 - the bug was exactly an exception here
            ok = False
            print("   seed=%d: %s: %s" % (seed, type(exc).__name__, exc))
        if not ok:
            break
        room.start_round()
        # Poker keeps a left player's seat for the game; who is dealt in is in_hand.
        order = room.in_hand if game_type == "poker" else room.turn_order
        if quitter in order:
            ok = False
            break
    check(ok, "[%s] a quit during the round summary leaves every summary view buildable "
              "and the next round deals without the quitter" % game_type)

room = make("super_seven", 4)
room.start_round()
room.end_round(None)
room.remove_participant("p2")
rows = [r["user_id"] for r in room.round_end_payload(room._last_result)["results"]]
check("p2" not in rows and len(rows) == 3, "[super_seven] the summary simply drops the quitter's row")


# ---- socket: the production scenario, through the real handlers ----
from flask import Flask
from flask_socketio import SocketIO
from game.core.manager import RoomManager
from sockets import register_handlers

app = Flask(__name__)
sio = SocketIO(app, async_mode="threading")
manager = RoomManager(restore=False)
register_handlers(sio, manager)


def received(client, name=None):
    return [e for e in client.get_received() if name is None or e["name"] == name]


def errors(client):
    return [e["args"][0].get("message") for e in received(client, "error")]


ids = ["u%d" % i for i in range(6)]
clients = [sio.test_client(app) for _ in ids]
clients[0].emit("create_room", {"name": "Host", "user_id": ids[0], "game_type": "super_seven"})
code = received(clients[0], "room_created")[0]["args"][0]["code"]
for i in range(1, 6):
    clients[i].emit("join_room", {"code": code, "name": "P%d" % i, "user_id": ids[i]})
for i, c in enumerate(clients):
    c.emit("enter_room", {"code": code, "name": "P%d" % i, "user_id": ids[i]})
clients[0].emit("start_game", {"code": code, "user_id": ids[0], "shuffle": True})
room = manager.get_room(code)
room.end_round(None)
for c in clients:
    c.get_received()

try:
    clients[3].emit("quit_game", {"code": code, "user_id": ids[3]})
    quit_ok = True
except Exception as exc:  # noqa: BLE001
    quit_ok = False
    print("   quit_game raised %s: %s" % (type(exc).__name__, exc))
check(quit_ok, "a quit during the round summary does not crash the quit broadcast")
got = [e["name"] for e in received(clients[1])]
check("player_list" in got and "round_end" in got,
      "the others get the new roster and a refreshed summary (got %s)" % got)

# A player refreshes: the summary must come back, not a dead lobby.
clients[2].disconnect()
clients[2] = sio.test_client(app)
try:
    clients[2].emit("enter_room", {"code": code, "name": "P2", "user_id": ids[2]})
    got = [e["name"] for e in received(clients[2])]
except Exception as exc:  # noqa: BLE001
    got = ["raised %s" % type(exc).__name__]
check("round_end" in got, "a player refreshing during the summary gets the summary back (got %s)" % got)

# The host refreshes: the role moves on, and whoever holds it can deal.
clients[0].disconnect()
check(room.host_id != ids[0] and room.host_id in room.players and room.players[room.host_id].connected,
      "the host's socket dropping hands the role to a connected player")
clients[0] = sio.test_client(app)
clients[0].emit("enter_room", {"code": code, "name": "Host", "user_id": ids[0]})
joined = received(clients[0], "room_joined")
check(joined and joined[0]["args"][0]["host_id"] == room.host_id,
      "the returning player is told who the host is now")
new_host = ids.index(room.host_id)
for c in clients:
    c.get_received()
clients[new_host].emit("next_round", {"code": code, "user_id": room.host_id, "shuffle": True})
check(room.state == STATE_IN_TURN and ids[3] not in room.turn_order and len(room.turn_order) == 5,
      "the new host deals round 2 for the five who stayed (errors: %s)" % errors(clients[new_host]))

for c in clients:
    if c.is_connected():
        c.disconnect()

print("\n%d/%d quit-between-rounds checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
