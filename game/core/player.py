"""Player model — the roster record shared by every game variant.

Most fields are genuinely cross-game (identity, connection, scoring, spectator
lifecycle). A few are scoped to a subset of games and are grouped/labelled as
such below so the coupling is explicit rather than accidental:

* ``hand`` / ``card_count`` (and therefore ``public_view``) belong to the
  **hand-based** games — Super Seven and Bluff. They are server-only card lists;
  the public view exposes only the *count*, never the faces. (Rule of two: two
  games share this the same way, so it lives in core.)
* ``is_safe`` is **Super Seven-only** (a player who emptied their hand locks at 0
  and sits the round out). No other variant sets it; it stays here because Super
  Seven's shared ``public_view`` reports it, and one boolean does not justify a
  variant Player subclass.

Slot-based games own their own state and view: **Super 4** keeps ``slots`` on its
Room and builds its own ``public_players()`` (it never calls ``public_view``), so
none of the hand/safe fields ever reach a Super 4 client.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Player:
    # ---- identity / roster (all games) ----
    user_id: str                 # stable, client-generated; survives reconnect
    name: str
    sid: str = ""                # Socket.IO session id; changes on reconnect
    connected: bool = False
    color_index: int = 0         # stable per-player colour (assigned at join)
    is_bot: bool = False         # single-player mode only; never True in group games

    # ---- scoring / lifecycle (all games) ----
    round_score: int = 0         # points this round
    total_score: int = 0         # cumulative across rounds
    timeout_count: int = 0       # cumulative timeouts this game
    eliminated: bool = False     # out of the game
    is_spectator: bool = False   # joined mid-game / benched, watches only
    pending_join: bool = False   # host allowed them to join next round
    join_penalty_pct: int = 0    # penalty to apply to average score on admit

    # ---- hand-based games only (Super Seven, Bluff) ----
    hand: List = field(default_factory=list)   # server-only; faces never broadcast

    # ---- Super Seven only ----
    is_safe: bool = False        # emptied hand this round -> locked at 0, sits out

    def public_view(self) -> dict:
        """Public roster entry for the hand-based games (Super Seven, Bluff).

        Exposes the hand *count* but never card faces. ``is_safe`` is meaningful
        only in Super Seven (always False elsewhere). Super 4 does not use this —
        it builds its own slot-aware ``public_players()``.
        """
        return {
            "user_id": self.user_id,
            "name": self.name,
            "score": self.total_score,
            "card_count": len(self.hand),
            "is_safe": self.is_safe,
            "connected": self.connected,
            "eliminated": self.eliminated,
            "color": self.color_index,
            "is_spectator": self.is_spectator,
            "pending_join": self.pending_join,
            "is_bot": self.is_bot,
        }
