"""Game variant registry.

Maps a ``game_type`` key to its concrete Room class and per-game metadata. This
is the single place the platform learns which games exist: adding a variant means
registering it here (plus shipping its ``game/<variant>/`` package and socket
handlers). Nothing else in ``core`` or the shared socket layer imports a specific
game.
"""
from dataclasses import dataclass
from typing import Dict, Optional

from game.super_seven.room import Room as SuperSevenRoom
from game.super_seven import settings as super_seven_settings
from game.super_four.room import Room as SuperFourRoom
from game.super_four import settings as super_four_settings
from game.bluff.room import Room as BluffRoom
from game.bluff import settings as bluff_settings

# The game selected when a client does not (yet) specify one. Keeps every
# existing Super Seven code path working unchanged.
DEFAULT_GAME = "super_seven"


@dataclass(frozen=True)
class GameSpec:
    """Everything the platform needs to stand up and validate one game variant."""
    key: str
    display_name: str
    room_class: type
    default_settings: dict
    settings_bounds: dict
    min_players: int
    max_players: int


_GAMES: Dict[str, GameSpec] = {}


def register(spec: GameSpec) -> None:
    _GAMES[spec.key] = spec


def get(game_type: str) -> Optional[GameSpec]:
    return _GAMES.get(game_type)


def is_registered(game_type: str) -> bool:
    return game_type in _GAMES


def all_games() -> Dict[str, GameSpec]:
    """Registered games, keyed by game_type — used by the landing-page picker."""
    return dict(_GAMES)


# ---- Registrations -------------------------------------------------------
register(
    GameSpec(
        key="super_seven",
        display_name="Super Seven",
        room_class=SuperSevenRoom,
        default_settings=super_seven_settings.DEFAULT_SETTINGS,
        settings_bounds=super_seven_settings.SETTINGS_BOUNDS,
        min_players=super_seven_settings.MIN_PLAYERS,
        max_players=super_seven_settings.MAX_PLAYERS,
    )
)

register(
    GameSpec(
        key="super_four",
        display_name="Super 4",
        room_class=SuperFourRoom,
        default_settings=super_four_settings.DEFAULT_SETTINGS,
        settings_bounds=super_four_settings.SETTINGS_BOUNDS,
        min_players=super_four_settings.MIN_PLAYERS,
        max_players=super_four_settings.MAX_PLAYERS,
    )
)

register(
    GameSpec(
        key="bluff",
        display_name="Bluff",
        room_class=BluffRoom,
        default_settings=bluff_settings.DEFAULT_SETTINGS,
        settings_bounds=bluff_settings.SETTINGS_BOUNDS,
        min_players=bluff_settings.MIN_PLAYERS,
        max_players=bluff_settings.MAX_PLAYERS,
    )
)

