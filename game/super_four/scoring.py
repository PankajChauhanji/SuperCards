"""Super 4 scoring — lowest total wins.

Card values are face value (Ace=1 .. King=13) with one exception: the **King of
Hearts** (the "Red King") is worth **-1**, the best card in the game. Empty slots
(cards removed via matching) contribute 0. Penalty cards just add their own value
like any other card.
"""
from typing import Dict, Optional


def card_value(card) -> int:
    """Point value of a single card (or 0 for an empty slot / None)."""
    if card is None:
        return 0
    # Only the King of Hearts is the -1 "Red King" (see DESIGN.md).
    if card.rank == 13 and card.suit == "H":
        return -1
    return card.rank


def hand_total(cards) -> int:
    """Total of a player's slots; None entries (empty slots) count as 0."""
    return sum(card_value(c) for c in cards)


def resolve_stop(totals: Dict[str, int], caller_id: Optional[str]) -> dict:
    """Determine the round outcome.

    totals: {user_id: hand_total} for everyone dealt in.
    caller_id: who declared Stop (or None for an auto-end).

    The overall winner is always the strictly-lowest total (None on a tie for
    lowest). When there is a caller, `caller_won` is True iff the caller is that
    strict winner. Returns {"winner": uid|None, "caller_won": bool, "totals": ...}.
    """
    winner = None
    if totals:
        lowest = min(totals.values())
        low_players = [uid for uid, t in totals.items() if t == lowest]
        if len(low_players) == 1:
            winner = low_players[0]

    caller_won = caller_id is not None and winner == caller_id
    return {"winner": winner, "caller_won": caller_won, "totals": dict(totals)}
