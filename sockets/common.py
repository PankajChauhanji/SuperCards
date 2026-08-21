"""Shared socket helpers.

SID_INDEX maps a live socket id -> (room_code, user_id). Only sockets that have
actually entered a room (via `enter_room`) are indexed, so a disconnect can be
resolved back to a player. This is what lets reconnection key off the stable
user_id instead of the volatile sid.
"""
from typing import Optional, Tuple

# Guarded drop-in for flask_socketio.emit — see sockets/audience.py. This
# module only emits errors to the requesting socket, but routing every
# emit through one place is what keeps the guard total.
from sockets.audience import emit

SID_INDEX = {}  # sid -> (code, user_id)


def bind_sid(sid: str, code: str, user_id: str) -> None:
    SID_INDEX[sid] = (code, user_id)


def unbind_sid(sid: str) -> Optional[Tuple[str, str]]:
    return SID_INDEX.pop(sid, None)


def error(message: str) -> None:
    """Reply to the current requester with a standard error event."""
    emit("error", {"message": message})
