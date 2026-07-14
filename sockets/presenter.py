"""Per-game private-state presenter registry.

The shared lobby deals a round and broadcasts the public `round_start`, but the
*private* per-player payload is game-specific (Super Seven sends `your_hand`;
Super 4 sends `your_view` with only the cards that player legitimately knows).
Each variant registers a dealer here; the lobby calls `deal(room[, user_id])`
without knowing which game it is.
"""
_DEALERS = {}


def register(game_type: str, fn) -> None:
    """fn(room, user_id_or_None): emit the private deal to one/all players."""
    _DEALERS[game_type] = fn


def deal(room, user_id=None) -> None:
    fn = _DEALERS.get(room.game_type)
    if fn is not None:
        fn(room, user_id)
