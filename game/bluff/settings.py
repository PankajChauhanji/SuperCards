"""Bluff gameplay settings.

Keep in sync when any default changes: docs/bluff_rules.md and
static/rules/bluff/en.html.
"""

# ---- Room / table limits ----
MIN_PLAYERS = 2
MAX_PLAYERS = 6
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
