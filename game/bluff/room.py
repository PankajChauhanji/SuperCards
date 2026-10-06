"""Room: the single source of truth for one Bluff game table.

Holds the full game lifecycle: lobby, dealing, turn play, and game end.
"""
import time
import random
from typing import Dict, List, Optional

from game.bluff.settings import MAX_PLAYERS, PODIUM_PLACES
from game.core.player import Player
from game.core.cards import shuffled_deck, rank_code

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
        self.table_theme = "casino"
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
        self.is_showing = False
        # User ids in the order they shed their last card, i.e. finishing places:
        # index 0 is 1st, index 1 is 2nd, and so on. Bluff has no score, so this
        # IS the ranking — see standings() and settings.PODIUM_PLACES.
        self.finish_order: List[str] = []

        # ---- table memory of what Shows have revealed ----
        # Both of these are PUBLIC: a Show flips cards face up for the whole
        # room (`bluff_show_result`), so every human at the table saw them and
        # can remember them. They live on the room rather than inside a bot so
        # that every player's view of the history is the same one, and so they
        # survive a reconnect or a snapshot restore.
        #
        # reveal_log: one entry per resolved Show, used to judge how often a
        # given player's claims have turned out to be true.
        self.reveal_log: List[dict] = []
        # known_cards: user_id -> rank codes currently known to be in that hand.
        # A Show sends the revealed cards to whoever picks the pile up, so their
        # location is known until they next play and we lose track of which
        # cards left. Deliberately erased faster than reality, never slower —
        # over-remembering would make a bot accuse people on stale evidence.
        self.known_cards: Dict[str, List[str]] = {}

        # ---- host's "Shuffle seats" (see request_shuffle) ----
        # Armed by the host, applied at the next fresh round — the moment the
        # pile is empty and no rank is locked, so no play or challenge is ever
        # in flight when neighbours change. ``seat_shuffles`` counts the ones
        # applied, so a client can notice a shuffle from state alone.
        self.shuffle_pending = False
        self.seat_shuffles = 0

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

    def remove_participant(self, user_id: str) -> None:
        """Voluntary quit — remove the player entirely, keeping the game valid.

        Mid-game this repairs the turn rotation, clears the centre pile if the
        quitter owned the live play, migrates the host if needed, and ends the
        game if one (or zero) players remain.
        """
        if user_id not in self.players:
            return
        was_host = self.is_host(user_id)
        in_play = self.state == STATE_IN_TURN

        if in_play and user_id in self.turn_order:
            was_current = self.current_turn_id() == user_id
            idx = self.turn_order.index(user_id)
            self.turn_order.pop(idx)
            if idx < self.turn_index:
                self.turn_index -= 1
            self.turn_index = (self.turn_index % len(self.turn_order)) if self.turn_order else 0
            # If the quitter was the one being (potentially) challenged, retire
            # the live pile so no one can call Show on a player who's gone.
            if self.last_play and self.last_play.get("user_id") == user_id:
                self.dead_pile.extend(self.center_pile)
                self.center_pile = []
                self.target_rank = None
                self.last_play = None
                self.pass_count = 0
            if was_current:
                self.turn_start_ts = time.time()
                self._skip_to_playable()

        self.players.pop(user_id, None)
        # Their remembered cards leave with them; a stale entry would otherwise
        # keep counting toward "copies accounted for" and make bots suspicious
        # of claims that are perfectly possible.
        self.known_cards.pop(user_id, None)

        if was_host:
            self.migrate_host()

        if in_play:
            # A quit can settle the game by leaving nobody to race. Routed
            # through the same check as a normal finish so there is one
            # definition of "the game is over" and one of who won.
            self._maybe_end_game()

    def _skip_to_playable(self) -> None:
        """Advance turn_index to the next player still in the race (no side effects)."""
        n = len(self.turn_order)
        if n == 0:
            return
        for _ in range(n):
            if not self._out_of_play(self.turn_order[self.turn_index % n]):
                self.turn_index %= n
                return
            self.turn_index = (self.turn_index + 1) % n

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

    def in_round(self) -> bool:
        return self.state == STATE_IN_TURN

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

        self.finish_order = []
        self.reveal_log = []
        self.known_cards = {}
        self.shuffle_pending = False
        self.seat_shuffles = 0
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

    # ---- finishing places ------------------------------------------------
    def is_finished(self, user_id: str) -> bool:
        """True once this player has shed their last card and survived the show."""
        return user_id in self.finish_order

    def _out_of_play(self, user_id: str) -> bool:
        """Finished or removed — either way, no longer takes turns."""
        player = self.players.get(user_id)
        return player is None or player.eliminated or self.is_finished(user_id)

    def still_holding(self) -> List[str]:
        """Players still in the race: not finished, not removed."""
        return [u for u in self.turn_order if not self._out_of_play(u)]

    def _confirm_finishers(self) -> bool:
        """Bank the place of anyone whose empty hand has survived the challenge.

        An empty hand is not a finish on its own: under the same-rank rules the
        next player may still call Show on that last play, and a caught bluffer
        picks the pile back up. So a player is only out once an action has
        happened after theirs — which is exactly "they are no longer last_play".

        Returns True if the game ended as a result.
        """
        if not self.last_play:
            return self.game_over

        last_actor_id = self.last_play["user_id"]
        for uid in self.turn_order:
            player = self.players.get(uid)
            if player is None or player.eliminated or self.is_finished(uid):
                continue
            if not player.hand and uid != last_actor_id:
                self.finish_order.append(uid)

        return self._maybe_end_game()

    def _maybe_end_game(self) -> bool:
        """End the game once the result is decided. Returns True if it ended.

        Two ways it is decided, whichever comes first:
          * the podium is full — the places worth playing for are settled;
          * at most one player is still holding cards — there is no race left,
            which is what ends a 2- or 3-player table before the podium binds.
        """
        if self.game_over:
            return True
        if len(self.finish_order) < PODIUM_PLACES and len(self.still_holding()) > 1:
            return False

        self.game_over = True
        self.state = STATE_GAME_END
        ranked = self.standings()
        self.winner = ranked[0]["user_id"] if ranked else None
        return True

    def apply_play(self, user_id: str, cards: List, declared_rank: str) -> None:
        """Player throws cards, claiming they match declared_rank."""
        player = self.players[user_id]
        thrown_ids = {c.id for c in cards}
        player.hand = [c for c in player.hand if c.id not in thrown_ids]

        self._forget_played(user_id, len(cards), declared_rank)
        self.center_pile.extend(cards)
        
        if self.target_rank is None:
            self.target_rank = declared_rank

        self.last_play = {
            "user_id": user_id,
            "cards": cards,
            "declared_rank": declared_rank
        }
        self.pass_count = 0

        # A player whose hand emptied on an earlier turn is now safe from the
        # challenge, so their place is banked here — and the game may be over.
        if self._confirm_finishers():
            return

        self.advance_turn()

    def _forget_played(self, user_id: str, count: int, declared_rank: str) -> None:
        """Drop remembered cards for a player who has just thrown some.

        Their cards went down face down, so there is no telling which ones left
        the hand. Up to `count` remembered cards are forgotten, the declared
        rank first because a player holding what they claim usually plays it.

        Erring toward forgetting is the safe direction: remembering too much
        would have a bot challenge on evidence that is no longer true, while
        remembering too little only costs it an opportunity.
        """
        known = self.known_cards.get(user_id)
        if not known:
            return
        for _ in range(count):
            if not known:
                break
            known.remove(declared_rank) if declared_rank in known else known.pop()
        if not known:
            self.known_cards.pop(user_id, None)

    def apply_pass(self, user_id: str) -> None:
        """Player passes. If pass_count hits (active_count - 1), clear table."""
        swept = False
        self.pass_count += 1
        
        # A pass is also an action, so it too closes the challenge window on
        # whoever played last.
        if self._confirm_finishers():
            return

        # If everyone passed back to the last player who played, clear the table.
        # Counted against players who can still act: a finished player never
        # passes, so including them would mean the pile could never be swept.
        active_count = len(self.still_holding())
        if self.pass_count >= active_count - 1 and self.last_play:
            last_actor = self.last_play["user_id"]
            if not self.players[last_actor].hand:
                # Everyone declined to challenge their last play: their place is
                # banked, and the pile they left goes out of the game with them.
                if not self.is_finished(last_actor):
                    self.finish_order.append(last_actor)
                self.dead_pile.extend(self.center_pile)
                self.center_pile = []
                self.target_rank = None
                self.last_play = None
                self.pass_count = 0
                if self._maybe_end_game():
                    return
                self.advance_turn()
                self._apply_pending_shuffle()     # pile swept: a fresh round
                return

            self.dead_pile.extend(self.center_pile)
            self.center_pile = []
            self.target_rank = None
            self.last_play = None
            self.pass_count = 0
            swept = True
            # Turn remains with the player who won the table (the last person who played)
            self.turn_index = self.turn_order.index(self.current_turn_id()) # actually it naturally advances back to them
            # Wait, if pass_count == active_count - 1, the NEXT turn is the person who played last.
            # So advancing turn will naturally put it on them. Let's just advance turn normally.
            
        self.advance_turn()
        if swept:
            self._apply_pending_shuffle()         # pile swept: a fresh round

    # ---- shuffle seats ----------------------------------------------------
    def _round_is_fresh(self) -> bool:
        """No live play: nothing on the pile, no rank locked, no reveal running."""
        return (self.last_play is None and not self.center_pile
                and self.target_rank is None and not self.is_showing)

    def request_shuffle(self) -> str:
        """The host pressed Shuffle seats. Returns "applied", "pending" or "cancelled".

        Pressing again while one is pending cancels it. At a fresh round it
        applies at once; mid-round it waits for the pile to clear.
        """
        if self.state != STATE_IN_TURN or self.game_over:
            return "cancelled"
        if getattr(self, "shuffle_pending", False):
            self.shuffle_pending = False
            return "cancelled"
        self.shuffle_pending = True
        if self._round_is_fresh():
            self._apply_pending_shuffle()
            return "applied"
        return "pending"

    def _apply_pending_shuffle(self) -> bool:
        """Re-seat everyone at random. The player about to lead keeps the lead.

        Only the rotation changes: the same players, the same hands, the same
        finishing places. Finished and removed players stay in the list and go
        on being skipped by advance_turn, as before.
        """
        if not getattr(self, "shuffle_pending", False) or self.game_over or not self.turn_order:
            return False
        leader = self.current_turn_id()
        random.shuffle(self.turn_order)
        if leader in self.turn_order:
            self.turn_index = self.turn_order.index(leader)
        self.shuffle_pending = False
        self.seat_shuffles = getattr(self, "seat_shuffles", 0) + 1
        return True

    def apply_show(self, user_id: str) -> dict:
        """Player calls Show. Determines the result, but doesn't alter piles yet."""
        if not self.last_play:
            return {}

        defender_id = self.last_play["user_id"]
        cards = self.last_play["cards"]
        declared_rank = self.last_play["declared_rank"]

        is_bluff = any(rank_code(c.rank) != declared_rank for c in cards)
        
        loser_id = defender_id if is_bluff else user_id
        winner_id = user_id if is_bluff else defender_id

        return {
            "challenger": user_id,
            "defender": defender_id,
            "declared_rank": declared_rank,
            "is_bluff": is_bluff,
            "revealed_cards": [c.to_dict() for c in cards],
            "loser": loser_id,
            "winner": winner_id,
        }

    def resolve_show(self, result: dict) -> None:
        """Applies the consequence of a show after the delay."""
        loser_id = result["loser"]
        winner_id = result["winner"]

        # Record what the table just saw. The cards were flipped face up for
        # everyone, so this is public history, not a private advantage.
        revealed = [c["code"] for c in result.get("revealed_cards", [])]
        self.reveal_log.append({
            "defender": result["defender"],
            "challenger": result["challenger"],
            "declared_rank": result.get("declared_rank"),
            "revealed": revealed,
            "was_bluff": bool(result["is_bluff"]),
            "loser": loser_id,
        })
        # Whoever picks the pile up demonstrably now holds the revealed cards.
        self.known_cards.setdefault(loser_id, []).extend(revealed)

        # Loser picks up the entire center pile
        self.players[loser_id].hand.extend(self.center_pile)

        self.center_pile = []
        self.target_rank = None
        self.pass_count = 0
        self.last_play = None

        # A challenge is the strongest confirmation there is: whoever is left
        # holding nothing after it has survived the only thing that could have
        # given them cards back, so their place is banked here rather than
        # waiting for a later action. Doing it now also keeps the turn off a
        # player with no cards, which would otherwise stall the round — the
        # defender who truthfully played their last cards is exactly that case.
        for uid in self.turn_order:
            player = self.players.get(uid)
            if player is None or player.eliminated or self.is_finished(uid):
                continue
            if not player.hand:
                self.finish_order.append(uid)
        if self._maybe_end_game():
            return

        self.turn_index = self.turn_order.index(winner_id)
        self.turn_start_ts = time.time()
        # The winner of the show leads the next round — unless they were the one
        # who just went out, in which case it moves on.
        if self._out_of_play(winner_id):
            self.advance_turn()
        # The pile is empty and a fresh round is about to be led: the moment a
        # pending host shuffle may re-seat the table, leader unchanged.
        self._apply_pending_shuffle()

    def advance_turn(self) -> None:
        """Hand the turn to the next player still holding cards.

        A player who has finished keeps their seat on the table but is skipped
        here — they have nothing left to play, and asking them to pass would
        stall the round for everyone behind them.
        """
        n = len(self.turn_order)
        if n == 0:
            return

        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            if not self._out_of_play(self.turn_order[self.turn_index]):
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
            # Carried in the public state rather than announced as a one-shot
            # event: a client that missed the announcement would show a finished
            # player as still playing until it reloaded, and state survives a
            # resync where an event does not (see sockets/sync.py).
            "finish_order": list(self.finish_order),
            # Host's Shuffle seats: queued for the next fresh round, and how many
            # have been applied (a client notices a shuffle by this count rising).
            "shuffle_pending": bool(getattr(self, "shuffle_pending", False)),
            "seat_shuffles": int(getattr(self, "seat_shuffles", 0)),
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
            # Removing a player can leave too few to race on — same check as a
            # normal finish.
            if not self._maybe_end_game():
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

    def standings(self) -> List[dict]:
        """Final table, best first.

        Bluff scores nothing, so the ranking has two tiers and they are not
        comparable to each other:

          * players who went out, in the order they did it — that order is the
            whole point of the game;
          * everyone still holding cards, fewest first. Cards held, not their
            face values: in Bluff a card is a card, and the player one turn from
            going out is doing better than the one nursing a dozen, however
            those dozen happen to add up.

        Ties among the unfinished keep turn order, so the result is stable and
        two players on the same count do not swap places between renders.
        """
        rows = []
        for place, uid in enumerate(self.finish_order, start=1):
            player = self.players.get(uid)
            if player is None:
                continue
            rows.append({
                "user_id": uid,
                "name": player.name,
                "cards_left": 0,
                "finished": True,
                "place": place,
                "eliminated": player.eliminated,
            })

        remaining = [
            self.players[u] for u in self.turn_order
            if u not in self.finish_order and u in self.players
        ]
        # Removed players rank below everyone still in the race, however few
        # cards they happened to be holding when they were taken out.
        remaining.sort(key=lambda p: (p.eliminated, len(p.hand)))
        for offset, player in enumerate(remaining):
            rows.append({
                "user_id": player.user_id,
                "name": player.name,
                "cards_left": len(player.hand),
                "finished": False,
                "place": len(self.finish_order) + offset + 1,
                "eliminated": player.eliminated,
            })
        return rows

    def game_end_payload(self) -> dict:
        return {
            "winner": self.winner,
            "winner_name": self.players[self.winner].name if self.winner else None,
            "standings": self.standings(),
            "finish_order": list(self.finish_order),
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
        self.finish_order = []
        self.reveal_log = []
        self.known_cards = {}
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
        self.shuffle_pending = False
        self.seat_shuffles = 0

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
