"""Room: the single source of truth for one Bluff game table.

Holds the full game lifecycle: lobby, dealing, turn play, and game end.
"""
import time
import random
from typing import Dict, List, Optional

from game.bluff.settings import MAX_PLAYERS
from game.core.player import Player
from game.core.cards import shuffled_deck

from game.core.states import (
    STATE_LOBBY,
    STATE_IN_TURN,
    STATE_ROUND_END,
    STATE_GAME_END,
)

class Room:
    game_type = "bluff"

    def __init__(self, code: str, host_id: str, settings: dict):
        self.code = code
        self.host_id = host_id
        self.original_host_id = host_id
        self.settings = settings
        self.table_theme = "default"
        self.players: Dict[str, Player] = {}
        self.state = STATE_LOBBY
        self.round_number = 0
        self.created_at = time.time()

        # Round state
        self.target_rank: Optional[str] = None
        self.center_pile: List = []
        self.last_play: Optional[dict] = None
        self.pass_count = 0
        self.dead_pile: List = []

        self.turn_order: List[str] = []
        self.turn_index = 0
        self.start_offset = 0
        self.turn_start_ts = 0.0
        
        self.game_over = False
        self.winner: Optional[str] = None

    # ---- registration / attachment ----
    def register_player(self, user_id: str, name: str) -> Player:
        player = self.players.get(user_id)
        if player is None:
            player = Player(user_id=user_id, name=name, color_index=len(self.players))
            self.players[user_id] = player
        elif name:
            player.name = name
        return player

    def attach(self, user_id: str, sid: str, name: str = "") -> Optional[Player]:
        player = self.players.get(user_id)
        if player is None:
            return None
        player.sid = sid
        player.connected = True
        if name:
            player.name = name
        return player

    def detach(self, user_id: str) -> None:
        player = self.players.get(user_id)
        if player is not None:
            player.connected = False
            player.sid = ""

    def remove_player(self, user_id: str) -> None:
        self.players.pop(user_id, None)

    # ---- queries ----
    def is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS

    def is_host(self, user_id: str) -> bool:
        return user_id == self.host_id

    def connected_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.connected]

    def any_connected(self) -> bool:
        return any(p.connected for p in self.players.values())

    def any_human_connected(self) -> bool:
        return any(p.connected and not p.is_bot for p in self.players.values())

    def public_players(self) -> List[dict]:
        return [p.public_view() for p in self.players.values()]

    # ---- round lifecycle ----
    def start_round(self) -> None:
        active = [
            uid for uid, p in self.players.items()
            if p.connected and not p.eliminated and not p.is_spectator
        ]
        deck = shuffled_deck(self.settings.get("num_decks", 1))

        # Reset per-round player state
        for player in self.players.values():
            player.hand = []
            player.is_safe = False

        # Deal evenly
        while deck:
            for uid in active:
                if deck:
                    self.players[uid].hand.append(deck.pop())

        self.target_rank = None
        self.center_pile = []
        self.last_play = None
        self.pass_count = 0
        self.dead_pile = []

        self.turn_order = active
        self.turn_index = (self.start_offset % len(active)) if active else 0
        self.start_offset += 1
        
        self.turn_start_ts = time.time()
        self.round_number += 1
        self.state = STATE_IN_TURN

    def current_turn_id(self) -> Optional[str]:
        if not self.turn_order:
            return None
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def card_objects(self, user_id: str, card_ids: List[str]) -> Optional[List]:
        player = self.players.get(user_id)
        if player is None or not card_ids:
            return None
        if len(set(card_ids)) != len(card_ids):
            return None
        by_id = {c.id: c for c in player.hand}
        cards = []
        for cid in card_ids:
            card = by_id.get(cid)
            if card is None:
                return None
            cards.append(card)
        return cards

    def _check_potential_winner(self) -> bool:
        """If someone has an empty hand and they are NOT the last_play (meaning the window to challenge them has passed), they win."""
        if not self.last_play:
            return False
        
        last_actor_id = self.last_play["user_id"]
        for uid in self.turn_order:
            if not self.players[uid].hand and uid != last_actor_id:
                self.winner = uid
                self.game_over = True
                self.state = STATE_GAME_END
                return True
        return False

    def apply_play(self, user_id: str, cards: List, declared_rank: str) -> None:
        """Player throws cards, claiming they match declared_rank."""
        player = self.players[user_id]
        thrown_ids = {c.id for c in cards}
        player.hand = [c for c in player.hand if c.id not in thrown_ids]

        self.center_pile.extend(cards)
        
        if self.target_rank is None:
            self.target_rank = declared_rank

        self.last_play = {
            "user_id": user_id,
            "cards": cards,
            "declared_rank": declared_rank
        }
        self.pass_count = 0

        # If a previous player had 0 cards and it wasn't challenged just now, they win!
        if self._check_potential_winner():
            return

        self.advance_turn()

    def apply_pass(self, user_id: str) -> None:
        """Player passes. If pass_count hits (active_count - 1), clear table."""
        self.pass_count += 1
        
        # If someone else had 0 cards, they just won because the turn passed without a challenge
        if self._check_potential_winner():
            return

        # If everyone passed back to the last player who played, clear the table.
        active_count = len([u for u in self.turn_order if not self.players[u].eliminated])
        if self.pass_count >= active_count - 1 and self.last_play:
            self.dead_pile.extend(self.center_pile)
            self.center_pile = []
            self.target_rank = None
            self.last_play = None
            self.pass_count = 0
            # Turn remains with the player who won the table (the last person who played)
            self.turn_index = self.turn_order.index(self.current_turn_id()) # actually it naturally advances back to them
            # Wait, if pass_count == active_count - 1, the NEXT turn is the person who played last.
            # So advancing turn will naturally put it on them. Let's just advance turn normally.
            
        self.advance_turn()

    def apply_show(self, user_id: str) -> dict:
        """Player calls Show. Returns the result."""
        if not self.last_play:
            return {}

        defender_id = self.last_play["user_id"]
        cards = self.last_play["cards"]
        declared_rank = self.last_play["declared_rank"]

        is_bluff = any(c.rank != declared_rank for c in cards)
        
        loser_id = defender_id if is_bluff else user_id
        winner_id = user_id if is_bluff else defender_id

        # Loser picks up the entire center pile
        self.players[loser_id].hand.extend(self.center_pile)
        
        self.center_pile = []
        self.target_rank = None
        self.pass_count = 0
        self.last_play = None

        # The winner of the challenge gets to start the next round
        self.turn_index = self.turn_order.index(winner_id)
        self.turn_start_ts = time.time()

        return {
            "challenger": user_id,
            "defender": defender_id,
            "is_bluff": is_bluff,
            "revealed_cards": [c.to_dict() for c in cards],
            "loser": loser_id,
            "winner": winner_id,
        }

    def advance_turn(self) -> None:
        n = len(self.turn_order)
        if n == 0:
            return
        
        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            player = self.players.get(self.turn_order[self.turn_index])
            if player and not player.eliminated:
                self.turn_start_ts = time.time()
                return

    def turn_seconds_left(self) -> Optional[int]:
        if self.state != STATE_IN_TURN or self.current_turn_id() is None:
            return None
        deadline = self.turn_start_ts + self.settings.get("turn_timer", 40)
        return max(0, int(round(deadline - time.time())))

    def is_timed_out(self) -> bool:
        if self.state != STATE_IN_TURN or self.current_turn_id() is None:
            return False
        return time.time() >= self.turn_start_ts + self.settings.get("turn_timer", 40)

    def public_round_state(self) -> dict:
        last_play_pub = None
        if self.last_play:
            last_play_pub = {
                "user_id": self.last_play["user_id"],
                "count": len(self.last_play["cards"]),
                "declared_rank": self.last_play["declared_rank"]
            }

        return {
            "game_type": self.game_type,
            "state": self.state,
            "round_number": self.round_number,
            "host_id": self.host_id,
            "settings": self.settings,
            "table_theme": self.table_theme,
            "current_turn": self.current_turn_id(),
            "turn_order": list(self.turn_order),
            "target_rank": self.target_rank,
            "center_count": len(self.center_pile),
            "last_play": last_play_pub,
            "pass_count": self.pass_count,
            "turn_seconds_left": self.turn_seconds_left(),
            "players": self.public_players(),
        }

    def hand_for(self, user_id: str) -> List[dict]:
        player = self.players.get(user_id)
        return [c.to_dict() for c in player.hand] if player else []

    def force_timeout(self, user_id: str) -> dict:
        player = self.players[user_id]
        player.timeout_count += 1
        removed = player.timeout_count >= self.settings.get("timeout_limit", 3)

        if removed:
            player.eliminated = True
            
            # Check win condition if people are removed
            active = [u for u in self.turn_order if not self.players[u].eliminated]
            if len(active) <= 1:
                self.game_over = True
                self.winner = active[0] if active else None
                self.state = STATE_GAME_END
                
            self.advance_turn()
            self._migrate_host_if_eliminated()
        else:
            # Auto-pass
            self.apply_pass(user_id)

        return {
            "removed": removed,
            "timeout_count": player.timeout_count,
        }

    def _migrate_host_if_eliminated(self) -> None:
        host = self.players.get(self.host_id)
        if host is None or not host.eliminated:
            return
        candidates = [
            p for p in self.players.values()
            if p.connected and not p.eliminated and not p.is_bot
        ]
        if not candidates:
            return
        # Random candidate since there's no score to optimize
        self.host_id = candidates[0].user_id

    def game_end_payload(self) -> dict:
        return {
            "winner": self.winner,
            "winner_name": self.players[self.winner].name if self.winner else None,
            "players": self.public_players(),
            "host_id": self.host_id,
        }

    def reset_for_rematch(self) -> None:
        original = self.players.get(self.original_host_id)
        if original is not None and original.connected:
            self.host_id = self.original_host_id
        for p in self.players.values():
            p.hand = []
            p.eliminated = False
            p.timeout_count = 0
            p.is_spectator = False
            p.pending_join = False
        self.state = STATE_LOBBY
        self.round_number = 0
        self.start_offset = 0
        self.turn_order = []
        self.turn_index = 0
        
        self.target_rank = None
        self.center_pile = []
        self.last_play = None
        self.pass_count = 0
        self.dead_pile = []
        
        self.game_over = False
        self.winner = None

    def migrate_host(self) -> Optional[str]:
        if (
            self.host_id in self.players
            and self.players[self.host_id].connected
            and not self.players[self.host_id].eliminated
        ):
            return self.host_id
        for player in self.players.values():
            if player.connected and not player.is_bot and not player.eliminated:
                self.host_id = player.user_id
                return self.host_id
        return None
