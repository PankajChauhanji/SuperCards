"""Seat guard — an action must come from the player it names.

Every gameplay and host event carries ``{code, user_id}`` in its payload, and the
handlers used to take both at their word. But every player's ``user_id`` is
public (it is in every roster broadcast), so anyone could open the browser
console and send ``next_round``, ``kick_player`` or ``play_cards`` *as someone
else* — acting as the host, or taking another player's turn.

The server already knows the truth: ``enter_room`` binds each socket to exactly
one ``(code, user_id)`` in ``sockets.common.SID_INDEX``. This module checks every
incoming event against that binding before its handler runs, so a payload that
names a different player or room is refused. One chokepoint, the same idea as
``sockets/audience.py`` for outgoing emits: no handler has to remember, and a
handler added later is covered automatically.

How it is installed: ``socketio.on`` is wrapped before any module registers its
handlers (see ``sockets/__init__.py``), so every ``@socketio.on(...)`` gets the
check except the events in ``OPEN_EVENTS`` below — the ones that happen before
a socket is seated, or that only ever describe the socket itself.

A refusal does not run the handler. It answers with an ``error`` whose reason is
``"not_your_seat"``; a genuine client only ever sees that if its binding was
lost (a reconnect race), and core/socket.js responds by re-entering the room.
"""
import functools
import logging

from flask import request

from sockets.common import SID_INDEX, error

log = logging.getLogger(__name__)

# Events that are allowed before (or without) a seat:
#   create_room / create_solo / join_room — the home page, before any room;
#   enter_room — what creates the binding in the first place (it already checks
#     that the user_id is registered in that room);
#   client_ping / client_sync — the connection heartbeat, which reports on the
#     socket itself and changes nothing;
#   connect / disconnect — socket lifecycle, no payload to trust.
OPEN_EVENTS = frozenset({
    "connect", "disconnect",
    "create_room", "create_solo", "join_room", "enter_room",
    "client_ping", "client_sync",
})


def seat_matches(sid, data) -> bool:
    """True when this socket is seated as the player (and room) the payload names."""
    if not isinstance(data, dict):
        # No payload to impersonate anyone with; the handler's own checks apply.
        return True
    names_player = "user_id" in data
    names_room = "code" in data
    if not names_player and not names_room:
        return True
    seat = SID_INDEX.get(sid)
    if seat is None:
        return False
    seat_code, seat_user = seat
    if names_player and data.get("user_id") != seat_user:
        return False
    if names_room and (data.get("code") or "").strip().upper() != seat_code:
        return False
    return True


def install(socketio) -> None:
    """Wrap ``socketio.on`` so every non-open handler checks the caller's seat."""
    if getattr(socketio, "_seat_guarded", False):
        return
    original_on = socketio.on

    def on(event, *args, **kwargs):
        register = original_on(event, *args, **kwargs)
        if event in OPEN_EVENTS:
            return register

        def decorator(handler):
            @functools.wraps(handler)
            def guarded(*handler_args):
                data = handler_args[0] if handler_args else None
                if not seat_matches(request.sid, data):
                    log.warning("seat guard refused %r from sid %s (seated as %r)",
                                event, request.sid, SID_INDEX.get(request.sid))
                    return error("That action isn't yours to take — reconnecting you to your seat.",
                                 reason="not_your_seat")
                return handler(*handler_args)
            return register(guarded)
        return decorator

    socketio.on = on
    socketio._seat_guarded = True
