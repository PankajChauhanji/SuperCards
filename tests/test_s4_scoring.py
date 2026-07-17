import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super 4 scoring: card values (both red Kings=-1), hand totals, round-point deltas."""
from game.core.cards import Card
from game.super_four.scoring import card_value, hand_total, round_deltas
from game.super_four.settings import DEFAULT_SETTINGS

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

S = DEFAULT_SETTINGS  # win_score=-1, stop_loss_score=2, loss_score=1, penalty_score=4

# ---- card_value ----
check(card_value(Card(1, "S")) == 1, "Ace = 1")
check(card_value(Card(13, "S")) == 13, "King of Spades = 13")
check(card_value(Card(13, "D")) == -1, "King of Diamonds = -1 (red King)")
check(card_value(Card(13, "H")) == -1, "King of Hearts = -1")
check(card_value(None) == 0, "empty slot = 0")

# ---- hand_total ----
check(hand_total([Card(3, "S"), Card(4, "D"), None, Card(13, "H")]) == 6, "3+4+empty+KH(-1) = 6")

# ---- round_deltas: no caller -> nobody scores negative (risk-based) ----
r = round_deltas({"A": 3, "B": 9, "C": 12}, None, S)
check(r["winners"] == ["A"], "A has the lowest hand")
check(r["deltas"] == {"A": 1, "B": 1, "C": 1}, "no Stop call -> everyone +1, no -3")

# ---- caller wins: the only negative score; a won Stop inflates the table ----
r = round_deltas({"A": 3, "B": 9}, "A", S)
check(r["caller_won"] and r["deltas"] == {"A": -1, "B": 2}, "caller strictly lowest -> -1, other +2")

# ---- caller caught -> penalty +4; lowest hand gets NO reward ----
r = round_deltas({"A": 9, "B": 3, "C": 12}, "A", S)
check(not r["caller_won"], "caller A not lowest -> caught")
check(r["deltas"] == {"A": 4, "B": 1, "C": 1}, "caught caller +4, everyone else +1 (no reward without risk)")

# ---- tie for lowest, no caller: still everyone +1 ----
r = round_deltas({"A": 5, "B": 5, "C": 12}, None, S)
check(set(r["winners"]) == {"A", "B"}, "A and B tie for lowest")
check(r["deltas"] == {"A": 1, "B": 1, "C": 1}, "no caller -> all +1")

# ---- caller tied for lowest -> caught (must be STRICTLY lowest) ----
r = round_deltas({"A": 5, "B": 5, "C": 12}, "A", S)
check(not r["caller_won"] and r["deltas"] == {"A": 4, "B": 1, "C": 1},
      "caller tied-lowest -> caught (+4), others +1")

print("\n%d/%d Super 4 scoring checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
