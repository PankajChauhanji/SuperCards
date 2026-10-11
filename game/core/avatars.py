"""Player avatars — a small motif shown in place of the initial.

An avatar is one name from ``MOTIFS``, chosen on the player's device and sent
with their name. Nothing is stored server-side beyond the Player record for the
life of the room, so there is no account and no database.

The colour is NOT part of the avatar: every player already has a stable identity
colour (``Player.color_index``) used by the seats, the Scores panel and the
action log, and a second, player-picked colour would fight it. The motif is the
only thing a player chooses.

Each motif is the id of a symbol in templates/partials/icons.html. The server
only ever echoes back a value from this list, so a client cannot inject markup
or reference an icon that does not exist. ``""`` means "show my initial" — the
default, so nobody has to choose anything.
"""
from typing import Any

MOTIFS = (
    "spade", "heart", "diamond", "club",
    "crown", "star", "flame", "bolt",
    "moon", "sun", "leaf", "anchor",
    "rocket", "music", "ghost", "gem",
)


def clean(raw: Any) -> str:
    """A motif from MOTIFS, or "" (show the initial) for anything else."""
    if isinstance(raw, str) and raw in MOTIFS:
        return raw
    return ""
