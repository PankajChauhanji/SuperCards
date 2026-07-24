import unittest
from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.cards import Card
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_GAME_END

class TestBluffLogic(unittest.TestCase):

    def setUp(self):
        self.room = Room("TEST", "u1", DEFAULT_SETTINGS)
        self.room.register_player("u1", "P1")
        self.room.register_player("u2", "P2")
        self.room.register_player("u3", "P3")
        self.room.state = STATE_IN_TURN
        self.room.turn_order = ["u1", "u2", "u3"]
        self.room.turn_index = 0
        self.room.players["u1"].hand = [Card(1, "S"), Card(1, "H"), Card(2, "C")]
        self.room.players["u2"].hand = [Card(2, "S"), Card(3, "H"), Card(3, "C")]
        self.room.players["u3"].hand = [Card(4, "S"), Card(4, "H"), Card(4, "C")]

    def get_cards(self, uid, count):
        return self.room.players[uid].hand[:count]

    def test_truthful_play_and_challenge(self):
        self.room.apply_play("u1", self.get_cards("u1", 2), "A")
        result = self.room.apply_show("u2")
        self.assertFalse(result["is_bluff"])
        self.assertEqual(result["loser"], "u2")
        self.assertEqual(result["winner"], "u1")
        self.assertEqual(len(self.room.players["u2"].hand), 5)
        self.assertEqual(len(self.room.players["u1"].hand), 1)

    def test_bluff_play_and_challenge(self):
        self.room.apply_play("u1", self.get_cards("u1", 2), "K")
        result = self.room.apply_show("u2")
        self.assertTrue(result["is_bluff"])
        self.assertEqual(result["loser"], "u1")
        self.assertEqual(len(self.room.players["u1"].hand), 3)

    def test_passing_clears_table(self):
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.room.apply_pass("u2")
        self.room.apply_pass("u3")
        self.assertEqual(self.room.pass_count, 0)
        self.assertEqual(len(self.room.center_pile), 0)
        self.assertEqual(len(self.room.dead_pile), 1)
        self.assertEqual(self.room.current_turn_id(), "u1")

    def test_win_condition(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.assertFalse(self.room.game_over)
        self.room.apply_play("u2", self.get_cards("u2", 1), "A")
        self.assertTrue(self.room.game_over)
        self.assertEqual(self.room.winner, "u1")
        
    def test_win_condition_by_pass(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.assertFalse(self.room.game_over)
        self.room.apply_pass("u2")
        self.assertFalse(self.room.game_over)
        self.room.apply_pass("u3")
        self.assertTrue(self.room.game_over)
        self.assertEqual(self.room.winner, "u1")

if __name__ == '__main__':
    unittest.main()
