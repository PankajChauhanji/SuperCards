"""Per-game private-state presenter registry.

The shared lobby deals a round and broadcasts the public `round_start`, but the
*private* per-player payload is game-specific (Super Seven sends `your_hand`;
Super 4 sends `your_view` with only the cards that player legitimately knows).
Each variant registers a dealer here; the lobby calls `deal(room[, user_id])`
without knowing which game it is.
"""
_DEALERS = {}
_REFRESHERS = {}


def register(game_type: str, fn) -> None:
    """fn(room, user_id_or_None): emit the private deal to one/all players."""
    _DEALERS[game_type] = fn


def deal(room, user_id=None) -> None:
    fn = _DEALERS.get(room.game_type)
    if fn is not None:
        fn(room, user_id)


def register_refresh(game_type: str, fn) -> None:
    """Register a per-game re-broadcast of the current public state.

    Used after a structural change that isn't a normal turn action (e.g. a player
    quitting mid-game), so remaining clients re-sync turn order / scores / round
    or game end. fn(room) emits the variant's own snapshot event(s) to the room.
    """
    _REFRESHERS[game_type] = fn


def refresh(room) -> None:
    fn = _REFRESHERS.get(room.game_type)
    if fn is not None:
        fn(room)
