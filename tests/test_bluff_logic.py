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

    # Show is deliberately two-phase: apply_show() only decides the outcome so
    # the client can animate the reveal, and resolve_show() then moves the pile.
    # Assertions about hand sizes must run after BOTH phases, the same order
    # sockets/gameplay/bluff.py uses.
    def test_truthful_play_and_challenge(self):
        self.room.apply_play("u1", self.get_cards("u1", 2), "A")
        result = self.room.apply_show("u2")
        self.assertFalse(result["is_bluff"])
        self.assertEqual(result["loser"], "u2")
        self.assertEqual(result["winner"], "u1")
        self.room.resolve_show(result)
        # u1 played 2 of its 3 cards; u2 loses the challenge and eats the pile.
        self.assertEqual(len(self.room.players["u2"].hand), 5)
        self.assertEqual(len(self.room.players["u1"].hand), 1)

    def test_bluff_play_and_challenge(self):
        self.room.apply_play("u1", self.get_cards("u1", 2), "K")
        result = self.room.apply_show("u2")
        self.assertTrue(result["is_bluff"])
        self.assertEqual(result["loser"], "u1")
        self.room.resolve_show(result)
        # Caught bluffing: u1 takes back its 2 cards, so it is down to 1 + 2.
        self.assertEqual(len(self.room.players["u1"].hand), 3)

    def test_passing_clears_table(self):
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.room.apply_pass("u2")
        self.room.apply_pass("u3")
        self.assertEqual(self.room.pass_count, 0)
        self.assertEqual(len(self.room.center_pile), 0)
        self.assertEqual(len(self.room.dead_pile), 1)
        self.assertEqual(self.room.current_turn_id(), "u1")

    # Shedding your last card no longer ends the game — it banks a place, and the
    # rest play on for the remaining ones. See game/bluff/settings.PODIUM_PLACES.
    def test_going_out_banks_first_place_and_play_continues(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        # Not out yet: u2 may still call Show on that last play.
        self.assertEqual(self.room.finish_order, [])
        self.room.apply_play("u2", self.get_cards("u2", 1), "A")
        # u2 acted without challenging, so u1's finish is confirmed…
        self.assertEqual(self.room.finish_order, ["u1"])
        # …but u2 and u3 are both still holding cards, so there is a race left.
        self.assertFalse(self.room.game_over)
        self.assertNotEqual(self.room.current_turn_id(), "u1")

    def test_going_out_is_confirmed_by_a_full_pass_round(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.room.apply_pass("u2")
        self.assertEqual(self.room.finish_order, [])
        self.room.apply_pass("u3")
        # Nobody challenged all the way round: u1 is out, and the pile they left
        # is swept out of the game.
        self.assertEqual(self.room.finish_order, ["u1"])
        self.assertEqual(len(self.room.center_pile), 0)
        self.assertFalse(self.room.game_over)

    def test_game_ends_once_only_one_player_still_holds_cards(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.players["u2"].hand = [Card(2, "S")]
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.room.apply_play("u2", self.get_cards("u2", 1), "A")
        self.room.apply_pass("u3")
        self.assertEqual(self.room.finish_order, ["u1", "u2"])
        self.assertTrue(self.room.game_over)
        self.assertEqual(self.room.state, STATE_GAME_END)
        self.assertEqual(self.room.winner, "u1")

    def test_standings_rank_the_unfinished_by_cards_held(self):
        self.room.players["u1"].hand = [Card(1, "S")]
        self.room.players["u2"].hand = [Card(13, "S"), Card(13, "H")]   # 2 high cards
        self.room.players["u3"].hand = [Card(2, "S")]                   # 1 low card
        self.room.apply_play("u1", self.get_cards("u1", 1), "A")
        self.room.apply_pass("u2")
        self.room.apply_pass("u3")

        rows = self.room.standings()
        self.assertEqual([r["user_id"] for r in rows], ["u1", "u3", "u2"])
        self.assertEqual([r["place"] for r in rows], [1, 2, 3])
        self.assertTrue(rows[0]["finished"])
        # Ranked on how many cards are left, not what they are worth: u3's single
        # 2 beats u2's pair of Kings.
        self.assertEqual(rows[1]["cards_left"], 1)
        self.assertEqual(rows[2]["cards_left"], 2)

if __name__ == '__main__':
    unittest.main()
