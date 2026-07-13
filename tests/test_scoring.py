import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Unit tests for game/scoring.py — no server needed."""
from game.core.cards import Card
from game.super_seven.scoring import hand_total, score_round

SETTINGS = {"win_discount": 5, "stop_penalty": 40, "max_score": 100, "timeout_limit": 3, "turn_timer": 40}
results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)


# hand_total: Ace=1, J=11, Q=12, K=13, numbers face value
check(hand_total([Card(1, "S"), Card(11, "H"), Card(13, "D")]) == 25, "hand total sums values (1+11+13)")
check(hand_total([]) == 0, "empty hand totals 0")

def hands_to_participants(d, safe=()):
    return [(uid, cards, uid in safe) for uid, cards in d.items()]

# ---- caller strictly lowest -> wins, discount applied ----
parts = hands_to_participants({
    "A": [Card(5, "S"), Card(3, "H")],        # 8
    "B": [Card(10, "S"), Card(2, "H")],       # 12
    "C": [Card(13, "S")],                     # 13
})
r = score_round(parts, "A", SETTINGS)
check(not r["caught"], "caller with strictly lowest total wins")
check(r["scores"]["A"] == 3, "winner scores total-5 (8-5=3)")
check(r["scores"]["B"] == 12 and r["scores"]["C"] == 13, "others score their hand totals")

# ---- winner discount floors at 0 ----
parts = hands_to_participants({"A": [Card(4, "S")], "B": [Card(13, "S")]})  # 4 vs 13
r = score_round(parts, "A", SETTINGS)
check(r["scores"]["A"] == 0, "winner with total below discount floors at 0 (4-5 -> 0)")

# ---- caught: another player ties the caller ----
parts = hands_to_participants({
    "A": [Card(5, "S"), Card(3, "H")],   # 8
    "B": [Card(5, "D"), Card(3, "C")],   # 8 (ties)
})
r = score_round(parts, "A", SETTINGS)
check(r["caught"], "a tie means the caller is caught")
check(r["scores"]["A"] == 48, "caught caller scores total+40 (8+40)")
check(r["scores"]["B"] == 8, "the tying player scores their hand")

# ---- caught: another player strictly lower ----
parts = hands_to_participants({
    "A": [Card(10, "S")],   # 10
    "B": [Card(4, "S")],    # 4 (lower)
})
r = score_round(parts, "A", SETTINGS)
check(r["caught"] and r["scores"]["A"] == 50, "caller beaten -> total+40 (10+40)")

# ---- Stop called with safe players present (ignored in comparison) ----
parts = hands_to_participants({
    "A": [Card(2, "S")],    # 2 (caller, lowest non-zero)
    "B": [],                # safe, 0 (ignored)
}, safe={"B"})
r = score_round(parts, "A", SETTINGS)
check(not r["caught"], "caller wins when they are the only non-safe player left")
check(r["scores"]["A"] == 0, "winner scores 0 (total 2 - discount 5 floors at 0)")
check(r["scores"]["B"] == 0, "safe player scores 0")

# ---- Stop called with 3 players, caller wins against remaining active player ----
parts = hands_to_participants({
    "A": [Card(2, "S")],    # 2 (caller)
    "B": [],                # safe, 0 (ignored)
    "C": [Card(5, "S")],    # active, 5
}, safe={"B"})
r = score_round(parts, "A", SETTINGS)
check(not r["caught"], "caller wins since 2 < 5 (safe player ignored)")
check(r["scores"]["A"] == 0, "winner scores 0")
check(r["scores"]["B"] == 0, "safe player scores 0")
check(r["scores"]["C"] == 5, "loser scores 5")

# ---- Stop called with 3 players, caller caught by remaining active player ----
parts = hands_to_participants({
    "A": [Card(6, "S")],    # 6 (caller)
    "B": [],                # safe, 0 (ignored)
    "C": [Card(5, "S")],    # active, 5
}, safe={"B"})
r = score_round(parts, "A", SETTINGS)
check(r["caught"], "caller is caught since 6 >= 5 (safe player ignored)")
check(r["scores"]["A"] == 46, "caught caller scores 6+40")
check(r["scores"]["B"] == 0, "safe player scores 0")
check(r["scores"]["C"] == 5, "other active player scores 5")

# ---- auto-end (everyone safe) ----
parts = hands_to_participants({"A": [], "B": []}, safe={"A", "B"})
r = score_round(parts, None, SETTINGS)
check(not r["caught"] and r["scores"] == {"A": 0, "B": 0}, "auto-end scores all safe players 0")

print("\n%d/%d scoring checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
