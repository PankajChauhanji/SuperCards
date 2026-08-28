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


_RESYNCERS = {}


def register_resync(game_type: str, fn) -> None:
    """Register a per-game *complete state* send, addressed to one player.

    This is the reconnect/resync contract, and it exists because the shared
    layer must not know a variant's event vocabulary. ``sockets/lobby.py`` used
    to hardcode Super Seven's names (``round_start`` / ``round_end`` /
    ``game_end``) for every game — so a Super 4 client, whose bundle listens for
    ``s4_state`` / ``s4_round_end``, received either an event it ignores or, at
    STATE_ROUND_END, nothing at all. The result was a stale table that a full
    page reload could not repair, because the reload took the same dead branch.

    fn(room, user_id): emit everything that one player needs to repaint from
    scratch — public state, their private view, and any round/game-end overlay.
    It must be safe to call at any state and any number of times.
    """
    _RESYNCERS[game_type] = fn


def resync(room, user_id: str) -> bool:
    """Send one player the complete current state. False if the game has no hook."""
    fn = _RESYNCERS.get(room.game_type)
    if fn is None:
        return False
    fn(room, user_id)
    return True
