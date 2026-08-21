"""Audience guard: catches a private payload sent to a public audience.

The hidden-information guardrail used to rest entirely on the author of each of
the ~55 emit sites remembering to target ``to=player.sid`` rather than
``to=room.code``. One slip broadcasts a hand to the whole table and *nothing
fails* — no test, no log line, no error. Players just start losing to opponents
who can see their cards.

This module closes that gap without touching those 55 call sites. Every outgoing
emit passes through here; when the destination resolves to a room code (i.e. a
broadcast), the payload is scanned for serialized cards and compared against
what that game says is currently public
(``game/<variant>/visibility.public_card_ids``). Anything extra is a leak.

Wiring (deliberately two mechanisms, because the app legitimately uses two emit
styles):
  * handlers call flask_socketio's contextual ``emit`` — they import it from
    here instead, a one-line change per gameplay module.
  * background work (director tick, bot turns) calls ``socketio.emit`` — that
    bound method is wrapped in ``install()``.

Failure mode is configurable and defaults to *safe*. In production the guard
logs and lets the payload through unchanged; it never raises and never rewrites
a payload, because a false positive must not be able to break a live game. Under
FLASK_DEBUG (and in the test suite) it raises, so a real mistake is impossible
to miss while developing. Set LEAK_GUARD=raise|log|off to override.
"""
import os
import sys

import flask_socketio

# game_type -> callable(room) -> set of card ids (or visibility.EVERYTHING)
_ORACLES = {}

# Events allowed to broadcast card faces during play, because revealing is the
# entire point of the event. Keep this list short and justified — every entry is
# a hole in the guard.
REVEAL_EVENTS = {
    # Bluff: a Show flips exactly the challenged play for the whole table. The
    # room.apply_show/resolve_show pair asserts it exposes nothing beyond that
    # play (see tests/test_leak_fuzz.py), so the pile stays protected.
    "bluff_show_result",
}

_MODE_ENV = os.environ.get("LEAK_GUARD", "").strip().lower()
_FALLBACK = "raise" if os.environ.get("FLASK_DEBUG") == "1" else "log"
MODE = _MODE_ENV if _MODE_ENV in ("raise", "log", "off") else _FALLBACK

_manager = None
_seen = set()   # de-duplicate log spam: one report per (event, path) per process


def register(game_type: str, oracle) -> None:
    """Register a game's public-visibility oracle. Called by its gameplay module."""
    _ORACLES[game_type] = oracle


class LeakError(AssertionError):
    """A room-wide payload carried a card face the table may not see."""


def _walk_cards(node, path=""):
    """Yield (card_id, path) for every serialized Card in a payload.

    Keys on the dict shape produced by ``Card.to_dict()`` (both ``rank`` and
    ``suit``) rather than on strings, so a player named "AS" or a theme called
    "KD" cannot trigger a false positive.
    """
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str):
            yield node.get("id") or "%s%s" % (node["rank"], node["suit"]), path or "<root>"
            return
        for key, val in node.items():
            yield from _walk_cards(val, "%s.%s" % (path, key) if path else str(key))
    elif isinstance(node, (list, tuple)):
        for idx, val in enumerate(node):
            yield from _walk_cards(val, "%s[%d]" % (path, idx))


def violations(event: str, payload, room):
    """Return a list of leak descriptions for a room-wide payload."""
    oracle = _ORACLES.get(getattr(room, "game_type", None))
    if oracle is None:
        return []
    try:
        allowed = oracle(room)
    except Exception:                       # a broken oracle must not break play
        return []
    return [
        "event=%s leaked card %s at payload.%s (room=%s game=%s state=%s)"
        % (event, card_id, path, room.code, room.game_type, room.state)
        for card_id, path in _walk_cards(payload)
        if card_id not in allowed
    ]


def _check(event, payload, to):
    """Guard one outgoing emit. Never raises unless MODE == 'raise'."""
    if MODE == "off" or _manager is None or not to:
        return
    if event in REVEAL_EVENTS:
        return
    # A destination that is not a known room code is a single socket (a sid) or
    # a namespace — i.e. already private. Only broadcasts are of interest.
    room = _manager.get_room(to) if isinstance(to, str) else None
    if room is None:
        return
    found = violations(event, payload, room)
    if not found:
        return
    if MODE == "raise":
        raise LeakError(found[0] if len(found) == 1 else
                        "%d leaks, first: %s" % (len(found), found[0]))
    for line in found:
        key = line.split(" (room=")[0]
        if key in _seen:
            continue
        _seen.add(key)
        print("LEAK-GUARD: " + line, file=sys.stderr, flush=True)


def emit(event, *args, **kwargs):
    """Drop-in for flask_socketio.emit, guarded.

    Handlers import this instead of flask_socketio's emit. A call with no ``to``
    goes to the requesting client only, which is private by construction.
    """
    payload = args[0] if args else kwargs.get("data")
    _check(event, payload, kwargs.get("to") or kwargs.get("room"))
    return flask_socketio.emit(event, *args, **kwargs)


def install(socketio, manager) -> None:
    """Wrap ``socketio.emit`` so background/bot broadcasts are guarded too."""
    global _manager
    _manager = manager

    if getattr(socketio, "_audience_guarded", False):
        return
    original = socketio.emit

    def guarded_emit(event, *args, **kwargs):
        payload = args[0] if args else kwargs.get("data")
        _check(event, payload, kwargs.get("to") or kwargs.get("room"))
        return original(event, *args, **kwargs)

    socketio.emit = guarded_emit
    socketio._audience_guarded = True
