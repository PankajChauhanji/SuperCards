from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.cards import Card
from game.core.states import STATE_IN_TURN

room = Room("TEST", "host", DEFAULT_SETTINGS)
room.register_player("p1", "P1")
room.register_player("p2", "P2")
room.state = STATE_IN_TURN
room.turn_order = ["p1", "p2"]
room.turn_index = 0

# Give specific cards
p1 = room.players["p1"]
p2 = room.players["p2"]

c1 = Card(9, "S") # True 9
c2 = Card(9, "H") # True 9
c3 = Card(8, "S") # Fake 9

p1.hand = [c1, c2, c3]
p2.hand = []

# Player 1 plays c1 and c2 as 9s (Truth)
print("P1 plays two 9s as 9 (Truth).")
room.apply_play("p1", [c1, c2], "9")
print(f"Center pile size: {len(room.center_pile)}")
print(f"Last play: {room.last_play['user_id']} played {len(room.last_play['cards'])} cards as {room.last_play['declared_rank']}")

# Player 2 plays c3 as 9 (Bluff - but wait, P2 doesn't have it, let's give P2 a fake 9)
p2.hand = [Card(2, "C")]
print("\nP2 plays a 2 as 9 (Bluff).")
room.apply_play("p2", [p2.hand[0]], "9")
print(f"Center pile size: {len(room.center_pile)}")
print(f"Last play: {room.last_play['user_id']} played {len(room.last_play['cards'])} cards as {room.last_play['declared_rank']}")

# Player 1 calls Show!
print("\nP1 calls Show!")
result = room.apply_show("p1")
print(f"Is bluff: {result['is_bluff']}")
print(f"Loser: {result['loser']}")
print(f"Revealed cards: {[c['code'] for c in result['revealed_cards']]}")

room.resolve_show(result)
print(f"\nAfter resolve:")
print(f"Center pile size: {len(room.center_pile)}")
print(f"P1 hand size: {len(p1.hand)}")
print(f"P2 hand size: {len(p2.hand)}")

