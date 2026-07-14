"""Super 4 gameplay settings (variant-owned; surfaced via the game registry)."""

# ---- Room / table limits ----
MIN_PLAYERS = 2
MAX_PLAYERS = 8
SLOTS = 4                     # fixed face-down card slots per player
PREVIEW_SLOTS = (0, 1)       # slots the owner may look at before play begins

# ---- Host-selectable game settings (defaults) ----
DEFAULT_SETTINGS = {
    "turn_timer": 45,        # seconds per turn before auto-play
    "timeout_limit": 3,      # cumulative timeouts before a player is removed
    "preview_seconds": 10,   # how long the initial two-card preview is shown
    "match_window": 3,       # seconds a discard stays matchable by others (0 = off)
    "num_decks": 1,          # 52-card decks shuffled together
}

# Bounds used to sanitise host-supplied settings.
SETTINGS_BOUNDS = {
    "turn_timer": (15, 180),
    "timeout_limit": (1, 10),
    "preview_seconds": (3, 30),
    "match_window": (0, 15),   # 0 disables cross-player matching
    "num_decks": (1, 6),
}
