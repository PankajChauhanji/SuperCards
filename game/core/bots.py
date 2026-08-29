"""The roster of computer players, shared by every game.

A bot is an ordinary ``Player`` with ``is_bot = True`` and no socket. Nothing
about how it *plays* lives here — each variant's ``ai.py`` already decides moves
from ``(room, bot_id)``, and the director calls it whenever a bot holds the turn.
This module owns only the part that is genuinely platform-wide: which computer
players exist, what they are called, how many may sit at one table, and how a new
one is given an identity that cannot collide with anyone already in the room.

It deliberately imports no game. Adding a variant does not touch this file, and
this file cannot break a variant's rules.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Every bot user_id starts with this, which is what makes a bot recognisable
# from its id alone in a log line or a snapshot.
ID_PREFIX = "bot_"

# The most computer players allowed at one table. A game's own MAX_PLAYERS still
# applies on top, and is checked separately — this is the platform's answer to
# "how much of the table may be machines", not "how big may a table be".
MAX_BOTS = 5


@dataclass(frozen=True)
class BotProfile:
    """One selectable computer player. Identity only — no behaviour."""
    key: str      # stable, used to build the user_id; never shown to players
    name: str     # what the table sees
    gender: str   # "m" / "f" — the picker shows a balanced roster, nothing else


# Five profiles for a cap of five, so seating a full table of computer
# players never has to fall back to a numbered repeat.
ROSTER: Tuple[BotProfile, ...] = (
    BotProfile("sooryavanshi", "Sooryavanshi", "m"),
    BotProfile("rajnikant", "Rajnikant", "m"),
    BotProfile("modi", "Modi", "m"),
    BotProfile("rashmika", "Rashmika Mandanna", "f"),
    BotProfile("smriti", "Smriti Mandhana", "f"),
)

DEFAULT_KEY = ROSTER[0].key


def profile(key: str) -> Optional[BotProfile]:
    """Look up a profile by key, or None if it is not one of ours."""
    for entry in ROSTER:
        if entry.key == key:
            return entry
    return None


def public_roster() -> List[dict]:
    """The roster as the lobby picker needs it."""
    return [{"key": p.key, "name": p.name, "gender": p.gender} for p in ROSTER]


def bots_in(room) -> List[str]:
    """User ids of the computer players currently in a room."""
    return [uid for uid, p in room.players.items() if p.is_bot]


def is_full(room) -> bool:
    """True when this room already holds the maximum number of bots."""
    return len(bots_in(room)) >= MAX_BOTS


def next_profile(room) -> BotProfile:
    """The profile to offer when the host does not pick one.

    First one not already at the table, so clicking Add bot repeatedly gives four
    distinct opponents before it has to repeat a name.
    """
    taken = {room.players[uid].name for uid in bots_in(room)}
    for entry in ROSTER:
        if entry.name not in taken:
            return entry
    return ROSTER[0]


def allocate(room, key: Optional[str] = None) -> Tuple[str, str]:
    """Reserve an identity for a new bot: returns ``(user_id, display_name)``.

    The roster matches the cap (five profiles, five seats), but a name still
    has to be usable more than once if ``MAX_BOTS`` ever grows past the roster
    size, or if a human already sits at the table under a bot's name. In that
    case the profile repeats under a numbered name (e.g. "Modi 2",
    ``bot_modi_2``) rather than being refused — a numbered name is clearer at
    a table than an invented one nobody chose.

    The suffix search walks past *any* existing player, not just bots, so a bot
    can never take an id or a display name that is already in the room —
    including from a human who happens to share a bot's name.
    """
    entry = profile(key) if key else None
    if entry is None:
        entry = next_profile(room)

    names_taken = {p.name for p in room.players.values()}
    suffix = 1
    while True:
        user_id = ID_PREFIX + entry.key + ("" if suffix == 1 else "_%d" % suffix)
        name = entry.name if suffix == 1 else "%s %d" % (entry.name, suffix)
        if user_id not in room.players and name not in names_taken:
            return user_id, name
        suffix += 1


def add_to(room, key: Optional[str] = None):
    """Seat a new computer player and return it.

    Marked connected because a bot is always present: it counts toward the
    minimum needed to start, and it never disconnects. It has no ``sid``, which
    is what every private-deal path already keys off to skip it.

    Callers are responsible for the *policy* checks (host, lobby state, table
    size, bot cap) — see sockets/lobby.py, which is where those errors belong.
    """
    user_id, name = allocate(room, key)
    bot = room.register_player(user_id, name)
    bot.is_bot = True
    bot.connected = True
    return bot
