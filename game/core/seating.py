"""Seat shuffling — the host's "🔀 Shuffle seats" option, shared by every game.

Every variant builds its turn order from ``room.players`` in insertion order:
Super Seven, Super Four and Bluff at every ``start_round``, Poker when it seats
the table at the start of a game. So reordering that dict *just before* a round
is dealt is the whole feature — no game's rules, rotation or turn logic needs to
know it happened, and a host who never ticks the box gets exactly the old,
join-order seating.

The dict is reordered in place (``clear`` + ``update``) rather than rebound, so
anything already holding a reference to ``room.players`` still sees the room's
one roster. Player identity, colour and every per-player field are untouched;
only the order changes.

Callers (sockets/lobby.py at game start, a variant's next-round handler between
rounds) decide *when*; this module only does the shuffle and describes the
result. It imports no game.
"""
import random
from typing import List


def shuffle_seats(room, rng=random) -> List[dict]:
    """Shuffle the room's seating in place. Returns the new public order."""
    items = list(room.players.items())
    rng.shuffle(items)
    room.players.clear()
    room.players.update(items)
    return public_order(room)


def public_order(room) -> List[dict]:
    """Who sits where, in turn order — players at the table only.

    Names and ids only: seating is public by nature (everyone sees the seats),
    and this carries nothing hidden.
    """
    return [
        {"user_id": uid, "name": p.name}
        for uid, p in room.players.items()
        if not getattr(p, "is_spectator", False) and not getattr(p, "eliminated", False)
    ]
