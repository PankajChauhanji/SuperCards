"""What Super Seven puts face-up, for everyone, right now.

Single source of truth for "publicly visible card" — consumed by both the
runtime emit guard (sockets/audience.py) and the leak fuzzer
(tests/test_leak_fuzz.py), so the rule cannot drift between the two.

Super Seven's only public faces are the current centre throw. Hands and the
draw pile are secret; the previous throw is buried in the discard pile and is no
longer visible either.
"""
from game.core.states import STATE_ROUND_END, STATE_GAME_END
from game.core.visibility import EVERYTHING


def public_card_ids(room):
    """Card ids every player may legitimately see in a room-wide payload."""
    if room.state in (STATE_ROUND_END, STATE_GAME_END):
        # Round end reveals every hand for scoring — by design, not a leak.
        return EVERYTHING
    return {c.id for c in room.center_throw}
