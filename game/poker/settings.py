"""Poker gameplay settings (variant-owned; surfaced via the game registry).

This file is the only source of truth. The numbers below are also *stated in
prose* for humans in:
  - docs/poker_rules.md (rules + design decisions)
  - static/rules/poker/{en,hi}.html (player-facing rules)

``tests/test_settings_docs.py`` pins each documented number to the value here, so
changing a default and running the suite names every sentence that needs editing.
"""

# ---- Room / table limits ----
MIN_PLAYERS = 2
# 20 players x 2 hole cards + 5 board + 3 burns = 48 of 52 cards, so one deck
# always suffices. Matches Super Seven and Bluff.
MAX_PLAYERS = 20
HOLE_CARDS = 2

# ---- Rule constants (not host-selectable) ----
# Big blind = starting coins // BLIND_DIVISOR (1%), small blind = half of that.
# Every player therefore starts 100 big blinds deep at any coin amount.
BLIND_DIVISOR = 100
# How long the round summary stays up before the next round deals by itself.
# The host may start it sooner.
ROUND_END_SECONDS = 30
# Seconds between board streets during an all-in runout, for the drama.
RUNOUT_STEP_SECONDS = 2

# ---- Host-selectable game settings (defaults) ----
DEFAULT_SETTINGS = {
    "starting_chips": 1_000_000,  # every player starts with exactly this many coins
    "rounds": 10,                 # rounds in a game (ends earlier if one player has it all)
    "turn_timer": 30,             # seconds per turn before auto check / fold
    "timeout_limit": 3,           # missed turns IN A ROW before a player is sat out
    "blind_up_every": 0,          # blinds double every N rounds; 0 = fixed blinds
    "hand_hints": 0,              # 1 = tell each player what hand they hold (whole table)
}

# Bounds used to sanitise host-supplied settings. (lo, hi)
SETTINGS_BOUNDS = {
    "starting_chips": (10_000, 100_000_000),
    "rounds": (1, 100),
    "turn_timer": (15, 120),
    "timeout_limit": (1, 10),
    "blind_up_every": (0, 50),
    "hand_hints": (0, 1),
}
