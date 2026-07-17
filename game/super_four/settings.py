"""Super 4 gameplay settings (variant-owned; surfaced via the game registry)."""

# ---- Room / table limits ----
MIN_PLAYERS = 2
MAX_PLAYERS = 8
SLOTS = 4                     # fixed face-down card slots per player
PREVIEW_SLOTS = (0, 1)       # slots the owner may look at before play begins

# ---- Host-selectable game settings (defaults) ----
# Scoring is round-based and LOWER cumulative is better: a player is eliminated
# once their cumulative reaches `exit_score`. See scoring.py / room.py.
DEFAULT_SETTINGS = {
    "turn_timer": 30,        # seconds per turn before auto-play
    "timeout_limit": 2,      # missed turns before a player is benched to spectator
    "match_window": 10,      # max seconds a face-up discard stays matchable (0 = off);
                             # the window also closes when the next player starts their turn
    "preview_seconds": 30,   # host may start early; server caps the preview at 30s
    "rounds": 5,             # rounds in a game (game may end earlier by elimination)
    "exit_score": 10,        # cumulative at/above this -> eliminated (spectator)
    "win_score": -3,         # round winner's score delta
    "loss_score": 1,         # every other active player's score delta
    "penalty_score": 3,      # caught Stop caller's delta (instead of loss_score)
    "num_decks": 1,          # 52-card decks shuffled together
}

# Bounds used to sanitise host-supplied settings. (lo, hi)
SETTINGS_BOUNDS = {
    "turn_timer": (15, 180),
    "timeout_limit": (1, 10),
    "match_window": (0, 10),
    "preview_seconds": (3, 30),
    "rounds": (1, 20),
    "exit_score": (3, 100),
    "win_score": (-20, 0),
    "loss_score": (0, 20),
    "penalty_score": (0, 40),
    "num_decks": (1, 6),
}
