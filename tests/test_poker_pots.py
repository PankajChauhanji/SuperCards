import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker pots: main/side pot construction, folded money, uncalled bets, splits."""
from game.poker.pots import build_pots, uncalled_excess, split

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)

# ---- the worked example from docs/poker_rules.md ----
pots = build_pots({"A": 100_000, "B": 300_000, "C": 300_000}, folded=[])
check(pots == [
    {"amount": 300_000, "eligible": ["A", "B", "C"]},
    {"amount": 400_000, "eligible": ["B", "C"]},
], "rules-doc example: main 300,000 (A,B,C) + side 400,000 (B,C)")

# ---- no all-in -> one pot ----
check(build_pots({"A": 50, "B": 50, "C": 50}, []) == [{"amount": 150, "eligible": ["A", "B", "C"]}],
      "equal contributions make a single pot")

# ---- folded money stays in, folder never eligible ----
pots = build_pots({"A": 200, "B": 200, "C": 80}, folded=["C"])
check(pots == [{"amount": 480, "eligible": ["A", "B"]}],
      "a folder's 80 stays in the pot they reached; only A and B can win it")

# ---- several all-ins at different sizes ----
pots = build_pots({"A": 50, "B": 120, "C": 300, "D": 300}, folded=[])
check([p["amount"] for p in pots] == [200, 210, 360], "three pots for two different all-in sizes")
check([p["eligible"] for p in pots] == [["A", "B", "C", "D"], ["B", "C", "D"], ["C", "D"]],
      "each pot is contested by exactly the players who reached it")
check(sum(p["amount"] for p in pots) == 770, "pots add up to everything put in")

# ---- folded big contributor: their level merges into the pot below ----
pots = build_pots({"A": 100, "B": 300, "C": 300}, folded=["B"])
check(pots == [{"amount": 300, "eligible": ["A", "C"]}, {"amount": 400, "eligible": ["C"]}],
      "B folded after investing 300: side pot only C can win")
check(build_pots({"A": 0, "B": 0}, []) == [], "nothing in -> no pots")

# ---- uncalled bet ----
check(uncalled_excess({"A": 300, "B": 100, "C": 0}) == ("A", 200), "A's unmatched 200 returns to A")
check(uncalled_excess({"A": 300, "B": 300}) == (None, 0), "a matched top bet returns nothing")
check(uncalled_excess({"A": 0, "B": 0}) == (None, 0), "no bets, nothing to return")
check(uncalled_excess({"A": 50}) == ("A", 50), "a lone bet is entirely uncalled")

# ---- splits & the odd coin ----
check(split(300, ["A", "B"], ["A", "B", "C"]) == {"A": 150, "B": 150}, "even split")
check(split(301, ["B", "C"], ["C", "A", "B"]) == {"C": 151, "B": 150},
      "odd coin to the winner closest left of the button (first in seat order)")
check(split(100, ["A", "B", "C"], ["B", "C", "A"]) == {"B": 34, "C": 33, "A": 33},
      "a three-way split hands the leftover coin out clockwise")
check(split(100, [], ["A"]) == {}, "no winners, no payouts")

print("\n%d/%d pot checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
