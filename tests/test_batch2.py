import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game.core.cards import build_deck, shuffled_deck, Card
from game.super_seven.room import Room

results = []
def check(ok, msg):
    results.append(ok); print(("PASS " if ok else "FAIL ") + msg)

# ---- deck construction ----
check(len(build_deck(1)) == 52, "1 deck = 52 cards")
check(len(build_deck(2)) == 104, "2 decks = 104 cards")
check(len(shuffled_deck(3)) == 156, "3 decks = 156 cards")

d2 = build_deck(2)
ids = [c.id for c in d2]
check(len(set(ids)) == 104, "every physical card has a unique id across decks")
check(len({c.face for c in d2}) == 52, "only 52 distinct faces (image basenames)")

sevens = [c for c in d2 if c.face == "7S"]
check(len(sevens) == 2 and sevens[0].id != sevens[1].id,
      "two 7-of-spades exist with distinct ids but the same face")
check(Card(7, "S").id == "7S#0" and Card(7, "S").face == "7S",
      "single-deck card keeps a clean face and id")

# ---- room deals from N decks, ids stay unique ----
SET = {"win_discount": 5, "stop_penalty": 40, "max_score": 100,
       "turn_timer": 40, "timeout_limit": 3, "num_decks": 2}
r = Room("T", "A", dict(SET))
for u in ("A", "B"):
    r.register_player(u, u); r.players[u].connected = True
r.start_round()
all_cards = list(r.draw_pile)
for u in ("A", "B"):
    all_cards += r.players[u].hand
check(len(all_cards) == 104, "all 104 cards accounted for after dealing 2 decks")
check(len({c.id for c in all_cards}) == 104, "no duplicate ids in play with 2 decks")

# ---- a player can hold + select one of two identical faces ----
p = r.players["A"]
p.hand = [Card(7, "S", 0), Card(7, "S", 1), Card(9, "H", 0)]
picked = r.card_objects("A", ["7S#1"])
check(picked is not None and len(picked) == 1 and picked[0].id == "7S#1",
      "card_objects resolves the exact deck-copy selected")
both = r.card_objects("A", ["7S#0", "7S#1"])
check(both is not None and len(both) == 2, "both identical faces are independently selectable (a pair)")

print("\n%d/%d Batch-2 checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
