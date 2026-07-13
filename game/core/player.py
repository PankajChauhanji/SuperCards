"""Player model.

The `hand` is server-only state and is NEVER included in the public view that
gets broadcast to other players. Each player learns their own hand through a
separate, privately-addressed event (added in Phase 1).
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Player:
    user_id: str                 # stable, client-generated; survives reconnect
    name: str
    sid: str = ""                # Socket.IO session id; changes on reconnect
    hand: List = field(default_factory=list)   # server-only (Phase 1+)
    round_score: int = 0         # points this round (locked 0 when safe)
    total_score: int = 0         # cumulative across rounds
    is_safe: bool = False        # emptied hand this round
    connected: bool = False
    timeout_count: int = 0       # cumulative timeouts this game
    eliminated: bool = False     # out of the game
    color_index: int = 0         # stable per-player colour (assigned at join)
    is_bot: bool = False         # single-player mode only; never True in group games
    is_spectator: bool = False   # joined mid-game, watches only
    pending_join: bool = False   # host allowed them to join next round
    join_penalty_pct: int = 0    # penalty to apply to average score

    def public_view(self) -> dict:
        """Everything other players are allowed to see. No card faces."""
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
        }
