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
        """Acknowledge a bare liveness probe, for clients running older JS.

        Superseded by ``client_sync`` (sockets/sync.py), which answers the same
        question and also reports whether the client's state is current. This
        stays because the service worker serves JavaScript stale-while-revalidate:
        for one page load after a deploy, a returning player is still running the
        previous bundle. If that bundle's probe went unanswered it would conclude
        its socket was dead and rebuild it on a loop — the failure it was written
        to prevent. Removable once no deployed client emits it.
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
