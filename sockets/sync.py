"""State reconciliation: the heartbeat that tells a client it has fallen behind.

**The failure this exists for.** A phone's transport can die without either end
being told. Android freezes a backgrounded page's timers and network, so the
client comes back holding a socket it still believes is open — ``socket.connected``
reads true while nothing is flowing. The server, whose timers never froze, has
already timed that session out and marked the player offline. Neither side is
wrong from where it stands, and nothing in the protocol made them compare notes.
The player then sat on a table that never updated while the rest of the room
watched them time out, and only a full page reload cleared it.

``core/connection.js`` used to probe for this on ``visibilitychange`` alone,
which covers exactly one entry point: the phone coming out of a pocket. A socket
that died while the player was *looking at the screen* — a Wi-Fi/cellular
handoff, a lift, a dropped packet on the polling transport — was never
re-checked at all.

**The mechanism.** While the page is visible the client sends ``client_sync`` on
a timer, carrying the last state version it has seen. The server answers, and
three things fall out of that one round trip:

* the ack *arriving* proves the socket is alive end-to-end; silence means it is
  a zombie, and the client rebuilds it;
* ``stale`` says this socket is not the one the room has on file (or the player
  is marked offline), which is the phone case above;
* ``v`` says which snapshot the room is actually on, so a client that missed a
  broadcast finds out instead of sitting on stale state forever.

**This handler only diagnoses.** The cure is the client re-emitting
``enter_room``, which already re-attaches the socket and replays full state
through the per-game resync hook. Repairing from here as well would mean a
second restoration path to keep in step with the first, and two paths that must
agree are the thing this codebase keeps not having.

**Why a version rather than "resync every time".** Every room-wide broadcast is
numbered by ``sockets/audience.py``, which already funnels every emit and so
cannot forget to. A client that is genuinely up to date reports the current
number and costs one integer round trip; only one that actually missed something
pays for a re-entry. Numbering *every* room-wide emit — toasts and reactions
included — is deliberate: an allow-list of "real" state events is exactly the
kind of thing that drifts, and re-entering after a missed toast is harmless.
"""
from flask import request

from sockets.audience import version


def register(socketio, manager):

    @socketio.on("client_sync")
    def on_client_sync(data=None):
        """Answer a client heartbeat with a verdict on its state.

        The return value is the ack, and its arrival is the liveness signal, so
        this must answer on every path — including the ones where there is
        nothing wrong. A path that returns nothing would read as a dead socket
        and make a healthy client tear down a healthy connection.
        """
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")

        room = manager.get_room(code) if code else None
        if room is None or not user_id:
            # Still an ack: the socket is demonstrably alive, and "the room is
            # gone" is more useful to the client than silence.
            return {"ok": True, "room": False}

        player = room.players.get(user_id)
        if player is None:
            return {"ok": True, "room": False}

        return {
            "ok": True,
            "room": True,
            # This socket is not the one the room has on file, or the player is
            # marked absent — either way the client must re-enter to be seen.
            "stale": player.sid != request.sid or not player.connected,
            "v": version(room),
        }
