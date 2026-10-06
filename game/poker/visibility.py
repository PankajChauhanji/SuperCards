"""What Poker puts face-up, for everyone, right now.

Single source of truth for "publicly visible card", shared by the runtime emit
guard (sockets/audience.py) and the leak fuzzer (tests/test_leak_fuzz.py).

Public: the board, plus the hole cards of players whose hands are turned up —
during an all-in runout and at showdown. Unlike the other games, the round end
is **not** a blanket reveal: a folded hand stays hidden forever, and so do an
uncontested winner's cards. Using ``EVERYTHING`` at round end here would let a
round summary leak exactly the cards players folded to keep secret.
"""


def public_card_ids(room):
    """Card ids every player may legitimately see in a room-wide payload."""
    ids = {c.id for c in room.board}
    for uid in room.shown:
        ids.update(c.id for c in room.hole.get(uid, []))
    return ids
