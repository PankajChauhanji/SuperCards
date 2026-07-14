"""RoomManager: owns all rooms and their lifecycle.

Codes are unique 4-letter strings. Rooms with no connected players are reaped
lazily (on access) once they pass EMPTY_ROOM_TTL, so an abandoned create never
lingers forever.
"""
import random
import string
import time
from typing import Any, Dict, Optional

from config import ROOM_CODE_LENGTH, EMPTY_ROOM_TTL
from game.core import registry


class RoomManager:
    def __init__(self):
        # Values are game-specific Room instances; typed loosely so the manager
        # stays game-agnostic (see game.core.registry for the concrete classes).
        self.rooms: Dict[str, Any] = {}

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
        return room

    def get_room(self, code: str) -> Optional[Any]:
        return self.rooms.get(code)

    def remove_room(self, code: str) -> None:
        self.rooms.pop(code, None)

    def _reap_stale(self) -> None:
        now = time.time()
        stale = [
            code
            for code, room in self.rooms.items()
            if not room.any_human_connected() and (now - room.created_at) > EMPTY_ROOM_TTL
        ]
        for code in stale:
            self.rooms.pop(code, None)
