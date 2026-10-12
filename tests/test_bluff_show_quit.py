import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Bluff: a player leaves while challenged cards are face up.

A Show is two-phase on purpose — apply_show() decides, the cards stay face up
for everyone for a few seconds, then resolve_show() moves the pile. Those
seconds are real time, so anyone can quit (or be kicked) inside them. That used
to crash resolve_show (the loser gone from ``players``, the winner gone from
``turn_order``); the socket handler never cleared ``is_showing``, and every
player still at the table was frozen out with "Cards are being revealed".

Every combination is played here: challenger or defender leaves, the Show
catches a bluff or not, and the departure leaves enough players to go on or
ends the game. After each, the room must be playable: every card accounted
for, the turn on a player still racing, and the game over when it should be.
"""
from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS
from game.core.cards import Card
from game.core.states import STATE_IN_TURN, STATE_GAME_END

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def make(n):
    room = Room("SHQT", "u1", dict(DEFAULT_SETTINGS))
    uids = ["u%d" % (i + 1) for i in range(n)]
    for u in uids:
        room.register_player(u, u.upper()).connected = True
    room.state = STATE_IN_TURN
    room.turn_order = list(uids)
    room.turn_index = 0
    hands = {
        "u1": [Card(1, "S"), Card(1, "H"), Card(2, "C")],
        "u2": [Card(2, "S"), Card(3, "H"), Card(3, "C")],
        "u3": [Card(4, "S"), Card(4, "H"), Card(4, "C")],
        "u4": [Card(5, "S"), Card(6, "H"), Card(7, "C")],
    }
    for u in uids:
        room.players[u].hand = list(hands[u])
    return room


def cards_in_play(room):
    n = len(room.center_pile) + len(room.dead_pile)
    return n + sum(len(p.hand) for p in room.players.values())


for n in (3, 4, 2):
    for bluff in (False, True):
        for leaver in ("challenger", "defender"):
            tag = "%d players, %s, %s leaves" % (n, "bluff" if bluff else "truth", leaver)
            room = make(n)
            # u1 throws two cards: truly two Aces, or claimed as Kings.
            room.apply_play("u1", room.players["u1"].hand[:2], "K" if bluff else "A")
            result = room.apply_show("u2")
            check(result["is_bluff"] == bluff, tag + ": show decided")
            gone = "u2" if leaver == "challenger" else "u1"
            gone_cards = len(room.players[gone].hand)
            total_before = cards_in_play(room) - gone_cards
            room.remove_participant(gone)        # ... during the reveal
            try:
                room.resolve_show(result)
                crashed = None
            except Exception as exc:              # the old behaviour
                crashed = exc
            check(crashed is None, tag + ": resolving the show does not crash (%r)" % (crashed,))
            if crashed:
                continue
            check(gone not in room.players and gone not in room.turn_order,
                  tag + ": the leaver is gone from the table")
            check(cards_in_play(room) == total_before,
                  tag + ": every card still accounted for (%d vs %d)" % (cards_in_play(room), total_before))
            if room.state == STATE_IN_TURN:
                cur = room.current_turn_id()
                check(cur in room.players and not room._out_of_play(cur),
                      tag + ": the turn is with a player still racing (%s)" % cur)
                check(room.last_play is None and room.target_rank is None,
                      tag + ": the table starts a fresh lead")
            else:
                check(room.state == STATE_GAME_END and n == 2,
                      tag + ": only a two-player table may end here (state %s)" % room.state)

# The game ends during the reveal: resolve_show must leave it ended.
room = make(2)
room.apply_play("u1", room.players["u1"].hand[:2], "A")
result = room.apply_show("u2")
room.remove_participant("u2")
check(room.state == STATE_GAME_END, "two players, the challenger quits: the game is over")
room.resolve_show(result)
check(room.state == STATE_GAME_END, "a show resolving after the game ended changes nothing")

print("\n%d/%d bluff show-quit checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
