"""Cards: model, deck construction, point values.

By default a card's point value equals its rank number (Ace=1, 2-10 face value,
Jack=11, Queen=12, King=13) — this is Super Seven's scoring and stays the default.
The `id` is a compact rank+suit code (e.g. "7H", "AS", "10C", "KD") and doubles as
the SVG image filename: /static/img/cards/<id>.svg.

Per-variant valuation
---------------------
`card_value` is suit-aware-capable (it accepts an optional suit) so a game can
value cards differently — e.g. Super 4 makes the Red King (KH/KD) worth -1. A
variant does this in its OWN scoring module, not by mutating global state here:
because one process hosts every game simultaneously, valuation must never be a
shared/global setting. The default below is intentionally suit-independent.

    # game/super_four/scoring.py
    from game.core.cards import RED_SUITS
    def card_value(card):
        if card.rank == 13 and card.suit in RED_SUITS:
            return -1
        return card.rank
"""
import random
from typing import List, Optional

SUITS = ("S", "H", "D", "C")
RANKS = list(range(1, 14))          # 1=Ace ... 13=King
RED_SUITS = {"H", "D"}

_RANK_CODE = {1: "A", 11: "J", 12: "Q", 13: "K"}
for _n in range(2, 11):
    _RANK_CODE[_n] = str(_n)


def rank_code(rank: int) -> str:
    return _RANK_CODE[rank]


def card_value(rank: int, suit: Optional[str] = None) -> int:
    """Default point value: the rank number, suit-independent (Super Seven).

    `suit` is accepted so variants can call/override with a suit-aware rule
    (see the module docstring); the default ignores it.
    """
    return rank


class Card:
    __slots__ = ("rank", "suit", "copy")

    def __init__(self, rank: int, suit: str, copy: int = 0):
        self.rank = rank
        self.suit = suit
        self.copy = copy            # which deck this card came from (0-based)

    @property
    def face(self) -> str:
        """Rank+suit code — the image basename. NOT unique across decks."""
        return f"{rank_code(self.rank)}{self.suit}"

    @property
    def id(self) -> str:
        """Stable, unique handle for one physical card (unique across decks)."""
        return f"{self.face}#{self.copy}"

    @property
    def value(self) -> int:
        return card_value(self.rank)

    def to_dict(self) -> dict:
        return {
            "id": self.id,      # unique per physical card (selection / dedup)
            "face": self.face,  # image basename: /static/img/cards/<face>.svg
            "rank": self.rank,
            "suit": self.suit,
            "code": rank_code(self.rank),
            "value": self.value,
            "red": self.suit in RED_SUITS,
        }

    def __repr__(self) -> str:
        return f"Card({self.id})"


def build_deck(num_decks: int = 1) -> List[Card]:
    """Build one or more standard 52-card decks combined into one pile."""
    return [
        Card(rank, suit, d)
        for d in range(max(1, num_decks))
        for suit in SUITS
        for rank in RANKS
    ]


def shuffled_deck(num_decks: int = 1) -> List[Card]:
    deck = build_deck(num_decks)
    random.shuffle(deck)
    return deck
