import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker hand evaluator: every category, kickers, the wheel, ties and the board playing."""
from game.core.cards import Card
from game.poker.evaluator import (
    evaluate, HIGH_CARD, ONE_PAIR, TWO_PAIR, THREE_OF_A_KIND, STRAIGHT, FLUSH,
    FULL_HOUSE, FOUR_OF_A_KIND, STRAIGHT_FLUSH,
)

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)

_R = {"A": 1, "J": 11, "Q": 12, "K": 13}


def cards(text):
    """'AS KH 10D' -> [Card...]; copy numbers keep duplicates distinct across tests."""
    out = []
    for tok in text.split():
        rank, suit = tok[:-1], tok[-1]
        out.append(Card(_R.get(rank) or int(rank), suit))
    return out


def ev(text):
    return evaluate(cards(text))


# ---- every category ----
CASES = [
    ("AS KS QS JS 10S 2D 3C", STRAIGHT_FLUSH, "Royal Flush"),
    ("9H 8H 7H 6H 5H KD 2C", STRAIGHT_FLUSH, "Straight Flush, 9 high"),
    ("QC QD QH QS 4D 2C 3H", FOUR_OF_A_KIND, "Four of a Kind, Queens"),
    ("8S 8D 8H KC KS 2D 3C", FULL_HOUSE, "Full House, Eights over Kings"),
    ("AD JD 9D 6D 2D KC 3S", FLUSH, "Flush, Ace high"),
    ("10C 9D 8S 7H 6C 2D KS", STRAIGHT, "Straight, 10 high"),
    ("7C 7D 7S KH 2D 9C 4S", THREE_OF_A_KIND, "Three of a Kind, Sevens"),
    ("JH JC 4S 4D AC 9H 2S", TWO_PAIR, "Two Pair, Jacks and Fours"),
    ("10S 10H KD 6C 3S 2D 8H", ONE_PAIR, "One Pair, Tens"),
    ("AC QD 8S 5H 3C 2D 9S", HIGH_CARD, "High Card, Ace"),
]
for text, cat, name in CASES:
    h = ev(text)
    check(h.category == cat and h.name == name, "%s -> %s (%s)" % (text, name, h.name))
    check(len(h.cards) == 5, "%s -> exactly five cards make the hand" % name)

# Higher categories beat lower ones, all the way down the table.
values = [ev(t).value for t, _, _ in CASES]
check(all(values[i] > values[i + 1] for i in range(len(values) - 1)),
      "the ten example hands are strictly ordered strongest to weakest")

# ---- aces: high, low only in the wheel, no wrap-around ----
wheel = ev("AS 2D 3C 4H 5S KD 9C")
check(wheel.category == STRAIGHT and wheel.value == (STRAIGHT, 5), "A-2-3-4-5 is a 5-high straight")
six_high = ev("2D 3C 4H 5S 6D AS KH")
check(six_high.value > wheel.value, "6-high straight beats the wheel")
check(ev("AS KD QC JH 10S 2C 3D").value == (STRAIGHT, 14), "A-K-Q-J-10 is an Ace-high straight")
check(ev("QS KD AC 2H 3S 8C 9D").category == HIGH_CARD, "Q-K-A-2-3 does not wrap into a straight")
steel = ev("AH 2H 3H 4H 5H 9C KD")
check(steel.value == (STRAIGHT_FLUSH, 5), "A-2-3-4-5 suited is a 5-high straight flush")

# ---- kickers ----
check(ev("KS KD AH 7C 3S 2D 4C").value > ev("KH KC QH 7D 3C 2S 4H").value,
      "pair of Kings with an Ace kicker beats Kings with a Queen")
check(ev("9S 9D 5H 5C AS 2D 3C").value > ev("9H 9C 5S 5D KS 2H 3D").value,
      "two pair decided by the fifth card")
check(ev("JS JD 4H 4C 2S 2D AC").value == (TWO_PAIR, 11, 4, 14),
      "with three pairs the third pair never counts but its rank can't beat an Ace kicker")
check(ev("JS JD 4H 4C 3S 3D 2C").value == (TWO_PAIR, 11, 4, 3),
      "with three pairs the third pair's rank can be the kicker")
check(ev("7C 7D 7S 7H AD KC QS").value == (FOUR_OF_A_KIND, 7, 14), "quads take the best kicker")
check(ev("7C 7D 7S 2H 2D KC KS").value == (FULL_HOUSE, 7, 13),
      "full house uses the higher of two pairs")
check(ev("7C 7D 7S 9H 9D 9C 2S").value == (FULL_HOUSE, 9, 7),
      "two sets of three make the full house from the higher three")
check(ev("AH 9H 7H 5H 3H 2H KC").value[:3] == (FLUSH, 14, 9),
      "six of a suit -> flush uses the five highest")

# ---- suits never break a tie; equal hands split ----
check(ev("AS KS QS 9S 2S 3D 4C").value == ev("AH KH QH 9H 2H 3C 4D").value,
      "a spade flush and a heart flush of the same ranks are equal")
board = "AS KD QC JH 10S"
check(evaluate(cards("2C 3D") + cards(board)).value
      == evaluate(cards("4H 5S") + cards(board)).value,
      "board straight plays for both players -> split")

# ---- five or six cards (flop and turn) evaluate too ----
check(ev("AS AD KC 5H 2S").category == ONE_PAIR, "five cards (the flop) evaluate")
check(ev("AS AD KC 5H 2S 5C").category == TWO_PAIR, "six cards (the turn) evaluate")
try:
    ev("AS KD QC")
    check(False, "fewer than five cards is rejected")
except ValueError:
    check(True, "fewer than five cards is rejected")

print("\n%d/%d evaluator checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
