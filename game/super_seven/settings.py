"""Super Seven gameplay settings.

These are game-specific tunables (table limits, host-selectable round settings,
and the server-only match-draw toggle). They live with the variant, not in the
shared config.py, so each game owns its own settings. The registry exposes
DEFAULT_SETTINGS / SETTINGS_BOUNDS / MIN_PLAYERS / MAX_PLAYERS to the shared
lobby via the game's GameSpec.
"""

# ---- Room / table limits ----
MIN_PLAYERS = 2
MAX_PLAYERS = 20
HAND_SIZE = 7

# ---- Host-selectable game settings (defaults) ----
# A round's scores add to cumulative totals. A player whose cumulative total
# reaches max_score is eliminated. Last player standing wins.
DEFAULT_SETTINGS = {
    "max_score": 100,      # cumulative total >= this -> eliminated
    "stop_penalty": 40,    # added to a caught Stop-caller's hand total
    "win_discount": 5,     # strictly-lowest caller scores max(total - this, 0)
    "turn_timer": 40,      # seconds per turn before auto-discard
    "timeout_limit": 3,    # cumulative timeouts before a player is removed
    "num_decks": 1,        # number of 52-card decks shuffled together
}

# Bounds used to sanitise host-supplied settings.
SETTINGS_BOUNDS = {
    "max_score": (20, 1000),
    "stop_penalty": (0, 200),
    "win_discount": (0, 50),
    "turn_timer": (15, 180),
    "timeout_limit": (1, 10),
    "num_decks": (1, 10),
}

# ---- Match-play draw rule ----
# If True, a Match still owes a draw afterwards (legacy behavior, same as a
# Single/Pair). If False, a Match behaves like a no-draw combo (Set/Sequence)
# and the turn advances immediately with no draw required.
# Server-only toggle — deliberately NOT part of DEFAULT_SETTINGS, so it can't be
# changed per-room from the lobby settings UI.
MATCH_REQUIRES_DRAW = False
