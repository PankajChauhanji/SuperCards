"""Super 4 card powers — pure metadata / targeting.

Powers trigger ONLY when a drawn card is immediately discarded (see room.discard),
and using one is always OPTIONAL — the acting player may skip it (room.power_skip).
This module classifies a rank into its power kind and describes what target the
power needs; the actual state mutation lives on the Room (power_* methods) so slot
and knowledge updates stay in one place.

    7 or 8   -> peek_own     : look at one of your own cards
    9 or 10  -> peek_opp     : look at one opponent card
    11 or 12 -> blind_swap   : swap one of yours with an opponent's (no reveal)
    13 King  -> king         : look at one of yours + one opponent's, then optionally swap
"""

PEEK_OWN = "peek_own"
PEEK_OPP = "peek_opp"
BLIND_SWAP = "blind_swap"
KING = "king"

_KIND_BY_RANK = {
    7: PEEK_OWN, 8: PEEK_OWN,
    9: PEEK_OPP, 10: PEEK_OPP,
    11: BLIND_SWAP, 12: BLIND_SWAP,
    13: KING,
}

_LABELS = {
    PEEK_OWN: "Look at one of your own cards",
    PEEK_OPP: "Look at one opponent's card",
    BLIND_SWAP: "Blind-swap one of your cards with an opponent's",
    KING: "Look at one of yours and one opponent's, then optionally swap",
}


def power_kind(rank: int):
    """Return the power kind for a rank, or None if the rank has no power."""
    return _KIND_BY_RANK.get(rank)


def power_label(rank: int) -> str:
    return _LABELS.get(power_kind(rank), "")


def needs_opponent(rank: int) -> bool:
    """peek_opp / blind_swap / king all require an opponent target."""
    return power_kind(rank) in (PEEK_OPP, BLIND_SWAP, KING)
