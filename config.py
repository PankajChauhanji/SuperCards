"""Platform-wide runtime & deployment configuration.

Only cross-game, environment/runtime settings live here. Per-game gameplay
tunables (hand size, round settings, table limits) live in each variant's
settings module, e.g. game/super_seven/settings.py, and are surfaced to the
shared lobby through the game registry (game/core/registry.py).
"""
import os

# ---- Room manager (game-agnostic) ----
ROOM_CODE_LENGTH = 4
# Seconds a room with zero connected players is kept before being reaped.
EMPTY_ROOM_TTL = 60

# ---- Runtime / deployment ----
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
PORT = int(os.environ.get("PORT", "5000"))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
