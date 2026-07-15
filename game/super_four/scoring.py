"""Super 4 scoring.

Two layers:

* **Hand value** — a player's total of card values at reveal. Lowest hand wins the
  round. The King of Hearts (the "Red King") is worth -1; empty slots count 0.
* **Round points** — a game-level running score where LOWER is better. Each round
  the winner(s) get `win_score` (negative), a caught Stop caller gets
  `penalty_score` (positive), and every other active player gets `loss_score`.
  A player is eliminated once their cumulative reaches `exit_score`.
"""
from typing import Dict, List, Optional


def card_value(card) -> int:
    """Point value of a single card (or 0 for an empty slot / None)."""
    if card is None:
        return 0
    if card.rank == 13 and card.suit == "H":   # King of Hearts = the -1 Red King
        return -1
    return card.rank


def hand_total(cards) -> int:
    """Total of a player's slots; None entries (empty slots) count as 0."""
    return sum(card_value(c) for c in cards)


def round_deltas(totals: Dict[str, int], caller_id: Optional[str], settings: dict) -> dict:
    """Per-player round-score deltas for a finished round.

    Winner(s) = the strictly-lowest hand total (ties share the win). A caller who
    is not among the winners is "caught". Returns:
      {"deltas": {uid: int}, "winners": [uid], "caller_won": bool, "totals": {...}}
    """
    win = settings.get("win_score", -3)
    loss = settings.get("loss_score", 1)
    penalty = settings.get("penalty_score", 3)

    if not totals:
        return {"deltas": {}, "winners": [], "caller_won": False, "totals": {}}

    lowest = min(totals.values())
    winners = [uid for uid, t in totals.items() if t == lowest]
    winset = set(winners)
    caller_won = caller_id is not None and caller_id in winset

    deltas = {}
    for uid in totals:
        if uid in winset:
            deltas[uid] = win
        elif uid == caller_id:
            deltas[uid] = penalty      # called Stop but got caught
        else:
            deltas[uid] = loss
    return {"deltas": deltas, "winners": winners, "caller_won": caller_won, "totals": dict(totals)}
