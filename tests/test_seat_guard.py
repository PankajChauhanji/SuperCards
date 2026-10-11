import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Seat guard (sockets/seat_guard.py): an action must come from the player it names.

Every player's user_id is public (it rides in every roster broadcast), and the
handlers used to trust the user_id in each payload. So a guest could send
next_round, kick_player or a game move *as the host* or as whoever held the
turn. These checks impersonate other players from a real, seated socket and
assert that nothing happens — and that the real owners can still act.

Runs in-process through the real handlers (Flask-SocketIO's test client).
"""
os.environ.setdefault("LEAK_GUARD", "raise")

from flask import Flask
from flask_socketio import SocketIO

from game.core.manager import RoomManager
from game.core.states import STATE_LOBBY, STATE_IN_TURN
from sockets import register_handlers, seat_guard

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


app = Flask(__name__)
sio = SocketIO(app, async_mode="threading")
manager = RoomManager(restore=False)
register_handlers(sio, manager)


def received(client, name=None):
    return [e for e in client.get_received() if name is None or e["name"] == name]


def refused(client):
    return any(e["args"][0].get("reason") == "not_your_seat" for e in received(client, "error"))


def seat(game_type, n_guests=1):
    """A room with a seated host and seated guests. Returns (code, host, guests)."""
    host = sio.test_client(app)
    host.emit("create_room", {"name": "Host", "user_id": "host", "game_type": game_type})
    code = received(host, "room_created")[0]["args"][0]["code"]
    host.emit("enter_room", {"code": code, "name": "Host", "user_id": "host"})
    guests = []
    for i in range(n_guests):
        g = sio.test_client(app)
        uid = "guest%d" % i
        g.emit("join_room", {"code": code, "name": "Guest %d" % i, "user_id": uid})
        g.emit("enter_room", {"code": code, "name": "Guest %d" % i, "user_id": uid})
        guests.append(g)
    for c in [host] + guests:
        c.get_received()
    return code, host, guests


# ---- the rule itself ----
seat_guard.SID_INDEX["sidA"] = ("ABCD", "u1")
check(seat_guard.seat_matches("sidA", {"code": "abcd", "user_id": "u1"}), "own seat (code case-insensitive) passes")
check(not seat_guard.seat_matches("sidA", {"code": "ABCD", "user_id": "u2"}), "another player's id is refused")
check(not seat_guard.seat_matches("sidA", {"code": "WXYZ", "user_id": "u1"}), "another room's code is refused")
check(not seat_guard.seat_matches("sidB", {"code": "ABCD", "user_id": "u1"}), "an unseated socket is refused")
check(seat_guard.seat_matches("sidB", None) and seat_guard.seat_matches("sidB", {"emoji": "x"}),
      "a payload naming nobody is left to the handler")
del seat_guard.SID_INDEX["sidA"]

# ---- lobby: a guest cannot be the host ----
code, host, (guest,) = seat("super_seven")
room = manager.get_room(code)
before = dict(room.settings)
guest.emit("update_settings", {"code": code, "user_id": "host", "settings": {"max_score": 20}})
check(refused(guest) and room.settings == before, "a guest cannot change the rules as the host")
guest.emit("add_bot", {"code": code, "user_id": "host"})
check(refused(guest) and not any(p.is_bot for p in room.players.values()), "a guest cannot seat a computer player as the host")
guest.emit("start_game", {"code": code, "user_id": "host"})
check(refused(guest) and room.state == STATE_LOBBY, "a guest cannot start the game as the host")
guest.emit("quit_game", {"code": code, "user_id": "host"})
check(refused(guest) and "host" in room.players, "a guest cannot make the host leave")

# A third, never-seated socket that only knows the ids from a roster broadcast.
stranger = sio.test_client(app)
stranger.emit("kick_player", {"code": code, "user_id": "host", "target": "guest0"})
check(refused(stranger) and "guest0" in room.players, "an outsider cannot kick a player as the host")

# The real host still can.
host.emit("start_game", {"code": code, "user_id": "host"})
check(room.state == STATE_IN_TURN and not refused(host), "the host's own start goes through")

# ---- in a game: nobody can take someone else's turn ----
current = room.current_turn_id()
mover = host if current == "host" else guest
other = guest if mover is host else host
other_id = "guest0" if other is guest else "host"
hand = room.hand_for(current)
before_hand = len(hand)
other.emit("play_cards", {"code": code, "user_id": current, "card_ids": [hand[0]["id"]]})
check(refused(other) and len(room.hand_for(current)) == before_hand and room.current_turn_id() == current,
      "a player cannot play the turn-holder's cards")
mover.emit("play_cards", {"code": code, "user_id": current, "card_ids": [hand[0]["id"]]})
check(not refused(mover) and len(room.hand_for(current)) < before_hand, "the turn-holder's own play goes through")

for c in (host, guest, stranger):
    if c.is_connected():
        c.disconnect()

# ---- every game's move events are covered ----
for game_type, event, extra in (
    ("bluff", "bluff_pass", {}),
    ("super_four", "s4_begin_play", {}),
    ("poker", "poker_action", {"action": "fold"}),
):
    code, host, (guest,) = seat(game_type)
    room = manager.get_room(code)
    host.emit("start_game", {"code": code, "user_id": "host"})
    for c in (host, guest):
        c.get_received()
    snapshot = (room.state, getattr(room, "current_turn_id", lambda: None)())
    victim = "host"
    guest.emit(event, dict({"code": code, "user_id": victim}, **extra))
    check(refused(guest) and (room.state, getattr(room, "current_turn_id", lambda: None)()) == snapshot,
          "[%s] a guest cannot send %s as the host" % (game_type, event))
    guest.emit("reaction", {"code": code, "user_id": victim, "emoji": "🤡"})
    check(refused(guest), "[%s] a guest cannot send a reaction in the host's name" % game_type)
    for c in (host, guest):
        if c.is_connected():
            c.disconnect()

# ---- reconnecting re-seats the new socket ----
code, host, (guest,) = seat("super_seven")
room = manager.get_room(code)
guest.disconnect()
guest = sio.test_client(app)
guest.emit("quit_game", {"code": code, "user_id": "guest0"})
check(refused(guest) and "guest0" in room.players, "a fresh socket that has not re-entered is not trusted yet")
guest.emit("enter_room", {"code": code, "name": "Guest 0", "user_id": "guest0"})
guest.get_received()
guest.emit("quit_game", {"code": code, "user_id": "guest0"})
check(not refused(guest) and "guest0" not in room.players, "after enter_room the same player acts normally")
for c in (host, guest):
    if c.is_connected():
        c.disconnect()

print("\n%d/%d seat-guard checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
