import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Exhaustive unit tests for game/rules.py — no server needed."""
from game.super_seven.rules import (
    is_set, is_sequence, is_match, infer_action,
    ACTION_SINGLE, ACTION_PAIR, ACTION_SET, ACTION_SEQUENCE, ACTION_MATCH,
)

results = []
def check(ok, msg):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + msg)


# ---- is_set ----
check(is_set([8, 8, 8]), "three of a kind is a set")
check(is_set([13, 13, 13, 13]), "four of a kind is a set")
check(not is_set([8, 8]), "a pair is not a set (needs 3+)")
check(not is_set([8, 8, 8, 8, 8]), "five of a kind is not a set (max 4)")

# ---- is_sequence ----
check(is_sequence([4, 5, 6]), "4-5-6 is a sequence")
check(is_sequence([11, 12, 13]), "J-Q-K is a sequence")
check(is_sequence([1, 2, 3]), "A-2-3 is a sequence (Ace low)")
check(not is_sequence([1, 12, 13]), "Q-K-A is NOT a sequence (no wrap)")
check(not is_sequence([5, 5, 6]), "duplicate rank breaks a sequence")
check(is_sequence([6, 4, 5]), "order does not matter (unsorted input)")

# ---- is_match ----
check(is_match([3], {2, 3, 4}), "single rank present in center matches")
check(is_match([3, 4], {2, 3, 4}), "multiple present ranks match")
check(not is_match([5], {2, 3, 4}), "absent rank does not match")
check(not is_match([3], set()), "nothing matches an empty center")

# ---- infer_action: basics ----
check(infer_action([7]) == ACTION_SINGLE, "1 card -> single")
check(infer_action([7, 7, 7]) == ACTION_SET, "3 same -> set")
check(infer_action([5, 6, 7]) == ACTION_SEQUENCE, "run -> sequence")
check(infer_action([]) is None, "empty -> illegal")

# ---- pair rule (issue 7): two of a kind is legal and draws one ----
check(infer_action([7, 7]) == ACTION_PAIR, "two of a kind -> pair (draws one)")
check(infer_action([13, 13]) == ACTION_PAIR, "two kings is a legal pair (issue 8)")
check(infer_action([7, 7], {5, 6, 7}) == ACTION_MATCH,
      "two of a kind becomes a match when matchable")
check(infer_action([7, 8]) is None, "two different ranks with no center -> illegal")

# ---- match off the current center (issue 8): no longer combo-gated ----
check(infer_action([13, 13], {13}) == ACTION_MATCH,
      "two kings after a king is a match")
check(infer_action([7, 8], {7, 8, 9}) == ACTION_MATCH,
      "two distinct ranks both in center -> match")
check(infer_action([2, 4], {2, 3, 4}) == ACTION_MATCH,
      "can match a subset of a multi-rank center")
check(infer_action([3, 3, 4], {2, 3, 4}) == ACTION_MATCH,
      "can dump multiples of present ranks as a match")
check(infer_action([8, 9], {2, 3, 4}) is None,
      "ranks absent from the center -> illegal")

# ---- PRIORITY: no-draw combo beats the draw plays ----
check(infer_action([3, 3, 3], {2, 3, 4}) == ACTION_SET,
      "set takes priority over match (no-draw preferred)")
check(infer_action([2, 3, 4], {2, 3, 4}) == ACTION_SEQUENCE,
      "sequence takes priority over match")

print("\n%d/%d unit checks passed" % (sum(results), len(results)))
exit(0 if all(results) else 1)
