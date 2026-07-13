"""Pure round scoring for Super Seven.

A round ends when a player calls Stop (or, rarely, when every player has gone
safe). Scoring rules (locked):

  * Hand total = sum of card point values. A safe (0-card) player totals 0.
  * Caller strictly lowest (lower than all other NOT-SAFE players):
        caller scores max(total - win_discount, 0); others score their hand.
  * Caller caught (any other not-safe player's total <= caller's):
        caller scores total + stop_penalty; others score their hand.

This means that if a player is in the safe zone (score 0), their score is ignored
for the Stop calculation, allowing other players to still successfully call Stop.
"""
from typing import List, Optional, Tuple


def hand_total(cards) -> int:
    return sum(c.value for c in cards)


def score_round(
    participants: List[Tuple[str, list, bool]],
    caller_id: Optional[str],
    settings: dict,
) -> dict:
    """Compute per-player round scores.

    participants: list of (user_id, hand_cards, is_safe) for everyone dealt in.
    caller_id: who called Stop, or None for an auto-end (all players safe).
    Returns {"scores": {uid: pts}, "caught": bool, "totals": {uid: hand_total}}.
    """
    totals = {uid: hand_total(hand) for uid, hand, _ in participants}

    # Auto-end (no caller): everyone simply scores their hand (0 if safe).
    if caller_id is None:
        return {"scores": dict(totals), "caught": False, "totals": totals}

    is_safe_dict = {uid: is_safe for uid, _, is_safe in participants}
    caller_total = totals[caller_id]
    others_not_safe = [uid for uid in totals if uid != caller_id and not is_safe_dict[uid]]

    caller_wins = all(totals[o] > caller_total for o in others_not_safe)
    caught = not caller_wins

    scores = {}
    for uid, total in totals.items():
        if uid == caller_id:
            if caller_wins:
                scores[uid] = max(caller_total - settings["win_discount"], 0)
            else:
                scores[uid] = caller_total + settings["stop_penalty"]
        else:
            scores[uid] = total

    return {"scores": scores, "caught": caught, "totals": totals}
