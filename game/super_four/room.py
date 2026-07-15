"""Super 4 room — authoritative game state for one table.

Implements the shared Room interface (game.core.room_base.RoomProtocol) plus the
Super-4-specific turn engine: 4 fixed face-down slots per player, a per-viewer
knowledge model (so hidden cards never leak), and the draw -> keep / discard /
match-own turn loop. Powers, Stop/reveal, and cross-player matching are layered on
in sibling methods (see powers.py and later tasks).

Hidden information is the core mechanic, so every payload is built from
`known[viewer]`: a viewer only ever receives the faces of positions they
legitimately know. See DESIGN.md.
"""
import time
from typing import Dict, List, Optional, Tuple

from game.core.player import Player
from game.core.cards import shuffled_deck
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.super_four import powers
from game.super_four.scoring import hand_total, round_deltas
from game.super_four.settings import (
    MAX_PLAYERS, SLOTS, PREVIEW_SLOTS,
)

POWER_RANKS = {7, 8, 9, 10, 11, 12, 13}

# Per-turn phases (within STATE_IN_TURN):
PHASE_DRAW = "draw"       # current player must draw (or call Stop)
PHASE_DECIDE = "decide"   # current player drew; must keep / discard / match-own
PHASE_POWER = "power"     # a discarded power card is being resolved (powers.py)
PHASE_MATCH = "match"     # a discard is open for cross-player matching (short window)
PHASE_PREVIEW = "preview" # initial private-memory period; host may end it early


class Room:
    game_type = "super_four"

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

        # ---- round state (populated by start_round) ----
        self.slots: Dict[str, List[Optional[object]]] = {}   # uid -> [Card|None,...]
        self.known: Dict[str, set] = {}      # viewer uid -> {(owner_uid, slot_idx)}
        self.draw_pile: List = []
        self.discard_pile: List = []         # all discarded cards (for reshuffle)
        self.center: Optional[object] = None  # top face-up card on the table
        self.turn_order: List[str] = []
        self.turn_index = 0
        self.turns_completed = 0
        self.initial_active = 0
        self.first_orbit_complete = False
        self.phase = PHASE_DRAW
        self.drawn: Optional[object] = None   # currently drawn card (private to drawn_by)
        self.drawn_by: Optional[str] = None
        self.pending_power: Optional[dict] = None   # {"by": uid, "rank": int}
        # Cross-player match window (PHASE_MATCH)
        self.match_card: Optional[object] = None    # the center card being matched
        self.match_discarder: Optional[str] = None  # who discarded it (can't self-match)
        self.match_deadline: float = 0.0
        self.match_attempted: set = set()           # players who already tried (once each)
        self.transient_reveals: List[dict] = []     # public one-shot reveals (failed matches)
        self.start_offset = 0
        self.turn_start_ts = 0.0
        self.preview_deadline = 0.0          # while now < this, owners see their preview
        # Stop / round-end / game-end
        self.stop_caller: Optional[str] = None
        self.final_turns_left = 0
        self.last_result: Optional[dict] = None
        self.newly_eliminated: List[str] = []
        self.game_over = False
        self.winner: Optional[str] = None

    # ================= registration / attachment =================
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

    def migrate_host(self) -> Optional[str]:
        """Promote another connected human to host; returns the new host id."""
        if self.players.get(self.host_id) and self.players[self.host_id].connected:
            return None
        for uid, p in self.players.items():
            if p.connected and not p.is_bot:
                self.host_id = uid
                return uid
        return None

    # ================= queries =================
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
        out = []
        for uid, p in self.players.items():
            view = {
                "user_id": p.user_id,
                "name": p.name,
                "score": p.total_score,
                "connected": p.connected,
                "eliminated": p.eliminated,
                "color": p.color_index,
                "is_spectator": p.is_spectator,
                "pending_join": p.pending_join,
                "is_bot": p.is_bot,
                # Super-4 specific: per-slot occupancy (never the card faces).
                "slots": [c is not None for c in self.slots.get(uid, [])],
            }
            out.append(view)
        return out

    # ================= knowledge model =================
    def _know(self, viewer: str, owner: str, slot: int) -> None:
        self.known.setdefault(viewer, set()).add((owner, slot))

    def _reveal_public(self, owner: str, slot: int) -> None:
        """Everyone now knows this position's current card (a public reveal)."""
        for viewer in self.players:
            self._know(viewer, owner, slot)

    def _forget_all(self, owner: str, slot: int) -> None:
        for viewer in self.players:
            self.known.get(viewer, set()).discard((owner, slot))

    def _swap_knowledge(self, a: Tuple[str, int], b: Tuple[str, int]) -> None:
        """Knowledge follows the card: exchange each viewer's bits for a and b."""
        for viewer in self.players:
            ks = self.known.setdefault(viewer, set())
            has_a, has_b = a in ks, b in ks
            ks.discard(a); ks.discard(b)
            if has_a:
                ks.add(b)
            if has_b:
                ks.add(a)

    # ================= round lifecycle =================
    def start_round(self) -> None:
        active = [
            uid for uid, p in self.players.items()
            if p.connected and not p.eliminated and not p.is_spectator
        ]
        deck = shuffled_deck(self.settings.get("num_decks", 1))

        self.slots = {}
        self.known = {uid: set() for uid in self.players}
        for player in self.players.values():
            player.round_score = 0
        for uid in active:
            self.slots[uid] = [deck.pop() for _ in range(SLOTS)]
            # Preview: the owner learns their first two slots.
            for s in PREVIEW_SLOTS:
                self._know(uid, uid, s)

        self.draw_pile = deck
        self.discard_pile = []
        self.center = None
        self.turn_order = active
        self.turn_index = (self.start_offset % len(active)) if active else 0
        self.start_offset += 1
        self.turns_completed = 0
        self.initial_active = len(active)
        self.first_orbit_complete = False
        self.phase = PHASE_PREVIEW
        self.drawn = None
        self.drawn_by = None
        self.pending_power = None
        self.match_card = None
        self.match_discarder = None
        self.match_deadline = 0.0
        self.match_attempted = set()
        self.transient_reveals = []
        self.stop_caller = None
        self.final_turns_left = 0
        self.last_result = None
        self.newly_eliminated = []
        self.turn_start_ts = 0.0
        # The host may start early, but a preview can never run longer than 30s.
        self.preview_deadline = time.time() + min(30, int(self.settings.get("preview_seconds", 30)))
        self.round_number += 1
        self.state = STATE_IN_TURN

    def begin_play(self) -> bool:
        """End the initial memory preview and start the first turn."""
        if self.state != STATE_IN_TURN or self.phase != PHASE_PREVIEW:
            return False
        self.phase = PHASE_DRAW
        self.turn_start_ts = time.time()
        return True

    def expire_preview(self) -> bool:
        """Start play when the server-side maximum preview time has elapsed."""
        if self.phase == PHASE_PREVIEW and time.time() >= self.preview_deadline:
            return self.begin_play()
        return False

    def current_turn_id(self) -> Optional[str]:
        if not self.turn_order:
            return None
        return self.turn_order[self.turn_index % len(self.turn_order)]

    def _reshuffle_if_needed(self) -> bool:
        """Refill the draw pile from the discard pile (excluding the center)."""
        if self.draw_pile:
            return False
        import random
        pool = list(self.discard_pile)
        self.discard_pile = []
        random.shuffle(pool)
        self.draw_pile = pool
        return True

    def _advance_turn(self) -> None:
        """Move to the next player's draw phase; track orbit + Stop countdown."""
        self.turns_completed += 1
        if not self.first_orbit_complete and self.turns_completed >= self.initial_active:
            self.first_orbit_complete = True
        self.turn_index = (self.turn_index + 1) % len(self.turn_order)
        self.phase = PHASE_DRAW
        self.drawn = None
        self.drawn_by = None
        self.transient_reveals = []
        self.turn_start_ts = time.time()
        # Final orbit: once play returns to the Stop caller, reveal & score.
        if self.stop_caller is not None and self.current_turn_id() == self.stop_caller:
            self._finalize_round()

    # ================= turn actions =================
    def draw(self, user_id: str) -> Optional[dict]:
        """Current player privately draws the top card."""
        if self.state != STATE_IN_TURN or self.phase != PHASE_DRAW:
            return None
        if self.current_turn_id() != user_id:
            return None
        reshuffled = self._reshuffle_if_needed()
        if not self.draw_pile:
            return None  # no cards anywhere (degenerate)
        card = self.draw_pile.pop()
        self.drawn = card
        self.drawn_by = user_id
        self.phase = PHASE_DECIDE
        return {"card": card, "reshuffled": reshuffled}

    def keep(self, user_id: str, slot: int) -> bool:
        """Swap the private drawn card into a slot and discard the old card.

        The replacement remains hidden. Only the old card landing face-up on the
        center is public, and it may open a match window. A kept card never fires
        a power.
        """
        if self.phase != PHASE_DECIDE or self.drawn_by != user_id:
            return False
        my = self.slots.get(user_id)
        if my is None or slot < 0 or slot >= len(my):
            return False
        old = my[slot]
        my[slot] = self.drawn
        if old is not None:
            self._to_center(old)
        # A newly kept card is face-down to everyone, including its owner unless
        # they later earn knowledge through a power.
        self._forget_all(user_id, slot)
        self.drawn = None
        self.drawn_by = None
        if old is not None:
            self._after_discard(user_id)
        else:
            self._advance_turn()
        return True

    def discard(self, user_id: str) -> Optional[dict]:
        """Discard the drawn card to the center.

        If it is a power card (7-13) with a valid target, enter the power phase and
        DO NOT advance the turn (powers.py resolves it). Otherwise advance.
        Returns {"power_rank": int|None}.
        """
        if self.phase != PHASE_DECIDE or self.drawn_by != user_id:
            return None
        card = self.drawn
        self._to_center(card)
        self.drawn = None
        self.drawn_by = None

        if card.rank in POWER_RANKS and self._power_has_target(user_id, card.rank):
            self.phase = PHASE_POWER
            self.pending_power = {"by": user_id, "rank": card.rank}
            return {"power_rank": card.rank}
        self._after_discard(user_id)
        return {"power_rank": None}

    def match_own(self, user_id: str, slot: int) -> Optional[dict]:
        """On your turn, attempt to match the drawn card against one of your slots.

        Correct -> both discarded (slot emptied). Wrong -> slot revealed, drawn
        discarded, penalty card taken. Either way the turn ends.
        """
        if self.phase != PHASE_DECIDE or self.drawn_by != user_id:
            return None
        my = self.slots.get(user_id)
        if my is None or slot < 0 or slot >= len(my) or my[slot] is None:
            return None
        drawn = self.drawn
        target = my[slot]
        success = (target.rank == drawn.rank)
        if success:
            self._to_center(target)      # matched card leaves
            self._to_center(drawn)       # drawn card leaves too
            my[slot] = None
            self._forget_all(user_id, slot)
            self.drawn = None
            self.drawn_by = None
            self._after_discard(user_id)
            return {"success": True, "slot": slot}
        # Wrong: the selected card stays hidden in its slot; the drawn card is
        # discarded and the player takes a hidden penalty card.
        self._to_center(drawn)
        penalty = self._take_penalty(user_id)
        self.drawn = None
        self.drawn_by = None
        self._after_discard(user_id)
        return {"success": False, "slot": slot, "penalty": penalty}

    # ================= cross-player match window =================
    def _move_knowledge(self, src: Tuple[str, int], dst: Tuple[str, int]) -> None:
        """A card moved from src position to dst: knowledge follows it."""
        for viewer in self.players:
            ks = self.known.setdefault(viewer, set())
            had = src in ks
            ks.discard(src)
            ks.discard(dst)
            if had:
                ks.add(dst)

    def _after_discard(self, discarder: str) -> None:
        """After a card lands on the center, open a match window (or advance)."""
        window = int(self.settings.get("match_window", 0))
        if window > 0 and self.center is not None:
            self.phase = PHASE_MATCH
            self.match_card = self.center
            self.match_discarder = discarder
            self.match_attempted = set()
            self.match_deadline = time.time() + window
        else:
            self._advance_turn()

    def _close_match_window(self) -> None:
        self.match_card = None
        self.match_discarder = None
        self.match_deadline = 0.0
        self.match_attempted = set()
        self._advance_turn()

    def match_seconds_left(self) -> int:
        if self.phase != PHASE_MATCH:
            return 0
        return max(0, int(self.match_deadline - time.time()))

    def _can_attempt_match(self, user_id: str) -> bool:
        return (
            self.phase == PHASE_MATCH
            and user_id not in self.match_attempted
            and user_id in self.players
            and not self.players[user_id].eliminated
            and not self.players[user_id].is_spectator
        )

    def react_match(self, user_id: str, selections: list, replacements: list) -> Optional[dict]:
        """Attempt the open, real-time match window as one atomic operation.

        ``selections`` contains any number of ``{owner, slot}`` positions.  All
        must match the face-up center rank.  The actor may select their own or
        opponents' cards.  For every opponent card removed, they must choose one
        distinct card of their own to transfer into that exact slot via
        ``replacements``.  A wrong attempt leaves all selected cards where they
        were, gives the actor a penalty card, and leaves the window open for the
        other players.  The first *successful* request closes the window.
        """
        if not self._can_attempt_match(user_id) or not isinstance(selections, list):
            return None
        if not selections or self.match_card is None:
            return None

        selected = []
        seen = set()
        for item in selections:
            if not isinstance(item, dict):
                return None
            owner = item.get("owner")
            try:
                slot = int(item.get("slot"))
            except (TypeError, ValueError):
                return None
            key = (owner, slot)
            if key in seen or not self._occupied(owner, slot):
                return None
            seen.add(key)
            selected.append(key)

        # An invalid rank is a genuine failed throw: no card face is published,
        # the card stays put, and the player can no longer retry this window.
        if any(self.slots[owner][slot].rank != self.match_card.rank for owner, slot in selected):
            self.match_attempted.add(user_id)
            penalty = self._take_penalty(user_id)
            return {"success": False, "by": user_id, "penalty": penalty}

        opponent_targets = [key for key in selected if key[0] != user_id]
        if not isinstance(replacements, list):
            return None
        replacement_by_target = {}
        used_give_slots = set()
        for item in replacements:
            if not isinstance(item, dict):
                return None
            try:
                target = (item.get("target_owner"), int(item.get("target_slot")))
                give_slot = int(item.get("from_slot"))
            except (TypeError, ValueError):
                return None
            if target in replacement_by_target or give_slot in used_give_slots:
                return None
            replacement_by_target[target] = give_slot
            used_give_slots.add(give_slot)
        if set(replacement_by_target) != set(opponent_targets):
            return None
        for give_slot in used_give_slots:
            # A transfer card must be an occupied card of the actor and cannot
            # also be one of the cards thrown to the center in this reaction.
            if not self._occupied(user_id, give_slot) or (user_id, give_slot) in seen:
                return None

        # Validate first, then mutate.  Cards transferred into opponent positions
        # remain face-down; knowledge follows the physical transfer card.
        transfers = [(target, (user_id, give_slot))
                     for target, give_slot in replacement_by_target.items()]
        for owner, slot in selected:
            self._to_center(self.slots[owner][slot])
            self.slots[owner][slot] = None
            self._forget_all(owner, slot)
        for (target_owner, target_slot), (from_owner, from_slot) in transfers:
            given = self.slots[from_owner][from_slot]
            self.slots[from_owner][from_slot] = None
            self.slots[target_owner][target_slot] = given
            self._move_knowledge((from_owner, from_slot), (target_owner, target_slot))

        self._close_match_window()
        return {
            "success": True,
            "by": user_id,
            "discarded": [{"owner": owner, "slot": slot} for owner, slot in selected],
            "transfers": [
                {"target_owner": target[0], "target_slot": target[1], "from_slot": source[1]}
                for target, source in transfers
            ],
        }

    def match_center_own(self, user_id: str, slot: int) -> Optional[dict]:
        """Compatibility wrapper for an own-card one-card reaction."""
        return self.react_match(user_id, [{"owner": user_id, "slot": slot}], [])

    def _highest_give_slot(self, user_id: str) -> int:
        """Slot of the acting player's highest-value card to give away (or -1)."""
        from game.super_four.scoring import card_value
        best, best_i = None, -1
        for i, c in enumerate(self.slots.get(user_id, [])):
            if c is None:
                continue
            v = card_value(c)
            if best is None or v > best:
                best, best_i = v, i
        return best_i

    def match_center_opp(self, user_id: str, target_uid: str, target_slot: int) -> Optional[dict]:
        """Deprecated one-card opponent reaction; callers must choose a transfer.

        Kept only to reject old clients safely instead of applying the former
        auto-give-highest rule.
        """
        return None

    def expire_match_window(self) -> bool:
        """Called by the director when the window's deadline passes."""
        if self.phase == PHASE_MATCH and time.time() >= self.match_deadline:
            self._close_match_window()
            return True
        return False

    # ================= Stop / round end =================
    def call_stop(self, user_id: str) -> Optional[dict]:
        """Declare Stop at the start of your turn (before drawing).

        Triggers the final orbit: every other player gets one more turn; when play
        returns to the caller (_advance_turn), the round is finalized and revealed.
        """
        if self.state != STATE_IN_TURN or self.phase != PHASE_DRAW:
            return None
        if self.current_turn_id() != user_id:
            return None
        if not self.first_orbit_complete:
            return None
        if self.stop_caller is not None:
            return None
        self.stop_caller = user_id
        # Caller forfeits their draw; play moves on. If no one else can act, this
        # returns straight to the caller and finalizes immediately.
        self._advance_turn()
        return {"caller": user_id}

    def _finalize_round(self) -> None:
        totals = {uid: hand_total(self.slots.get(uid, [])) for uid in self.turn_order}
        result = round_deltas(totals, self.stop_caller, self.settings)
        for uid, delta in result["deltas"].items():
            if uid in self.players:
                self.players[uid].round_score = delta
                self.players[uid].total_score += delta   # cumulative; lower is better

        # Elimination: cumulative at/above exit_score -> out (spectates the rest).
        exit_score = int(self.settings.get("exit_score", 10))
        self.newly_eliminated = []
        for uid in self.turn_order:
            p = self.players.get(uid)
            if p and not p.eliminated and p.total_score >= exit_score:
                p.eliminated = True
                self.newly_eliminated.append(uid)

        self.last_result = result
        self.phase = PHASE_DRAW
        self.drawn = None
        self.drawn_by = None
        self.pending_power = None

        # Game over after the configured rounds, or when <=1 player is left in.
        rounds = int(self.settings.get("rounds", 5))
        remaining = [uid for uid, p in self.players.items()
                     if not p.eliminated and not p.is_spectator]
        if self.round_number >= rounds or len(remaining) <= 1:
            self.game_over = True
            self.winner = self._lowest_cumulative()
            self.state = STATE_GAME_END
        else:
            self.state = STATE_ROUND_END

    def _lowest_cumulative(self) -> Optional[str]:
        contenders = {uid: p.total_score for uid, p in self.players.items() if not p.is_spectator}
        if not contenders:
            return None
        low = min(contenders.values())
        lows = [uid for uid, s in contenders.items() if s == low]
        return lows[0] if len(lows) == 1 else None

    def round_end_payload(self, result=None) -> dict:
        result = result or self.last_result or {}
        reveal = {
            uid: [(c.to_dict() if c is not None else None) for c in self.slots.get(uid, [])]
            for uid in self.turn_order
        }
        return {
            "caller": self.stop_caller,
            "winners": result.get("winners", []),
            "caller_won": result.get("caller_won", False),
            "deltas": result.get("deltas", {}),
            "totals": result.get("totals", {}),
            "reveal": reveal,
            "newly_eliminated": list(self.newly_eliminated),
            "round_number": self.round_number,
            "rounds": int(self.settings.get("rounds", 5)),
            "game_over": self.game_over,
            "winner": self.winner,
            "state": self.state,
            "players": self.public_players(),
        }

    def game_end_payload(self) -> dict:
        return self.round_end_payload()

    def reset_for_rematch(self) -> None:
        for p in self.players.values():
            p.total_score = 0
            p.round_score = 0
            p.eliminated = False
            p.timeout_count = 0
        if self.players.get(self.original_host_id):
            self.host_id = self.original_host_id
        self.slots = {}
        self.known = {}
        self.draw_pile = []
        self.discard_pile = []
        self.center = None
        self.turn_order = []
        self.turn_index = 0
        self.drawn = None
        self.drawn_by = None
        self.pending_power = None
        self.transient_reveals = []
        self.stop_caller = None
        self.winner = None
        self.last_result = None
        self.round_number = 0
        self.start_offset = 0
        self.state = STATE_LOBBY

    def hand_for(self, user_id: str):
        """Present for the RoomProtocol; Super 4 sends state via private_view()."""
        return []

    # ================= helpers used by actions & later tasks =================
    def _to_center(self, card) -> None:
        """Send the previous center card to the discard pile; card becomes center."""
        if self.center is not None:
            self.discard_pile.append(self.center)
        self.center = card

    def _take_penalty(self, user_id: str) -> bool:
        """Give a player one face-down penalty card (unknown to everyone)."""
        self._reshuffle_if_needed()
        if not self.draw_pile:
            return False
        card = self.draw_pile.pop()
        self.slots.setdefault(user_id, []).append(card)
        # New position is unknown to all (drawn face-down from the deck).
        return True

    def _opponents_with_cards(self, user_id: str) -> List[str]:
        return [
            uid for uid in self.turn_order
            if uid != user_id and any(c is not None for c in self.slots.get(uid, []))
        ]

    def _power_has_target(self, user_id: str, rank: int) -> bool:
        """Whether the power for this rank has any legal target right now."""
        if powers.needs_opponent(rank):
            return bool(self._opponents_with_cards(user_id))
        # peek_own — needs at least one of your own cards
        return any(c is not None for c in self.slots.get(user_id, []))

    # ================= power resolution =================
    def _valid_power(self, user_id: str, kind: str) -> bool:
        return (
            self.phase == PHASE_POWER
            and self.pending_power is not None
            and self.pending_power.get("by") == user_id
            and powers.power_kind(self.pending_power.get("rank")) == kind
        )

    def _occupied(self, owner: str, slot: int) -> bool:
        cards = self.slots.get(owner)
        return cards is not None and 0 <= slot < len(cards) and cards[slot] is not None

    def _swap_positions(self, a: Tuple[str, int], b: Tuple[str, int]) -> None:
        (o1, s1), (o2, s2) = a, b
        self.slots[o1][s1], self.slots[o2][s2] = self.slots[o2][s2], self.slots[o1][s1]
        self._swap_knowledge(a, b)

    def _end_power(self) -> None:
        by = self.pending_power.get("by") if self.pending_power else self.current_turn_id()
        self.pending_power = None
        # The discarded power card (now on the center) is itself matchable.
        self._after_discard(by)

    def power_peek_own(self, user_id: str, slot: int) -> Optional[dict]:
        """7/8: privately look at one of your own cards."""
        if not self._valid_power(user_id, powers.PEEK_OWN):
            return None
        if not self._occupied(user_id, slot):
            return None
        self._know(user_id, user_id, slot)
        card = self.slots[user_id][slot]
        self._end_power()
        return {"peeked": {"owner": user_id, "slot": slot, "card": card.to_dict()}}

    def power_peek_opp(self, user_id: str, opp: str, slot: int) -> Optional[dict]:
        """9/10: privately look at one opponent card."""
        if not self._valid_power(user_id, powers.PEEK_OPP):
            return None
        if opp == user_id or not self._occupied(opp, slot):
            return None
        self._know(user_id, opp, slot)
        card = self.slots[opp][slot]
        self._end_power()
        return {"peeked": {"owner": opp, "slot": slot, "card": card.to_dict()}}

    def power_blind_swap(self, user_id: str, own_slot: int, opp: str, opp_slot: int) -> Optional[dict]:
        """11/12: swap one of yours with an opponent's — no reveal to anyone."""
        if not self._valid_power(user_id, powers.BLIND_SWAP):
            return None
        if opp == user_id or not self._occupied(user_id, own_slot) or not self._occupied(opp, opp_slot):
            return None
        self._swap_positions((user_id, own_slot), (opp, opp_slot))
        self._end_power()
        return {"swap": {"a": {"owner": user_id, "slot": own_slot},
                         "b": {"owner": opp, "slot": opp_slot}}}

    def power_king_look(self, user_id: str, own_slot: int, opp: str, opp_slot: int) -> Optional[dict]:
        """King step 1: privately look at one of yours + one opponent's."""
        if not self._valid_power(user_id, powers.KING):
            return None
        if opp == user_id or not self._occupied(user_id, own_slot) or not self._occupied(opp, opp_slot):
            return None
        self._know(user_id, user_id, own_slot)
        self._know(user_id, opp, opp_slot)
        self.pending_power["positions"] = {"own_slot": own_slot, "opp": opp, "opp_slot": opp_slot}
        a = self.slots[user_id][own_slot]
        b = self.slots[opp][opp_slot]
        return {"looked": [
            {"owner": user_id, "slot": own_slot, "card": a.to_dict()},
            {"owner": opp, "slot": opp_slot, "card": b.to_dict()},
        ]}

    def power_king_decide(self, user_id: str, do_swap: bool) -> Optional[dict]:
        """King step 2: swap the two looked-at cards, or leave them."""
        if not self._valid_power(user_id, powers.KING):
            return None
        pos = (self.pending_power or {}).get("positions")
        if pos is None:
            return None  # must look first
        if do_swap:
            self._swap_positions((user_id, pos["own_slot"]), (pos["opp"], pos["opp_slot"]))
        self._end_power()
        return {"swapped": bool(do_swap)}

    def power_skip(self, user_id: str) -> bool:
        """End a pending power without acting — used by the director on timeout."""
        if self.phase != PHASE_POWER or not self.pending_power or self.pending_power.get("by") != user_id:
            return False
        self._end_power()
        return True

    # ================= views (privacy-safe) =================
    def public_round_state(self) -> dict:
        """Snapshot every player may see — NO hidden card faces."""
        return {
            "game_type": self.game_type,
            "state": self.state,
            "phase": self.phase,
            "round_number": self.round_number,
            "host_id": self.host_id,
            "settings": self.settings,
            "table_theme": self.table_theme,
            "current_turn": self.current_turn_id(),
            "turn_order": list(self.turn_order),
            "first_orbit_complete": self.first_orbit_complete,
            "stop_caller": self.stop_caller,
            "preview_seconds_left": self.preview_seconds_left(),
            "deck_count": len(self.draw_pile),
            # Draws are private.  The public table only says that the active
            # player is deciding; the actual card is supplied in private_view.
            "drawn": None,
            "drawn_by": self.drawn_by,
            "draw_pending": self.drawn is not None,
            "center": self.center.to_dict() if self.center else None,
            "pending_power": self.pending_power,
            "match": None if self.phase != PHASE_MATCH else {
                "card": self.match_card.to_dict() if self.match_card else None,
                "discarder": self.match_discarder,
                "seconds_left": self.match_seconds_left(),
                "attempted": list(self.match_attempted),
            },
            "transient_reveals": list(self.transient_reveals),
            "turn_seconds_left": self.turn_seconds_left(),
            "players": self.public_players(),
        }

    def private_view(self, viewer: str) -> dict:
        """Private transient data for ``viewer`` without persistent card leaks.

        Initial preview cards are included only while the preview phase is live.
        Power results are delivered by their targeted one-shot socket events, so
        reconnects and routine state refreshes never reveal a card face merely
        because a player once saw it.
        """
        known_cards = []
        if self.phase == PHASE_PREVIEW and time.time() < self.preview_deadline:
            for (owner, slot) in sorted(self.known.get(viewer, set())):
                if owner != viewer:
                    continue
                cards = self.slots.get(owner)
                if cards is None or slot >= len(cards) or cards[slot] is None:
                    continue
                known_cards.append({"owner": owner, "slot": slot, "card": cards[slot].to_dict()})
        private_drawn = None
        if viewer == self.drawn_by and self.drawn is not None:
            private_drawn = self.drawn.to_dict()
        return {"your_id": viewer, "known": known_cards, "drawn": private_drawn}

    def turn_seconds_left(self) -> int:
        limit = int(self.settings.get("turn_timer", 30))
        if self.state != STATE_IN_TURN:
            return limit
        return max(0, limit - int(time.time() - self.turn_start_ts))

    def preview_seconds_left(self) -> int:
        if self.state != STATE_IN_TURN:
            return 0
        return max(0, int(self.preview_deadline - time.time()))
