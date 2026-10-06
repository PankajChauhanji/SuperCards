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
from game.poker.room import Room as PokerRoom
from game.poker import settings as poker_settings

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
    # False renders the landing-page tile as a disabled "coming soon" — for a
    # game whose backend is registered before its client bundle exists. This
    # lives on the spec, not in app.py: a hardcoded list there meant registering
    # game #4 and having it silently fail to appear, with no error anywhere.
    ready: bool = True
    # Whether the game scores discrete rounds and passes through STATE_ROUND_END.
    # Super Seven and Super 4 do; Bluff is a single race to an empty hand and
    # goes straight to STATE_GAME_END. Round-based games must therefore provide
    # ``round_end_payload`` (the shared lobby resends it on a mid-round-end
    # reconnect) — which is exactly what tests/test_platform_contract.py checks.
    has_rounds: bool = True


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
        display_name="Super Four",
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
        # Bluff is one continuous race to an empty hand: no per-round scoring,
        # so it never enters STATE_ROUND_END and has no round_end_payload.
        has_rounds=False,
    )
)

register(
    GameSpec(
        key="poker",
        display_name="Poker",
        room_class=PokerRoom,
        default_settings=poker_settings.DEFAULT_SETTINGS,
        settings_bounds=poker_settings.SETTINGS_BOUNDS,
        min_players=poker_settings.MIN_PLAYERS,
        max_players=poker_settings.MAX_PLAYERS,
        # Each deal is a round with its own summary (STATE_ROUND_END), and the
        # game ends after the host's chosen number of rounds.
        has_rounds=True,
    )
)
