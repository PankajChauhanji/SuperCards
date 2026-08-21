"""What Bluff puts face-up, for everyone, right now.

The answer during play is: **nothing**. Every card played goes face down, the
centre pile stays face down, and the dead pile is discarded face down. That
makes the public set empty — the strictest oracle of the three games, and
rightly so: a player who could see the pile would win every Show call, which
does not merely help them, it solves the game.

The one intentional exposure is a Show, which flips exactly the cards of the
challenged play. That travels as its own event (``bluff_show_result``) and is
allowlisted in sockets/audience.py rather than widened into this set, so the
buried pile stays protected even mid-reveal.
"""
from game.core.states import STATE_ROUND_END, STATE_GAME_END
from game.core.visibility import EVERYTHING


def public_card_ids(room):
    """Card ids every player may legitimately see in a room-wide payload."""
    if room.state in (STATE_ROUND_END, STATE_GAME_END):
        return EVERYTHING
    return set()
