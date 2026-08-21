"""Shared vocabulary for card visibility.

Each game ships a ``visibility.public_card_ids(room)`` returning the set of card
ids the rules currently show to everyone — or ``EVERYTHING`` for the moments a
game deliberately reveals all hands (round end, game end).

Two consumers share these oracles so the rule has exactly one definition:
  * ``sockets/audience.py`` — the runtime guard on outgoing broadcasts.
  * ``tests/test_leak_fuzz.py`` — the randomized leak harness.
"""


class _Everything:
    """Sentinel: this moment reveals all cards by design."""

    __slots__ = ()

    def __contains__(self, _card_id):   # any card is allowed
        return True

    def __repr__(self):
        return "EVERYTHING"


EVERYTHING = _Everything()
