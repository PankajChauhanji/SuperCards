"""Canonical game-lifecycle states, shared by every variant.

These four states are part of the Room interface (see room_base.RoomProtocol):
the shared socket layer (lobby, director, connection) branches on them, so every
game must drive its room through the same lifecycle vocabulary. Variant-specific
sub-states (e.g. Super Seven's owed-draw phase) stay inside the variant's room.
"""
STATE_LOBBY = "LOBBY"
STATE_IN_TURN = "IN_TURN"
STATE_ROUND_END = "ROUND_END"
STATE_GAME_END = "GAME_END"
