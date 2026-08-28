import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""State reconciliation: a client must be able to find out it has fallen behind.

Every one of these pins a failure that was reported from real phones and could
not be reproduced in a desktop mobile-emulation view, because the causes are all
things only a real device does: freeze a page's timers, drop a transport without
a close frame, and lose every player's connection at the same moment.

  * a room-wide broadcast carries a version, so a client can tell whether the
    snapshot it is holding is current (sockets/audience.py);
  * a private payload does NOT, because it is an answer to one socket rather than
    a snapshot anyone can fall behind on;
  * each game answers the shared reconnect hook in *its own* event vocabulary —
    the lobby used to send Super Seven's names to every game, which left a
    reconnecting Super 4 player with nothing at all at round end;
  * the empty-room reaper measures its grace period from when a room went empty,
    not from when it was created.
"""
import time

import config
from game.core import registry
from game.core.manager import RoomManager
from game.core.states import STATE_GAME_END
from sockets import audience, presenter

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


class FakeManager:
    """Resolves one room code the way RoomManager does, and nothing else."""

    def __init__(self, room):
        self.room = room

    def get_room(self, code):
        return self.room if code == self.room.code else None


def build(game_type, code="AAAA", players=("u0", "u1")):
    """A started room of the given game, with every player attached."""
    spec = registry.get(game_type)
    room = spec.room_class(code, players[0], dict(spec.default_settings))
    room.game_type = game_type
    for uid in players:
        room.register_player(uid, uid.upper())
        room.attach(uid, "sid_" + uid, uid.upper())
    room.start_round()
    return room


# ── version stamping ─────────────────────────────────────────────────────
room = build("super_seven")
audience._manager = FakeManager(room)
try:
    args = audience._stamped(({"state": room.state},), {}, room.code)
    first = args[0].get(audience.VERSION_KEY)
    check(isinstance(first, int), "a room-wide payload is stamped with a version")

    payload = {"state": room.state}
    args = audience._stamped((payload,), {}, room.code)
    check(args[0].get(audience.VERSION_KEY) == first + 1,
          "the version advances on every room-wide broadcast")
    check(audience.VERSION_KEY not in payload,
          "the caller's own dict is left alone (stamped onto a copy)")

    before = audience.version(room)
    same = audience._stamped(({"cards": ["private"]},), {}, "sid_u0")
    check(audience.VERSION_KEY not in same[0],
          "a payload addressed to one socket is not stamped")
    check(audience.version(room) == before,
          "and does not burn a version, so nobody looks behind for it")

    non_dict = audience._stamped(("just a string",), {}, room.code)
    check(non_dict[0] == "just a string" and audience.version(room) == before,
          "a non-dict payload passes through untouched, version unchanged")
finally:
    audience._manager = None


# ── the reconnect hook speaks each game's own vocabulary ─────────────────
class Recorder:
    """Stands in for the guarded emit so a hook's output can be inspected."""

    def __init__(self):
        self.sent = []

    def __call__(self, event, payload=None, **kwargs):
        self.sent.append(event)

    def events(self):
        return set(self.sent)


def resync_events(game_type, mutate=None):
    """Run a game's registered resync hook and report which events it sent."""
    import sockets.gameplay.super_seven as ss
    import sockets.gameplay.bluff as bl
    import sockets.gameplay.super_four as s4
    module = {"super_seven": ss, "bluff": bl, "super_four": s4}[game_type]
    attr = "_femit" if game_type == "super_four" else "emit"

    room = build(game_type, code="RSY0")
    if mutate:
        mutate(room)

    recorder = Recorder()
    original = getattr(module, attr)
    setattr(module, attr, recorder)
    try:
        check(presenter.resync(room, "u0"),
              "%s registers a resync hook" % game_type)
    finally:
        setattr(module, attr, original)
    return recorder.events()


sent = resync_events("super_seven")
check("round_start" in sent and "your_hand" in sent,
      "super_seven mid-round resync sends round_start + your_hand (got %s)" % sorted(sent))

sent = resync_events("bluff")
check("round_start" in sent and "your_hand" in sent,
      "bluff mid-round resync sends round_start + your_hand (got %s)" % sorted(sent))

sent = resync_events("super_four")
check("s4_state" in sent and "your_view" in sent,
      "super_four mid-round resync sends s4_state + your_view (got %s)" % sorted(sent))

# The regression this whole file exists for: Super 4 at round end used to send
# the reconnecting player nothing, because the shared branch asked for Super
# Seven's `_last_result` and then Super Seven's event name. A page reload took
# the same branch, which is why refreshing did not help.
sent = resync_events("super_four", mutate=lambda r: r._finalize_round())
check("s4_round_end" in sent,
      "super_four at ROUND_END resyncs with s4_round_end, the event it listens "
      "for (got %s)" % sorted(sent))

sent = resync_events("super_seven", mutate=lambda r: r.end_round(None))
check("round_end" in sent,
      "super_seven at ROUND_END resyncs with round_end (got %s)" % sorted(sent))


def _bluff_to_game_end(room):
    room.players["u0"].hand = []
    room.state = STATE_GAME_END
    room.winner = "u0"          # Bluff stores the winner's user_id, not the Player


sent = resync_events("bluff", mutate=_bluff_to_game_end)
check("game_end" in sent,
      "bluff at GAME_END resyncs with game_end (got %s)" % sorted(sent))

# A hook must never address a player who has no live socket.
detached = build("super_seven", code="RSY1")
detached.detach("u0")
import sockets.gameplay.super_seven as _ss
_rec = Recorder()
_orig, _ss.emit = _ss.emit, _rec
try:
    presenter.resync(detached, "u0")
finally:
    _ss.emit = _orig
check(_rec.events() == set(),
      "resync of a player with no socket sends nothing rather than to an empty sid")


# ── the empty-room reaper ────────────────────────────────────────────────
manager = RoomManager()
live = manager.create_room("u0", "Alice", {}, "super_seven")
live.register_player("u1", "Bob")
live.attach("u0", "sid0", "Alice")
live.attach("u1", "sid1", "Bob")
live_code = live.code
live.created_at = time.time() - (config.EMPTY_ROOM_TTL + 600)   # a long game
manager._reap_stale()                                           # scan while present

# Both phones lose their transport for a moment — routine on mobile — and some
# unrelated player creates a room, which is what triggers a reap.
live.detach("u0")
live.detach("u1")
manager.create_room("u9", "Carol", {}, "bluff")
check(live_code in manager.rooms,
      "a long-running game survives every player dropping for a moment")

manager._empty_since[live_code] = time.time() - (config.EMPTY_ROOM_TTL + 1)
manager._reap_stale()
check(live_code not in manager.rooms,
      "but is reaped once genuinely empty for longer than the TTL")

abandoned = RoomManager()
ghost = abandoned.create_room("u0", "Ghost", {}, "super_seven")
ghost.created_at = time.time() - (config.EMPTY_ROOM_TTL + 1)
abandoned._empty_since[ghost.code] = ghost.created_at
abandoned._reap_stale()
check(ghost.code not in abandoned.rooms,
      "a room nobody ever joined is still reaped from its creation time")

returning = RoomManager()
back = returning.create_room("u0", "Alice", {}, "bluff")
returning._reap_stale()
back.attach("u0", "sid0", "Alice")
returning._reap_stale()
check(back.code not in returning._empty_since,
      "the grace clock resets the moment a player comes back")


print("\n%d/%d state-sync checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
