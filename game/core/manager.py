"""RoomManager: owns all rooms and their lifecycle.

Codes are unique 4-letter strings. Rooms with no connected humans are reaped
lazily (on access) once they have been empty for EMPTY_ROOM_TTL, so an abandoned
create never lingers forever.

Note "have been empty for", not "are older than". The reaper used to compare the
TTL against ``room.created_at``, which is the room's *age* — so a game that had
been running for ten minutes was eligible for deletion the instant its players
were all momentarily disconnected, with no grace at all. On phones that is not
an edge case: a backgrounded tab loses its transport routinely, and every player
in a two-person room can be offline for a few seconds at once. The next
``create_room`` by any unrelated user then destroyed their game.
"""
import random
import string
import time
from typing import Any, Dict, Optional

from config import ROOM_CODE_LENGTH, EMPTY_ROOM_TTL
from game.core import registry, store


class RoomManager:
    def __init__(self, restore: bool = False):
        # Values are game-specific Room instances; typed loosely so the manager
        # stays game-agnostic (see game.core.registry for the concrete classes).
        self.rooms: Dict[str, Any] = {}
        # code -> time the room was first observed with no human connected.
        # Kept here rather than on the Room so no game has to maintain it, and
        # so a room restored from a snapshot starts its grace period fresh.
        self._empty_since: Dict[str, float] = {}
        if restore:
            # Rooms from a previous process, if that process ran this same code.
            # Off by default so tests and tools get a clean manager; app.py opts in.
            self.rooms.update(store.load())

    def snapshot(self) -> bool:
        """Persist the current rooms so a restart does not end live games."""
        return store.save(self.rooms)

    def _generate_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=ROOM_CODE_LENGTH))
            if code not in self.rooms:
                return code

    def create_room(
        self,
        host_id: str,
        name: str,
        settings: dict,
        game_type: str = registry.DEFAULT_GAME,
    ) -> Any:
        """Create a room for the given game variant.

        Raises ValueError if game_type is not registered — callers (the lobby
        handlers) validate/translate this into a user-facing error.
        """
        spec = registry.get(game_type)
        if spec is None:
            raise ValueError(f"Unknown game_type: {game_type!r}")
        self._reap_stale()
        code = self._generate_code()
        room = spec.room_class(code, host_id, settings)
        room.game_type = game_type
        room.register_player(host_id, name)
        self.rooms[code] = room
        # A room nobody has entered yet is empty from birth — that is the
        # abandoned-create the reaper was written for. The clock is reset the
        # moment a human actually connects.
        self._empty_since[code] = room.created_at
        return room

    def get_room(self, code: str) -> Optional[Any]:
        return self.rooms.get(code)

    def remove_room(self, code: str) -> None:
        self.rooms.pop(code, None)
        self._empty_since.pop(code, None)

    def _reap_stale(self) -> None:
        """Drop rooms that have had no human connected for longer than the TTL.

        The clock starts when a room is first *seen* empty and resets the moment
        anyone comes back, so a transient disconnect can never cost a live game.
        A room nobody has ever joined counts as empty from its creation, which is
        the abandoned-create case the reaper was written for.
        """
        now = time.time()
        for code, room in list(self.rooms.items()):
            if room.any_human_connected():
                self._empty_since.pop(code, None)
                continue
            since = self._empty_since.setdefault(code, now)
            if (now - since) > EMPTY_ROOM_TTL:
                self.rooms.pop(code, None)
                self._empty_since.pop(code, None)
