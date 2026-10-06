"""Main pot, side pots and splitting them — pure functions over contributions.

Kept apart from the Room so the arithmetic that decides who gets paid can be
tested exhaustively on its own (tests/test_poker_pots.py). Nothing here knows
about turns, streets or cards.

Contributions are what each player has put in over the *whole round*. A folded
player's coins stay in the pots they reached; they are simply never eligible.
"""
from typing import Dict, Iterable, List, Sequence


def build_pots(contributed: Dict[str, int], folded: Iterable[str]) -> List[dict]:
    """Split the round's money into pots: ``[{"amount", "eligible": [uid...]}]``.

    One level per distinct contribution size. Each level collects, from every
    player, the slice of their contribution between the previous level and this
    one, and is contested by the live players who reached it. That is exactly
    "an all-in player can only win from each opponent what they put in".

    Adjacent levels with the same contestants are merged, so a round with no
    all-in produces one pot, not one per bet size. A level nobody live reached
    (possible only if a folder out-contributed every live player) is folded into
    the pot below it rather than left with no one to win it.
    """
    folded = set(folded)
    levels = sorted({amt for amt in contributed.values() if amt > 0})
    pots: List[dict] = []
    prev = 0
    for level in levels:
        amount = sum(min(amt, level) - min(amt, prev) for amt in contributed.values())
        eligible = sorted(
            uid for uid, amt in contributed.items()
            if amt >= level and uid not in folded
        )
        prev = level
        if amount <= 0:
            continue
        if not eligible:
            if pots:
                pots[-1]["amount"] += amount
            else:
                pots.append({"amount": amount, "eligible": []})
            continue
        if pots and pots[-1]["eligible"] == eligible:
            pots[-1]["amount"] += amount
        else:
            pots.append({"amount": amount, "eligible": eligible})
    return pots


def uncalled_excess(bets: Dict[str, int]):
    """The part of the top bet nobody matched: ``(uid, amount)`` or ``(None, 0)``.

    Uncalled money is returned to its owner, never won. Only a sole top bettor
    can have any; with a tie at the top, everything was matched.
    """
    ranked = sorted(bets.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] <= 0:
        return None, 0
    if len(ranked) == 1:
        return ranked[0][0], ranked[0][1]
    excess = ranked[0][1] - ranked[1][1]
    return (ranked[0][0], excess) if excess > 0 else (None, 0)


def split(amount: int, winners: Sequence[str], seat_order: Sequence[str]) -> Dict[str, int]:
    """Divide a pot equally; leftover coins go clockwise from the button.

    ``seat_order`` is the table order starting with the first seat after the
    button, so the odd coin lands on the tied winner closest to the button's
    left — the standard rule.
    """
    if not winners:
        return {}
    share, odd = divmod(amount, len(winners))
    payout = {uid: share for uid in winners}
    order = [uid for uid in seat_order if uid in payout]
    order += [uid for uid in winners if uid not in order]  # defensive: unseated winner
    for uid in order[:odd]:
        payout[uid] += 1
    return payout
