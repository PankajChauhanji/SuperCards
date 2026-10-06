"""Hold'em hand evaluator: the best five cards out of five to seven.

``evaluate(cards)`` returns a ``Hand`` whose ``value`` is a plain tuple —
``(category, tiebreak...)`` — so comparing two hands is comparing two tuples, and
equal tuples are a genuine split. Suits never appear in ``value``: they decide
whether a hand is a flush, never which flush is better.

The shared ``game.core.cards`` stores an Ace as rank 1 (Super Seven scores it as
1 point). Poker needs it high, and low only in the A-2-3-4-5 straight, so that
mapping happens here and nowhere else — the core is not touched.

A direct seven-card evaluation rather than scoring all 21 five-card combinations:
the bot's Monte Carlo estimate (ai.py) calls this thousands of times per decision
on a single-worker server, so the extra speed is worth having.
"""
from collections import Counter
from typing import List, NamedTuple, Optional, Tuple

# ---- categories (higher beats lower) ----
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    ONE_PAIR: "One Pair",
    TWO_PAIR: "Two Pair",
    THREE_OF_A_KIND: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    FOUR_OF_A_KIND: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}

ACE_HIGH = 14

_SINGULAR = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "Jack", 12: "Queen", 13: "King", 14: "Ace",
}
_PLURAL = {
    2: "Twos", 3: "Threes", 4: "Fours", 5: "Fives", 6: "Sixes", 7: "Sevens",
    8: "Eights", 9: "Nines", 10: "Tens", 11: "Jacks", 12: "Queens", 13: "Kings",
    14: "Aces",
}


class Hand(NamedTuple):
    value: Tuple[int, ...]   # (category, tiebreak...) — compare these
    cards: List              # the five Card objects that make the hand
    name: str                # e.g. "Full House, Kings over Sevens"

    @property
    def category(self) -> int:
        return self.value[0]


def poker_rank(card) -> int:
    """Ace-high rank: 2..14."""
    return ACE_HIGH if card.rank == 1 else card.rank


def _straight_top(ranks) -> Optional[int]:
    """Highest top card of five in a row among ``ranks`` (a set of 2..14), or None.

    The Ace also plays low, so the wheel A-2-3-4-5 is a straight with top card 5.
    It cannot wrap: Q-K-A-2-3 is not a straight.
    """
    present = set(ranks)
    if ACE_HIGH in present:
        present.add(1)
    for top in range(ACE_HIGH, 4, -1):
        if all((top - i) in present for i in range(5)):
            return top
    return None


def _straight_cards(cards, top: int) -> List:
    """One card for each rank top..top-4 (the Ace standing in for 1 in a wheel)."""
    out = []
    for r in range(top, top - 5, -1):
        want = ACE_HIGH if r == 1 else r
        out.append(next(c for c in cards if poker_rank(c) == want))
    return out


def _take(cards, rank: int, n: int, used: set) -> List:
    """Take n not-yet-used cards of ``rank``, marking them used."""
    picked = []
    for c in cards:
        if len(picked) == n:
            break
        if id(c) not in used and poker_rank(c) == rank:
            picked.append(c)
            used.add(id(c))
    return picked


def _kickers(cards, n: int, used: set) -> List:
    """The n highest cards not already used."""
    rest = [c for c in cards if id(c) not in used]
    rest.sort(key=poker_rank, reverse=True)
    return rest[:n]


def evaluate(cards) -> Hand:
    """Best five-card hand from 5..7 cards."""
    cards = list(cards)
    if not 5 <= len(cards) <= 7:
        raise ValueError("evaluate() needs 5 to 7 cards, got %d" % len(cards))
    ordered = sorted(cards, key=poker_rank, reverse=True)

    # ---- flush / straight flush ----
    by_suit = {}
    for c in ordered:
        by_suit.setdefault(c.suit, []).append(c)
    flush_cards = next((v for v in by_suit.values() if len(v) >= 5), None)
    if flush_cards:
        top = _straight_top({poker_rank(c) for c in flush_cards})
        if top is not None:
            five = _straight_cards(flush_cards, top)
            name = "Royal Flush" if top == ACE_HIGH else "Straight Flush, %s high" % _SINGULAR[top]
            return Hand((STRAIGHT_FLUSH, top), five, name)

    counts = Counter(poker_rank(c) for c in ordered)
    # Ranks grouped by how many of each, highest rank first within a group.
    quads = sorted((r for r, n in counts.items() if n == 4), reverse=True)
    trips = sorted((r for r, n in counts.items() if n == 3), reverse=True)
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    used = set()

    if quads:
        q = quads[0]
        five = _take(ordered, q, 4, used) + _kickers(ordered, 1, used)
        return Hand((FOUR_OF_A_KIND, q, poker_rank(five[4])), five,
                    "Four of a Kind, %s" % _PLURAL[q])

    if trips and (len(trips) >= 2 or pairs):
        t = trips[0]
        # A second set of three can supply the pair, and may outrank every pair.
        p = max(([trips[1]] if len(trips) >= 2 else []) + pairs)
        five = _take(ordered, t, 3, used) + _take(ordered, p, 2, used)
        return Hand((FULL_HOUSE, t, p), five,
                    "Full House, %s over %s" % (_PLURAL[t], _PLURAL[p]))

    if flush_cards:
        five = flush_cards[:5]
        return Hand((FLUSH,) + tuple(poker_rank(c) for c in five), five,
                    "Flush, %s high" % _SINGULAR[poker_rank(five[0])])

    top = _straight_top(counts)
    if top is not None:
        return Hand((STRAIGHT, top), _straight_cards(ordered, top),
                    "Straight, %s high" % _SINGULAR[top])

    if trips:
        t = trips[0]
        five = _take(ordered, t, 3, used) + _kickers(ordered, 2, used)
        return Hand((THREE_OF_A_KIND, t) + tuple(poker_rank(c) for c in five[3:]), five,
                    "Three of a Kind, %s" % _PLURAL[t])

    if len(pairs) >= 2:
        hi, lo = pairs[0], pairs[1]
        # A third pair is not part of the hand; its rank can still be the kicker.
        five = _take(ordered, hi, 2, used) + _take(ordered, lo, 2, used) + _kickers(ordered, 1, used)
        return Hand((TWO_PAIR, hi, lo, poker_rank(five[4])), five,
                    "Two Pair, %s and %s" % (_PLURAL[hi], _PLURAL[lo]))

    if pairs:
        p = pairs[0]
        five = _take(ordered, p, 2, used) + _kickers(ordered, 3, used)
        return Hand((ONE_PAIR, p) + tuple(poker_rank(c) for c in five[2:]), five,
                    "One Pair, %s" % _PLURAL[p])

    five = ordered[:5]
    return Hand((HIGH_CARD,) + tuple(poker_rank(c) for c in five), five,
                "High Card, %s" % _SINGULAR[poker_rank(five[0])])
