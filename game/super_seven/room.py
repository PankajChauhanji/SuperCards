"""Room: the single source of truth for one game table.

Holds the full game lifecycle: lobby, dealing, turn play, round scoring with
elimination, the per-turn clock used by the timeout director, and game end.
All state is in memory, which is why production runs a single worker.
"""
import time
import random
from typing import Dict, List, Optional

from game.super_seven.settings import MAX_PLAYERS, HAND_SIZE, MATCH_REQUIRES_DRAW
from game.core.player import Player
from game.core.cards import shuffled_deck
from game.super_seven.rules import DRAW_ACTIONS, COMBO_ACTIONS, ACTION_SINGLE, ACTION_MATCH

# Game lifecycle states — canonical definitions live in game.core.states and are
# re-exported here for backward compatibility (existing imports and tests do
# `from game.super_seven.room import STATE_IN_TURN`).
from game.core.states import (  # noqa: E402,F401
    STATE_LOBBY,
    STATE_IN_TURN,
    STATE_ROUND_END,
    STATE_GAME_END,
)

# Fixed grace period (seconds) to take the owed draw after a discard before the
# server auto-picks for the player. Deliberately NOT host-configurable.
PICK_SECONDS = 3


class Room:
    # Variant identifier; RoomManager also sets this per instance from the
    # registry. Kept as a class default so room.game_type always resolves.
    game_type = "super_seven"

    def __init__(self, code: str, host_id: str, settings: dict):
        self.code = code
        self.host_id = host_id
        self.original_host_id = host_id   # restored once back in the lobby (rematch)
        self.settings = settings
        self.table_theme = "default"
        self.players: Dict[str, Player] = {}   # user_id -> Player
        self.state = STATE_LOBBY
        self.round_number = 0
        self.created_at = time.time()

        # Round state (populated by start_round)
        self.draw_pile: List = []
        self.discard_pile: List = []      # all thrown cards, for reshuffle
        self.center_throw: List = []      # the visible last throw
        self.last_was_combo = False       # gates Action D (Match) in Phase 2
        self.turn_order: List[str] = []   # active user_ids, seating order
        self.turn_index = 0
        self.awaiting_draw = False        # current player owes a draw
        self.awaiting_draw_ts = 0.0       # when the owed draw began (pick timer)
        self.turns_completed = 0          # completed turns this round
        self.initial_active = 0           # players dealt in this round
        self.first_orbit_complete = False # gates calling Stop
        self.last_caller = None           # who called Stop last round
        self.last_caught = False
        self.turn_start_ts = 0.0          # when the current turn began (for the timer)
        self.start_offset = 0             # rotates the first drawer each round
        self.newly_eliminated: List[str] = []
        self.game_over = False
        self.winner: Optional[str] = None

    # ---- registration / attachment ----
    def register_player(self, user_id: str, name: str) -> Player:
        """Add a player without binding a socket (pre-navigation step)."""
        player = self.players.get(user_id)
        if player is None:
            player = Player(user_id=user_id, name=name, color_index=len(self.players))
            self.players[user_id] = player
        elif name:
            player.name = name
        return player

    def attach(self, user_id: str, sid: str, name: str = "") -> Optional[Player]:
        """Bind a live socket to an already-registered player."""
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
        """True if at least one non-bot player is connected.
        Used by the reaper so solo rooms don't live forever after the human leaves."""
        return any(p.connected and not p.is_bot for p in self.players.values())

    def public_players(self) -> List[dict]:
        return [p.public_view() for p in self.players.values()]

    # ---- round lifecycle ----
    def start_round(self) -> None:
        """Deal a fresh round. Active = connected and not eliminated."""
        active = [
            uid for uid, p in self.players.items()
            if p.connected and not p.eliminated and not p.is_spectator
        ]
        deck = shuffled_deck(self.settings.get("num_decks", 1))

        # Reset per-round player state.
        for player in self.players.values():
            player.hand = []
            player.is_safe = False
            player.round_score = 0

        for uid in active:
            self.players[uid].hand = [deck.pop() for _ in range(HAND_SIZE)]

        self.draw_pile = deck
        self.discard_pile = []
        self.center_throw = []
        self.last_was_combo = False
        self.turn_order = active
        # Rotate who leads off each round.
        self.turn_index = (self.start_offset % len(active)) if active else 0
        self.start_offset += 1
        self.awaiting_draw = False
        self.turns_completed = 0
        self.initial_active = len(active)
        self.first_orbit_complete = False
        self.last_caller = None
        self.last_caught = False
        self.turn_start_ts = time.time()
        self.round_number += 1
        self.state = STATE_IN_TURN

    def current_turn_id(self) -> Optional[str]:
        if not self.turn_order:
            return None
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def center_rank_set(self) -> set:
        """Rank set currently showing in the centre (matchable by the next play)."""
        return {c.rank for c in self.center_throw}

    def card_objects(self, user_id: str, card_ids: List[str]) -> Optional[List]:
        """Resolve card ids to Card objects in the player's hand.

        Returns None if any id is missing or duplicated (an illegal selection).
        Card ids are unique within a deck, so a valid selection has no repeats.
        """
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

    def apply_throw(self, user_id: str, cards: List, action: str) -> bool:
        """Apply a validated throw. Returns True if the player now owes a draw."""
        player = self.players[user_id]
        thrown_ids = {c.id for c in cards}
        player.hand = [c for c in player.hand if c.id not in thrown_ids]

        # The previous visible throw is now buried in the discard pile.
        self.discard_pile.extend(self.center_throw)
        self.center_throw = list(cards)
        # A match does NOT leave a matchable combo (no chaining).
        self.last_was_combo = action in COMBO_ACTIONS

        owes_draw = action in DRAW_ACTIONS
        if action == ACTION_MATCH and not MATCH_REQUIRES_DRAW:
            owes_draw = False
        if owes_draw:
            self.awaiting_draw = True
            self.awaiting_draw_ts = time.time()  # start the 3s pick timer
            # Turn does not advance until the draw is taken.
        else:
            # Only a no-draw combo can empty a hand -> player is safe.
            if not player.hand:
                player.is_safe = True
            self.awaiting_draw = False
            self.advance_turn()
        return owes_draw

    def draw_one(self, user_id: str) -> dict:
        """Take the owed draw, reshuffling if needed, then advance.

        Returns {"card": Card|None, "reshuffled": bool}.
        """
        reshuffled = False
        if not self.draw_pile and self.discard_pile:
            # Reshuffle the buried discards (the visible center stays on the table).
            random.shuffle(self.discard_pile)
            self.draw_pile = self.discard_pile
            self.discard_pile = []
            reshuffled = True
        drawn = None
        if self.draw_pile:
            drawn = self.draw_pile.pop()
            self.players[user_id].hand.append(drawn)
        # If both piles are empty there is nothing to draw; the turn still passes.
        self.awaiting_draw = False
        self.advance_turn()
        return {"card": drawn, "reshuffled": reshuffled}

    def advance_turn(self) -> None:
        """Move to the next player who can act (not safe, not eliminated)."""
        n = len(self.turn_order)
        if n == 0:
            return
        # One turn has just completed.
        self.turns_completed += 1
        if self.turns_completed >= self.initial_active:
            self.first_orbit_complete = True
        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            player = self.players.get(self.turn_order[self.turn_index])
            if player and not player.is_safe and not player.eliminated:
                self.turn_start_ts = time.time()  # fresh clock for the new turn
                return
        # No eligible player remains — the caller-less auto-end is handled
        # by the gameplay layer via active_count().

    def turn_seconds_left(self) -> Optional[int]:
        """Whole seconds remaining on the current turn, or None when not in play."""
        if self.state != STATE_IN_TURN or self.current_turn_id() is None:
            return None
        deadline = self.turn_start_ts + self.settings["turn_timer"]
        return max(0, int(round(deadline - time.time())))

    def is_timed_out(self) -> bool:
        if self.state != STATE_IN_TURN or self.current_turn_id() is None:
            return False
        return time.time() >= self.turn_start_ts + self.settings["turn_timer"]

    def pick_seconds_left(self) -> Optional[int]:
        """Whole seconds left on the 3s post-discard pick timer, or None."""
        if self.state != STATE_IN_TURN or not self.awaiting_draw:
            return None
        return max(0, int(round(self.awaiting_draw_ts + PICK_SECONDS - time.time())))

    def pick_timed_out(self) -> bool:
        """True once the owed draw has gone untaken past the fixed grace period."""
        if self.state != STATE_IN_TURN or not self.awaiting_draw:
            return False
        return time.time() >= self.awaiting_draw_ts + PICK_SECONDS

    def active_count(self) -> int:
        """Players still holding cards who can take a turn."""
        return sum(
            1 for uid in self.turn_order
            if not self.players[uid].is_safe and not self.players[uid].eliminated
        )

    def public_round_state(self) -> dict:
        """Common, privacy-safe snapshot shared by every player (no hands)."""
        return {
            "game_type": self.game_type,
            "state": self.state,
            "round_number": self.round_number,
            "host_id": self.host_id,
            "settings": self.settings,
            "table_theme": getattr(self, "table_theme", "default"),
            "current_turn": self.current_turn_id(),
            "awaiting_draw": self.awaiting_draw,
            "first_orbit_complete": self.first_orbit_complete,
            "turn_order": list(self.turn_order),
            "deck_count": len(self.draw_pile),
            "center": [c.to_dict() for c in self.center_throw],
            "last_was_combo": self.last_was_combo,
            "match_requires_draw": MATCH_REQUIRES_DRAW,
            "turn_seconds_left": self.turn_seconds_left(),
            "pick_seconds_left": self.pick_seconds_left(),
            "players": self.public_players(),
        }

    # ---- round end / scoring / elimination ----
    def end_round(self, caller_id: Optional[str]) -> dict:
        """Score the round, apply totals, resolve eliminations, set end state."""
        from game.super_seven.scoring import score_round

        participants = [
            (uid, self.players[uid].hand, self.players[uid].is_safe)
            for uid in self.turn_order
        ]
        result = score_round(participants, caller_id, self.settings)
        for uid, pts in result["scores"].items():
            self.players[uid].round_score = pts
            self.players[uid].total_score += pts

        self.last_caller = caller_id
        self.last_caught = result["caught"]
        self.awaiting_draw = False

        # Calculate average for pending spectators using post-round totals
        in_play = [p for p in self.players.values() if not p.eliminated and not p.is_spectator]
        avg_score = sum(p.total_score for p in in_play) / len(in_play) if in_play else 0

        for p in self.players.values():
            if p.is_spectator and p.pending_join:
                p.total_score = int(round(avg_score + (avg_score * p.join_penalty_pct / 100.0)))
                p.is_spectator = False
                p.pending_join = False
                p.eliminated = False # Ensure they enter active state

        self._resolve_eliminations()
        self.state = STATE_GAME_END if self.game_over else STATE_ROUND_END
        self._last_result = result
        return result

    def non_eliminated(self) -> List[str]:
        return [uid for uid, p in self.players.items() if not p.eliminated and not p.is_spectator]

    def _resolve_eliminations(self) -> None:
        """Eliminate anyone at/over the score cap; set game_over and winner.

        If every remaining player would be eliminated in the same round, the
        single lowest cumulative total survives and wins (tiebreaker keeps the
        game producing exactly one winner).
        """
        cap = self.settings["max_score"]
        in_play = self.non_eliminated()
        crossing = [uid for uid in in_play if self.players[uid].total_score >= cap]
        newly = []

        if crossing and len(crossing) >= len(in_play):
            survivor = min(in_play, key=lambda u: self.players[u].total_score)
            for uid in crossing:
                if uid != survivor:
                    self.players[uid].eliminated = True
                    newly.append(uid)
        else:
            for uid in crossing:
                self.players[uid].eliminated = True
                newly.append(uid)

        self.newly_eliminated = newly
        remaining = self.non_eliminated()
        self.game_over = len(remaining) <= 1
        self.winner = remaining[0] if (self.game_over and remaining) else None
        self._migrate_host_if_eliminated()

    def _migrate_host_if_eliminated(self) -> None:
        """Hand the host role to a stand-in once the host is eliminated.

        Picks the connected, still-in-play, non-bot player with the lowest
        cumulative score (most likely to survive longest, so this fires as
        rarely as possible over the rest of the game). Ties break on player
        registration order for a deterministic pick. No-op if the host isn't
        eliminated, or if no eligible stand-in is connected right now.
        """
        host = self.players.get(self.host_id)
        if host is None or not host.eliminated:
            return
        candidates = [
            p for p in self.players.values()
            if p.connected and not p.eliminated and not p.is_bot
        ]
        if not candidates:
            return
        self.host_id = min(candidates, key=lambda p: p.total_score).user_id

    def round_end_payload(self, result: dict) -> dict:
        """Full reveal — hands are public now that the round is over."""
        rows = []
        for uid in self.turn_order:
            player = self.players[uid]
            rows.append({
                "user_id": uid,
                "name": player.name,
                "hand": [c.to_dict() for c in player.hand],
                "hand_total": result["totals"][uid],
                "round_score": player.round_score,
                "total_score": player.total_score,
                "is_safe": player.is_safe,
                "eliminated": player.eliminated,
            })
        return {
            "caller": self.last_caller,
            "caught": self.last_caught,
            "results": rows,
            "players": self.public_players(),
            "eliminated": list(self.newly_eliminated),
            "game_over": self.game_over,
            "winner": self.winner,
            "host_id": self.host_id,
        }

    def standings(self) -> List[dict]:
        """Final-table ordering: survivors first, then by lowest total."""
        rows = [
            {
                "user_id": p.user_id,
                "name": p.name,
                "total_score": p.total_score,
                "eliminated": p.eliminated,
            }
            for p in self.players.values()
        ]
        rows.sort(key=lambda r: (r["eliminated"], r["total_score"]))
        return rows

    def game_end_payload(self) -> dict:
        return {
            "winner": self.winner,
            "winner_name": self.players[self.winner].name if self.winner else None,
            "standings": self.standings(),
            "players": self.public_players(),
            "host_id": self.host_id,
        }

    # ---- timeout handling (driven by the director loop) ----
    def force_timeout(self, user_id: str) -> dict:
        """Resolve a turn that ran out of time. Auto-plays, or removes on the
        configured timeout limit. Returns a small description for broadcasting."""
        player = self.players[user_id]
        player.timeout_count += 1
        removed = player.timeout_count >= self.settings["timeout_limit"]
        drawn = None

        if removed:
            player.eliminated = True
            self.awaiting_draw = False
            self.advance_turn()
            self._migrate_host_if_eliminated()
        elif self.awaiting_draw:
            drawn = self.draw_one(user_id)["card"]
        elif player.hand:
            highest = max(player.hand, key=lambda c: c.value)
            self.apply_throw(user_id, [highest], ACTION_SINGLE)
            drawn = self.draw_one(user_id)["card"]
        else:
            self.advance_turn()

        # A mid-round removal can end the game outright.
        remaining = self.non_eliminated()
        if removed and len(remaining) <= 1:
            self.game_over = True
            self.winner = remaining[0] if remaining else None
            self.state = STATE_GAME_END

        return {
            "removed": removed,
            "timeout_count": player.timeout_count,
            "drawn": drawn.id if drawn else None,
        }

    def hand_for(self, user_id: str) -> List[dict]:
        """A single player's own cards — sent only to that player."""
        player = self.players.get(user_id)
        return [c.to_dict() for c in player.hand] if player else []

    def in_round(self) -> bool:
        return self.state == STATE_IN_TURN

    def reset_for_rematch(self) -> None:
        """Wipe scores/eliminations and return everyone to the lobby.

        Any mid-game host migration (see _migrate_host_if_eliminated) is only
        a stand-in for the rest of that game — restore the room's original
        host now, provided they're still connected to take the role back.
        """
        original = self.players.get(self.original_host_id)
        if original is not None and original.connected:
            self.host_id = self.original_host_id
        for p in self.players.values():
            p.hand = []
            p.round_score = 0
            p.total_score = 0
            p.is_safe = False
            p.eliminated = False
            p.timeout_count = 0
            p.is_spectator = False
            p.pending_join = False
        self.state = STATE_LOBBY
        self.round_number = 0
        self.start_offset = 0
        self.turn_order = []
        self.turn_index = 0
        self.draw_pile = []
        self.discard_pile = []
        self.center_throw = []
        self.last_was_combo = False
        self.awaiting_draw = False
        self.awaiting_draw_ts = 0.0
        self.turns_completed = 0
        self.initial_active = 0
        self.first_orbit_complete = False
        self.last_caller = None
        self.last_caught = False
        self.newly_eliminated = []
        self.game_over = False
        self.winner = None
        self._last_result = None

    # ---- host migration ----
    def migrate_host(self) -> Optional[str]:
        """Promote the next connected player to host. Returns new host id.
        Bot players are never promoted to host — they can't interact with the
        UI. Eliminated players are skipped too — they're spectating, not
        playing, so they'd have no stake in decisions like starting the next
        round. Returns None (host_id left unchanged) if no one qualifies."""
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
