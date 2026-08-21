import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""The emit guard must actually fire — otherwise it is decoration.

sockets/audience.py exists to catch a private payload addressed to a public
audience. A guard that never triggers is worse than no guard, because it reads
as protection. These checks pin the behaviour in both directions: real leaks are
caught, and the legitimate traffic the games depend on is left alone.
"""
from game.core.cards import Card
from game.core.states import STATE_IN_TURN, STATE_ROUND_END
from sockets import audience

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


class FakeManager:
    """Resolves a room code the way RoomManager does, and nothing else."""

    def __init__(self, room):
        self.room = room

    def get_room(self, code):
        return self.room if code == self.room.code else None


def seven_room():
    from game.super_seven.room import Room
    from game.super_seven.settings import DEFAULT_SETTINGS
    room = Room("AAAA", "u0", dict(DEFAULT_SETTINGS))
    for i in range(3):
        room.register_player("u%d" % i, "P%d" % i).connected = True
    room.start_round()
    return room


def bluff_room():
    from game.bluff.room import Room
    from game.bluff.settings import DEFAULT_SETTINGS
    room = Room("BBBB", "u0", dict(DEFAULT_SETTINGS))
    for i in range(3):
        room.register_player("u%d" % i, "P%d" % i).connected = True
    room.start_round()
    return room


# ── Super Seven: hands secret, centre public ─────────────────────────────
room = seven_room()
hand = room.players["u0"].hand
secret = {"cards": [c.to_dict() for c in hand]}

found = audience.violations("your_hand", secret, room)
check(len(found) == len(hand),
      "Super Seven: a hand broadcast to the room is flagged (every card)")

centre = {"center": [c.to_dict() for c in room.center_throw]}
check(audience.violations("table_state", centre, room) == [],
      "Super Seven: the face-up centre throw is not flagged")

check(audience.violations("table_state", room.public_round_state(), room) == [],
      "Super Seven: the real public_round_state passes clean")

# Round end reveals every hand by design, so the same payload must be allowed.
room.state = STATE_ROUND_END
check(audience.violations("round_end", secret, room) == [],
      "Super Seven: hands are allowed once the round has ended")
room.state = STATE_IN_TURN

# ── Bluff: nothing is face-up during play ────────────────────────────────
broom = bluff_room()
one = {"cards": [broom.players["u1"].hand[0].to_dict()]}
check(len(audience.violations("cards_played", one, broom)) == 1,
      "Bluff: any single card face in a room payload is flagged")
check(audience.violations("table_state", broom.public_round_state(), broom) == [],
      "Bluff: the real public_round_state passes clean")

# ── routing: private destinations and reveal events ──────────────────────
audience._manager = FakeManager(room)
prev_mode = audience.MODE
audience.MODE = "raise"
try:
    raised = False
    try:
        audience._check("your_hand", secret, room.code)
    except audience.LeakError:
        raised = True
    check(raised, "guard raises in raise-mode when a hand is sent to the room code")

    # A sid is not a room code, so it is already private.
    ok_private = True
    try:
        audience._check("your_hand", secret, "a-socket-sid-not-a-room")
    except audience.LeakError:
        ok_private = False
    check(ok_private, "guard ignores a payload addressed to a single socket")

    # No destination = flask_socketio's contextual reply to the requester only.
    ok_ctx = True
    try:
        audience._check("your_hand", secret, None)
    except audience.LeakError:
        ok_ctx = False
    check(ok_ctx, "guard ignores a contextual reply with no destination")

    # An allowlisted reveal event is permitted to carry faces.
    ok_reveal = True
    audience._manager = FakeManager(broom)
    try:
        audience._check("bluff_show_result", one, broom.code)
    except audience.LeakError:
        ok_reveal = False
    check(ok_reveal, "guard allows the allowlisted bluff_show_result reveal")

    # An unregistered game must not raise: no oracle means no opinion.
    saved = audience._ORACLES.pop("bluff")
    quiet = True
    try:
        audience._check("cards_played", one, broom.code)
    except audience.LeakError:
        quiet = False
    audience._ORACLES["bluff"] = saved
    check(quiet, "guard stays silent for a game with no registered oracle")
finally:
    audience.MODE = prev_mode
    audience._manager = None

# ── log mode must never raise, whatever it finds ─────────────────────────
audience._manager = FakeManager(room)
audience.MODE = "log"
audience._seen.clear()
try:
    # Swallow the report: this check deliberately triggers logging, and the
    # LEAK-GUARD lines would otherwise look like a real finding in the suite log.
    import contextlib, io
    with contextlib.redirect_stderr(io.StringIO()) as sink:
        audience._check("your_hand", secret, room.code)
    check("LEAK-GUARD" in sink.getvalue(),
          "log mode reports without raising (a live game is never broken)")
except Exception as exc:
    check(False, "log mode raised %r — it must only log" % exc)
finally:
    audience.MODE = prev_mode
    audience._manager = None

# ── detector precision: card-shaped strings must not false-positive ──────
decoys = {
    "players": [{"name": "AS", "user_id": "KD"}],
    "table_theme": "KH",
    "settings": {"max_score": 100},
    "code": "10C",
}
check(audience.violations("table_state", decoys, room) == [],
      "a player named 'AS' or a theme called 'KH' is not mistaken for a card")

# A card dict nested arbitrarily deep is still found.
buried = {"a": {"b": [{"c": {"d": hand[0].to_dict()}}]}}
found_deep = audience.violations("whatever", buried, room)
check(len(found_deep) == 1 and "a.b[0].c.d" in found_deep[0],
      "a card buried deep in a payload is found, with its path reported")

print("\n%d/%d audience-guard checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
