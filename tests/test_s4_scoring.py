import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 scoring: card values (KH=-1), hand totals, Stop resolution."""
from game.core.cards import Card
from game.super_four.scoring import card_value, hand_total, resolve_stop

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

# ---- card_value ----
check(card_value(Card(1, "S")) == 1, "Ace of Spades = 1")
check(card_value(Card(10, "D")) == 10, "10 of Diamonds = 10")
check(card_value(Card(11, "C")) == 11, "Jack = 11")
check(card_value(Card(12, "H")) == 12, "Queen = 12")
check(card_value(Card(13, "S")) == 13, "King of Spades = 13")
check(card_value(Card(13, "D")) == 13, "King of Diamonds = 13 (NOT the red king)")
check(card_value(Card(13, "H")) == -1, "King of Hearts = -1 (the Red King)")
check(card_value(None) == 0, "empty slot = 0")

# ---- hand_total ----
check(hand_total([Card(3, "S"), Card(4, "D"), None, Card(13, "H")]) == 6,
      "3+4+empty+KH(-1) = 6")
check(hand_total([None, None, None, None]) == 0, "all-empty hand = 0")

# ---- resolve_stop ----
r = resolve_stop({"A": 5, "B": 9, "C": 12}, "A")
check(r["winner"] == "A" and r["caller_won"], "caller A strictly lowest -> wins")

r = resolve_stop({"A": 9, "B": 5, "C": 12}, "A")
check(r["winner"] == "B" and not r["caller_won"], "caller A not lowest -> caught, B wins")

r = resolve_stop({"A": 5, "B": 5, "C": 12}, "A")
check(r["winner"] is None and not r["caller_won"], "tie for lowest incl caller -> caller loses, no unique winner")

r = resolve_stop({"A": 7, "B": 3, "C": 3}, None)
check(r["winner"] is None and not r["caller_won"], "auto-end tie for lowest -> no unique winner")

r = resolve_stop({"A": 7, "B": 2, "C": 9}, None)
check(r["winner"] == "B", "auto-end: strictly lowest B wins")

print("\n%d/%d Super 4 scoring checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
