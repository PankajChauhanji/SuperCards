from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.cards import Card
from game.core.states import STATE_IN_TURN

room = Room("TEST", "u1", DEFAULT_SETTINGS)
room.state = STATE_IN_TURN
room.register_player("u1", "P1")
room.register_player("u2", "P2")
room.turn_order = ["u1", "u2"]
room.turn_index = 0

# P1 throws a 9 of Spades, claims 9
p1 = room.players["u1"]
c = Card(9, "S")
p1.hand = [c]
room.apply_play("u1", [c], "9")

result = room.apply_show("u2")
print("Claim 9, Throw 9:")
print("is_bluff:", result["is_bluff"])
print("loser:", result["loser"])

room.resolve_show(result)

# P1 throws a 8 of Spades, claims 9
room.turn_index = 0
c2 = Card(8, "S")
p1.hand = [c2]
room.apply_play("u1", [c2], "9")
result = room.apply_show("u2")

print("\nClaim 9, Throw 8:")
print("is_bluff:", result["is_bluff"])
print("loser:", result["loser"])
