"""Pure move-validation logic — the heart of Super Seven.

No sockets, no room state: just "given these card ranks (and what's on the
table), what legal action is this, if any?". Kept dependency-free so it can be
unit-tested exhaustively.

Action inference priority (locked decision): when a selection qualifies as both
a no-draw combo (set/sequence) AND a match, it is treated as the combo, because
the player always prefers not to draw.
"""
from typing import List, Optional, Set

ACTION_SINGLE = "single"      # throw 1, draw 1
ACTION_PAIR = "pair"          # throw 2 of a rank, draw 1
ACTION_SET = "set"            # 3-4 of a rank, no draw
ACTION_SEQUENCE = "sequence"  # 3+ consecutive ranks, no draw
ACTION_MATCH = "match"        # ranks all in the current centre throw, draw 1

# Actions that oblige the player to draw a card afterwards.
DRAW_ACTIONS = {ACTION_SINGLE, ACTION_PAIR, ACTION_MATCH}
# Actions that put 3+ cards down without a draw.
COMBO_ACTIONS = {ACTION_SET, ACTION_SEQUENCE}


def is_set(ranks: List[int]) -> bool:
    """3 or 4 cards, all the same rank."""
    return len(ranks) in (3, 4) and len(set(ranks)) == 1


def is_sequence(ranks: List[int]) -> bool:
    """3+ cards forming a run of consecutive ranks.

    Ace is low only (A-2-3 valid; Q-K-A invalid, no wraparound) — which falls
    out naturally because Ace=1 and the run must be strictly consecutive
    integers with no duplicates.
    """
    if len(ranks) < 3:
        return False
    ordered = sorted(ranks)
    if len(set(ordered)) != len(ordered):  # no repeated ranks in a run
        return False
    return all(ordered[i] == ordered[i - 1] + 1 for i in range(1, len(ordered)))


def is_match(ranks: List[int], center_ranks: Set[int]) -> bool:
    """Every thrown rank appears in the current centre throw's rank set."""
    if not ranks or not center_ranks:
        return False
    return all(r in center_ranks for r in ranks)


def infer_action(ranks: List[int], center_ranks: Optional[Set[int]] = None) -> Optional[str]:
    """Classify a selection of card ranks into a legal action, or None.

    `ranks` is the list of rank integers for the selected cards (1=Ace..13=King).
    `center_ranks` is the rank set currently showing in the centre; a match may
    be played off whatever is there (matching is no longer limited to combos).

    Priority: a no-draw combo (set/sequence) is preferred over the equivalent
    draw plays, since the player would rather not draw.
    """
    n = len(ranks)
    if n == 0:
        return None
    if n == 1:
        # A single card that matches a rank in the centre is a Match (no draw
        # when MATCH_REQUIRES_DRAW is False), not a plain Single discard.
        if center_ranks and is_match(ranks, center_ranks):
            return ACTION_MATCH
        return ACTION_SINGLE

    # No-draw combos take priority.
    if is_set(ranks):
        return ACTION_SET
    if is_sequence(ranks):
        return ACTION_SEQUENCE

    # Match takes priority over pair when the rank is in the centre (free play).
    if center_ranks and is_match(ranks, center_ranks):
        return ACTION_MATCH

    # Two of a kind: a legal discard that still draws one.
    if n == 2 and len(set(ranks)) == 1:
        return ACTION_PAIR
    return None
