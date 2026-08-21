"""What Super 4 puts face-up, for everyone, right now.

Public: the centre discard (face-up by definition) and any one-shot public
reveal the rules produce (a failed match shows the card before it goes back).
Everything else — all four slots per player, the draw pile, and the card the
active player has just drawn — is secret.

Peeks (7/8/9/10, King) deliberately do NOT widen this set. They are private to
the acting player and are delivered by targeted one-shot events, so a peeked
card must never appear in a room-wide payload.
"""
from game.core.states import STATE_ROUND_END, STATE_GAME_END
from game.core.visibility import EVERYTHING


def public_card_ids(room):
    """Card ids every player may legitimately see in a room-wide payload."""
    if room.state in (STATE_ROUND_END, STATE_GAME_END):
        # Final reveal scores the round — every slot is turned over by design.
        return EVERYTHING
    ids = set()
    if room.center is not None:
        ids.add(room.center.id)
    for entry in room.transient_reveals or ():
        card = entry.get("card") if isinstance(entry, dict) else None
        if isinstance(card, dict) and card.get("id"):
            ids.add(card["id"])
    return ids
