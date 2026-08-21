"""Connection lifecycle handlers.

Attachment to a room happens in lobby.enter_room, not here, so `connect` is a
no-op. `disconnect` resolves the sid back to a player and marks them offline —
but only if the disconnecting sid is still that player's current sid, which
avoids a stale page-unload socket knocking a freshly reconnected player offline.
"""
from flask import request
# Guarded drop-in for flask_socketio.emit — see sockets/audience.py.
from sockets.audience import emit

from sockets.common import unbind_sid


def register(socketio, manager):

    @socketio.on("connect")
    def on_connect():
        # Real attachment is driven by enter_room once the game page loads.
        pass

    @socketio.on("client_ping")
    def on_client_ping(_data=None):
        """Acknowledge a liveness probe. Deliberately touches no room state.

        A phone returning from the background holds a socket the CLIENT still
        believes is open — `socket.connected` is true while the transport is
        already dead. The client cannot detect that locally at all, so it asks
        instead: an ack that never arrives means the socket is a zombie and has to
        be torn down and rebuilt. Without this the player looks online to their own
        screen and offline to everyone else until a full page reload.
        """
        return {"ok": True}

    @socketio.on("disconnect")
    def on_disconnect():
        sid = request.sid
        entry = unbind_sid(sid)
        if not entry:
            return
        code, user_id = entry
        room = manager.get_room(code)
        if room is None:
            return
        player = room.players.get(user_id)
        if player is None:
            return
        # Ignore if the player has already re-attached on a newer socket.
        if player.sid != sid:
            return

        room.detach(user_id)

        if room.is_host(user_id):
            room.migrate_host()

        if not room.any_connected():
            # Keep the room briefly (TTL) so a quick refresh can rejoin;
            # the manager reaps it later if nobody comes back.
            return

        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )
