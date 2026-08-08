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

# ---- TWA (the Android wrapper app) ----
# Digital Asset Links: proves the site and the Android package share an owner.
# Until the fingerprint below is served at /.well-known/assetlinks.json on the
# production domain, Chrome keeps its URL bar visible inside the installed app.
# Neither value is a secret — the fingerprint is published by design — so they
# are committed as defaults and only need overriding if the signing key changes.
# Regenerate with:  bubblewrap fingerprint list  (inside twa/)
TWA_PACKAGE_NAME = os.environ.get("TWA_PACKAGE_NAME", "com.pankajchauhan.supercards")
TWA_SHA256_FINGERPRINT = os.environ.get(
    "TWA_SHA256_FINGERPRINT",
    "83:19:0C:E6:A2:70:61:89:AA:BC:F6:C1:1C:70:53:DE:"
    "4D:F8:18:28:C3:34:A2:0E:5E:3F:06:DD:F0:EF:5B:7C",
)
