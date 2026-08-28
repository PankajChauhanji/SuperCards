"""Bluff gameplay settings.

This file is the only source of truth. Where these numbers are also stated in
prose (docs/bluff_rules.md, static/rules/bluff/en.html), add a claim to
tests/test_settings_docs.py so drift fails a test instead of relying on memory.
"""

# ---- Room / table limits ----
MIN_PLAYERS = 2
MAX_PLAYERS = 6

# How many places are played out before the game is called. Bluff has no score
# to rank people by, so the only ranking it can produce is the order in which
# players shed their last card — which means the game has to keep running after
# the first player is out, or there is nothing to put on a podium.
#
# Three is the podium. Playing on past it would only be sorting out last place,
# which nobody stays for. A table too small to fill three places ends as soon as
# one player is left holding cards, so a 2- or 3-player game finishes naturally
# without this ever binding.
PODIUM_PLACES = 3
# Cards are dealt evenly among all players; HAND_SIZE isn't strictly fixed per player,
# but we can set a dummy or ignore it in dealing logic.

# ---- Host-selectable game settings (defaults) ----
DEFAULT_SETTINGS = {
    "turn_timer": 40,      # seconds per turn before auto-pass
    "timeout_limit": 3,    # cumulative timeouts before a player is removed
    "num_decks": 1,        # number of 52-card decks shuffled together
}

SETTINGS_BOUNDS = {
    "turn_timer": (15, 180),
    "timeout_limit": (1, 10),
    "num_decks": (1, 5),
}
