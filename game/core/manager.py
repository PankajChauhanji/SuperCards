"""RoomManager: owns all rooms and their lifecycle.

Codes are unique 4-letter strings. Rooms with no connected players are reaped
lazily (on access) once they pass EMPTY_ROOM_TTL, so an abandoned create never
lingers forever.
"""
import random
import string
import time
from typing import Dict, Optional

from config import ROOM_CODE_LENGTH, EMPTY_ROOM_TTL
from game.super_seven.room import Room


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}

    def _generate_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=ROOM_CODE_LENGTH))
            if code not in self.rooms:
                return code

    def create_room(self, host_id: str, name: str, settings: dict) -> Room:
        self._reap_stale()
        code = self._generate_code()
        room = Room(code, host_id, settings)
        room.register_player(host_id, name)
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Optional[Room]:
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
