"""Super 4 scoring.

Two layers:

* **Hand value** — a player's total of card values at reveal. Lowest hand wins the
  round. Both red Kings (Hearts and Diamonds) are worth -1; empty slots count 0.
* **Round points** — a game-level running score where LOWER is better. Risk-based:
  the ONLY negative delta is a winning Stop caller's `win_score`, and a won Stop
  also inflates everyone else by `stop_loss_score` (> the routine `loss_score`),
  pushing the passive players toward `exit_score`. A caught caller gets
  `penalty_score`; a low hand earns nothing without the risk of calling Stop.
  A player is eliminated once their cumulative reaches `exit_score`.
"""
from typing import Dict, List, Optional

from game.core.cards import RED_SUITS


def card_value(card) -> int:
    """Point value of a single card (or 0 for an empty slot / None)."""
    if card is None:
        return 0
    if card.rank == 13 and card.suit in RED_SUITS:
        return -1
    return card.rank


def hand_total(cards) -> int:
    """Total of a player's slots; None entries (empty slots) count as 0."""
    return sum(card_value(c) for c in cards)


def round_deltas(totals: Dict[str, int], caller_id: Optional[str], settings: dict) -> dict:
    """Per-player round-score deltas for a finished round.

    Risk-based: the only way to score negative is to call Stop and WIN.
      * Caller with the STRICTLY-lowest hand (a tie = caught): `win_score`, and
        everyone else takes `stop_loss_score` — a won Stop pressures the table.
      * Caught caller: `penalty_score`; everyone else takes the routine `loss_score`.
      * No caller at all (e.g. deck-out): every active player gets `loss_score` —
        the lowest hand earns nothing without the risk of a call.
    `winners` still lists the lowest hand(s), for display only. Returns:
      {"deltas": {uid: int}, "winners": [uid], "caller_won": bool, "totals": {...}}
    """
    win = settings.get("win_score", -1)
    stop_loss = settings.get("stop_loss_score", 2)
    loss = settings.get("loss_score", 1)
    penalty = settings.get("penalty_score", 4)

    if not totals:
        return {"deltas": {}, "winners": [], "caller_won": False, "totals": {}}

    lowest = min(totals.values())
    winners = [uid for uid, t in totals.items() if t == lowest]
    caller_won = caller_id is not None and winners == [caller_id]

    deltas = {}
    for uid in totals:
        if uid == caller_id:
            deltas[uid] = win if caller_won else penalty
        else:
            deltas[uid] = stop_loss if caller_won else loss
    return {"deltas": deltas, "winners": winners, "caller_won": caller_won, "totals": dict(totals)}
