"""Room: the single source of truth for one Poker (No-Limit Hold'em) table.

The rules are in docs/poker_rules.md; this file implements them. The shape
follows the other variants — a pure state machine with no I/O, so the socket
layer (sockets/gameplay/poker.py) only validates who is asking and broadcasts
what changed, and the engine can be tested without a server.

Vocabulary, matching the rules doc:
  * a **game** is the whole session; a **round** is one deal (a poker "hand");
  * a **stage** (``street``) is one of preflop / flop / turn / river;
  * ``contributed`` is what a player has put in over the round, ``bets`` what
    they have put in on the current street only.

Lifecycle states are the shared ones (game/core/states.py). Inside
STATE_IN_TURN the round is either taking bets (PHASE_BETTING) or, once nobody
can bet any more, dealing the rest of the board one street at a time
(PHASE_RUNOUT). STATE_ROUND_END is the round summary popup, which the host
closes early or which times out after ``ROUND_END_SECONDS``.

Poker-only state (stacks, seats, the button) lives on the Room rather than on
the shared Player, so the core Player model is untouched by this game.
"""
import random
import time
from typing import Dict, List, Optional

from game.core.cards import shuffled_deck
from game.core.player import Player
from game.core.states import (
    STATE_LOBBY,
    STATE_IN_TURN,
    STATE_ROUND_END,
    STATE_GAME_END,
)
from game.poker import pots as potlib
from game.poker.evaluator import evaluate, poker_rank, _PLURAL, _SINGULAR, STRAIGHT_FLUSH
from game.poker.settings import (
    MAX_PLAYERS,
    HOLE_CARDS,
    BLIND_DIVISOR,
    ROUND_END_SECONDS,
    RUNOUT_STEP_SECONDS,
)

PREFLOP = "preflop"
FLOP = "flop"
TURN = "turn"
RIVER = "river"
_NEXT_STREET = {PREFLOP: FLOP, FLOP: TURN, TURN: RIVER}

PHASE_BETTING = "betting"
PHASE_RUNOUT = "runout"

ACTIONS = ("fold", "check", "call", "bet", "raise", "allin")


class Room:
    game_type = "poker"

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

        # ---- game-long state ----
        # Seating is fixed for the game (clockwise = list order) and never
        # shrinks: a player who busts or leaves keeps their place in the list
        # and is skipped, so "clockwise from the button" is always well defined
        # even when the button's own seat has emptied.
        self.seats: List[str] = []
        self.chips: Dict[str, int] = {}
        # Coins each player was given — starting coins, or the stack a late
        # joiner was admitted with. Net result = chips - received.
        self.received: Dict[str, int] = {}
        # One entry per bust, in order: who, in which round, and with how much
        # they started that round (the tiebreak for two busts in one round).
        self.bust_log: List[dict] = []
        self.button: Optional[str] = None
        self.sitting_out = set()
        self.game_over = False
        self.winner: Optional[str] = None
        self.last_result: Optional[dict] = None
        self.round_end_at = 0.0

        self._reset_round_state()

    def _reset_round_state(self) -> None:
        self.deck: List = []
        self.burns: List = []
        self.board: List = []
        self.hole: Dict[str, List] = {}
        self.in_hand: List[str] = []          # dealt into this round, seat order
        self.start_chips: Dict[str, int] = {}
        self.folded = set()
        self.bets: Dict[str, int] = {}
        self.contributed: Dict[str, int] = {}
        self.street: Optional[str] = None
        self.phase: Optional[str] = None
        self.current_bet = 0
        self.min_raise = 0
        # uid -> the street's bet level right after their last voluntary action.
        # Present = has acted this street; the value decides whether a later
        # short all-in re-opened the betting to them (see legal_actions).
        self.acted_at: Dict[str, int] = {}
        self.current: Optional[str] = None
        self.sb_id: Optional[str] = None
        self.bb_id: Optional[str] = None
        # Players whose hole cards are face up for everyone (runout / showdown).
        self.shown = set()
        self.turn_start_ts = 0.0
        self.runout_next_at = 0.0
        self.last_action: Optional[dict] = None

    # ---- registration / attachment (same contract as every variant) ----
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

    def migrate_host(self) -> Optional[str]:
        host = self.players.get(self.host_id)
        if host is not None and host.connected and not host.is_bot:
            return self.host_id
        for player in self.players.values():
            if player.connected and not player.is_bot:
                self.host_id = player.user_id
                return self.host_id
        return None

    # ---- blinds ----
    def blinds(self):
        """(small, big) for the current round — see "Blinds" in the rules."""
        big = max(2, int(self.settings.get("starting_chips", 1_000_000)) // BLIND_DIVISOR)
        every = int(self.settings.get("blind_up_every", 0) or 0)
        if every > 0 and self.round_number > 0:
            big *= 2 ** ((self.round_number - 1) // every)
        return big // 2, big

    # ---- seat queries ----
    def _seated(self, uid: str) -> bool:
        """At the table for this game: present, not busted, not watching."""
        p = self.players.get(uid)
        return p is not None and not p.eliminated and not p.is_spectator

    def players_with_chips(self) -> List[str]:
        return [u for u in self.seats if self._seated(u) and self.chips.get(u, 0) > 0]

    def _clockwise_after(self, uid: Optional[str], pool) -> List[str]:
        """Members of ``pool`` in seat order, starting with the seat after ``uid``.

        ``uid`` itself comes last if it is in the pool.
        """
        if not self.seats:
            return []
        i = self.seats.index(uid) if uid in self.seats else -1
        order = self.seats[i + 1:] + self.seats[:i + 1]
        return [u for u in order if u in pool]

    def live(self) -> List[str]:
        """Still in this round: dealt in and not folded."""
        return [u for u in self.in_hand if u not in self.folded]

    def live_not_allin(self) -> List[str]:
        """Live players who still have coins behind, i.e. can still bet."""
        return [u for u in self.live() if self.chips.get(u, 0) > 0]

    def is_all_in(self, uid: str) -> bool:
        return uid in self.in_hand and uid not in self.folded and self.chips.get(uid, 0) == 0

    def current_turn_id(self) -> Optional[str]:
        return self.current if self.phase == PHASE_BETTING else None

    # ---- round lifecycle ----
    def start_round(self) -> None:
        if self.round_number == 0:
            self._start_game()
        else:
            self._admit_pending()

        eligible = self.players_with_chips()
        if len(eligible) < 2:
            self._end_game()
            return

        self._reset_round_state()
        self.round_number += 1
        small, big = self.blinds()

        pool = set(eligible)
        if self.button is None or self.button not in self.seats:
            self.button = self._pick_first_button(eligible)
        else:
            self.button = self._clockwise_after(self.button, pool)[0]
        after_button = self._clockwise_after(self.button, pool)
        if len(eligible) == 2:
            # Heads-up: the button is the small blind and acts first pre-flop.
            self.sb_id, self.bb_id = self.button, after_button[0]
        else:
            self.sb_id, self.bb_id = after_button[0], after_button[1]

        self.in_hand = [u for u in self.seats if u in pool]
        self.start_chips = {u: self.chips[u] for u in self.in_hand}
        self.bets = {u: 0 for u in self.in_hand}
        self.contributed = {u: 0 for u in self.in_hand}

        self.deck = shuffled_deck(1)
        for _ in range(HOLE_CARDS):
            for uid in after_button:
                self.hole.setdefault(uid, []).append(self.deck.pop())

        self._put(self.sb_id, small)
        self._put(self.bb_id, big)
        # The full big blind is the bet to match even if the big blind is short.
        self.current_bet = big
        self.min_raise = big
        self.street = PREFLOP
        self.phase = PHASE_BETTING
        self.state = STATE_IN_TURN
        self.turn_start_ts = time.time()

        if self._stage_done():
            self._end_stage()
        else:
            self.current = self._next_to_act(self.bb_id)
            if self.current is None:
                self._end_stage()

    def _pick_first_button(self, eligible: List[str]) -> str:
        """Round 1's dealer: a random player. A method so tests can pin it."""
        return random.choice(eligible)

    def _start_game(self) -> None:
        start = int(self.settings.get("starting_chips", 1_000_000))
        self.seats = []
        for uid, p in self.players.items():
            p.eliminated = False
            p.timeout_count = 0
            p.pending_join = False
            # Anyone not at the table when the deal starts watches instead; the
            # host can admit them from the next round like any late joiner.
            p.is_spectator = not p.connected
            if not p.is_spectator:
                self.seats.append(uid)
        self.chips = {u: start for u in self.seats}
        self.received = dict(self.chips)
        self.bust_log = []
        self.button = None
        self.sitting_out = set()
        self.game_over = False
        self.winner = None
        self.last_result = None

    def _admit_pending(self) -> None:
        """Seat spectators the host admitted, with the table's average stack.

        The admit dialog's penalty % shaves the stack, never below one big blind.
        """
        pending = [u for u, p in self.players.items() if p.pending_join and p.is_spectator]
        if not pending:
            return
        _, big = self.blinds()
        stacks = [self.chips[u] for u in self.players_with_chips()]
        average = (sum(stacks) // len(stacks)) if stacks else int(self.settings.get("starting_chips", 0))
        for uid in pending:
            p = self.players[uid]
            pct = max(0, min(100, int(p.join_penalty_pct or 0)))
            amount = average * (100 - pct) // 100
            amount = max(big, (amount // big) * big)
            self.chips[uid] = amount
            self.received[uid] = amount
            p.is_spectator = False
            p.pending_join = False
            p.eliminated = False
            p.timeout_count = 0
            if uid not in self.seats:
                self.seats.append(uid)

    # ---- betting ----
    def _put(self, uid: str, amount: int) -> int:
        """Move up to ``amount`` from a stack into the pot. Returns what moved."""
        amount = max(0, min(int(amount), self.chips.get(uid, 0)))
        self.chips[uid] -= amount
        self.bets[uid] = self.bets.get(uid, 0) + amount
        self.contributed[uid] = self.contributed.get(uid, 0) + amount
        return amount

    def _needs_action(self, uid: str) -> bool:
        return uid not in self.acted_at or self.bets.get(uid, 0) < self.current_bet

    def _next_to_act(self, after: str) -> Optional[str]:
        able = set(self.live_not_allin())
        for uid in self._clockwise_after(after, able):
            if self._needs_action(uid):
                return uid
        return None

    def _stage_done(self) -> bool:
        if len(self.live()) <= 1:
            return True
        actors = self.live_not_allin()
        if not actors:
            return True
        if len(actors) == 1:
            # Nobody left who could answer a bet: the one player with coins only
            # has to match what is already there — they never get to bet alone.
            uid = actors[0]
            top_other = max((self.bets.get(o, 0) for o in self.live() if o != uid), default=0)
            return self.bets.get(uid, 0) >= top_other
        return all(not self._needs_action(u) for u in actors)

    def legal_actions(self, uid: Optional[str]) -> Optional[dict]:
        """What ``uid`` may do right now, or None if it is not their decision."""
        if (self.state != STATE_IN_TURN or self.phase != PHASE_BETTING
                or uid is None or uid != self.current):
            return None
        stack = self.chips.get(uid, 0)
        bet = self.bets.get(uid, 0)
        to_call = max(0, self.current_bet - bet)
        others_can_act = any(o != uid for o in self.live_not_allin())
        # A short all-in does not re-open the betting to someone who has already
        # acted, unless the bet has since risen by at least one full raise.
        reopened = (uid not in self.acted_at
                    or self.current_bet - self.acted_at[uid] >= self.min_raise)
        can_raise = stack > to_call and others_can_act and reopened
        max_to = bet + stack
        min_to = min(self.current_bet + self.min_raise, max_to)
        return {
            "fold": True,
            "check": to_call == 0,
            "to_call": to_call,
            "call": min(to_call, stack),
            "raise": can_raise,
            "min_to": min_to,
            "max_to": max_to,
            "verb": "bet" if self.current_bet == 0 else "raise",
            "stack": stack,
            "bet": bet,
        }

    def act(self, uid: str, action: str, amount=None, auto: bool = False) -> dict:
        """Apply one decision. Raises ValueError with a player-facing message.

        ``amount`` is the *total* street bet a bet/raise goes to ("raise to").
        ``auto`` marks a move the game made for a player (timeout / sat out);
        anything else is a real decision and brings a sat-out player back.
        """
        legal = self.legal_actions(uid)
        if legal is None:
            raise ValueError("It's not your turn.")
        if action not in ACTIONS:
            raise ValueError("Unknown action.")

        if action == "allin":
            if legal["raise"]:
                action, amount = "raise", legal["max_to"]
            elif legal["to_call"] > 0:
                action = "call"
            else:
                raise ValueError("You can't raise right now.")

        if action == "fold":
            self.folded.add(uid)
            done = {"action": "fold"}
        elif action == "check":
            if not legal["check"]:
                raise ValueError("You have to call, raise or fold.")
            self.acted_at[uid] = self.current_bet
            done = {"action": "check"}
        elif action == "call":
            if legal["to_call"] == 0:
                raise ValueError("There's nothing to call — check instead.")
            paid = self._put(uid, legal["call"])
            self.acted_at[uid] = self.current_bet
            done = {"action": "call", "amount": paid, "all_in": self.chips[uid] == 0}
        else:  # bet / raise
            if not legal["raise"]:
                raise ValueError("You can't raise right now.")
            try:
                target = int(amount)
            except (TypeError, ValueError):
                raise ValueError("Choose how much to bet.")
            if target > legal["max_to"]:
                raise ValueError("You don't have that many coins.")
            if target < legal["min_to"]:
                raise ValueError("The minimum is %d." % legal["min_to"])
            self._put(uid, target - legal["bet"])
            if target - self.current_bet >= self.min_raise:
                self.min_raise = target - self.current_bet     # a full raise
            verb = legal["verb"]
            self.current_bet = target
            self.acted_at[uid] = target
            done = {"action": verb, "to": target, "all_in": self.chips[uid] == 0}

        player = self.players.get(uid)
        if not auto and player is not None:
            player.timeout_count = 0
            self.sitting_out.discard(uid)

        done["user_id"] = uid
        done["street"] = self.street
        self.last_action = done
        self._after_action(uid)
        return done

    def _after_action(self, uid: str) -> None:
        if len(self.live()) == 1:
            self._award_fold_win()
            return
        if self._stage_done():
            self._end_stage()
            return
        nxt = self._next_to_act(uid)
        if nxt is None:
            self._end_stage()
            return
        self.current = nxt
        self.turn_start_ts = time.time()

    def _return_uncalled(self) -> None:
        uid, excess = potlib.uncalled_excess({u: self.bets.get(u, 0) for u in self.in_hand})
        # Only a live bettor gets money back. Someone who folded — or quit — while
        # holding the top bet forfeits it like everything else they put in.
        if uid is None or excess <= 0 or uid in self.folded:
            return
        self.bets[uid] -= excess
        self.contributed[uid] -= excess
        if uid in self.chips:
            self.chips[uid] += excess

    def _end_stage(self) -> None:
        self._return_uncalled()
        self.current = None
        if len(self.live()) <= 1:
            self._award_fold_win()
            return
        if self.street == RIVER:
            self._showdown()
            return
        if len(self.live_not_allin()) <= 1:
            # Nobody can bet any more: hands go face up and the board is dealt
            # out one street at a time (the director calls step_runout).
            self.phase = PHASE_RUNOUT
            self.shown = set(self.live())
            self.runout_next_at = time.time() + RUNOUT_STEP_SECONDS
            return
        self._deal_street()
        self.bets = {u: 0 for u in self.in_hand}
        self.current_bet = 0
        self.min_raise = self.blinds()[1]
        self.acted_at = {}
        self.current = self._next_to_act(self.button)
        self.turn_start_ts = time.time()
        if self.current is None:
            self._end_stage()

    def _deal_street(self) -> None:
        """Burn one, then deal the next street onto the board."""
        self.burns.append(self.deck.pop())
        count = 3 if self.street == PREFLOP else 1
        for _ in range(count):
            self.board.append(self.deck.pop())
        self.street = _NEXT_STREET[self.street]

    def step_runout(self) -> bool:
        """Deal the next street of an all-in runout. True if anything happened."""
        if self.state != STATE_IN_TURN or self.phase != PHASE_RUNOUT:
            return False
        if self.street in _NEXT_STREET:
            self._deal_street()
        if self.street == RIVER:
            self._showdown()
        else:
            self.runout_next_at = time.time() + RUNOUT_STEP_SECONDS
        return True

    def runout_due(self) -> bool:
        return (self.state == STATE_IN_TURN and self.phase == PHASE_RUNOUT
                and time.time() >= self.runout_next_at)

    # ---- paying out ----
    def _payout_order(self) -> List[str]:
        """Seat order starting left of the button — who gets an odd coin first."""
        return self._clockwise_after(self.button, set(self.in_hand))

    def _showdown(self) -> None:
        live = self.live()
        self.shown = set(live)
        hands = {u: evaluate(self.hole[u] + self.board) for u in live}
        awards = []
        for pot in potlib.build_pots(self.contributed, self.folded):
            contenders = [u for u in pot["eligible"] if u in hands] or list(hands)
            best = max(hands[u].value for u in contenders)
            winners = [u for u in contenders if hands[u].value == best]
            payout = potlib.split(pot["amount"], winners, self._payout_order())
            for uid, amount in payout.items():
                if uid in self.chips:
                    self.chips[uid] += amount
            awards.append({
                "amount": pot["amount"],
                "winners": winners,
                "hand_name": hands[winners[0]].name,
                "payouts": payout,
            })
        self._finish_round(awards, hands, fold_win=False)

    def _award_fold_win(self) -> None:
        self._return_uncalled()
        live = self.live()
        total = sum(self.contributed.values())
        awards = []
        if live:
            winner = live[0]
            if winner in self.chips:
                self.chips[winner] += total
            awards.append({"amount": total, "winners": [winner], "hand_name": None,
                           "payouts": {winner: total}})
        # An uncontested winner's cards stay hidden.
        self.shown = set()
        self._finish_round(awards, {}, fold_win=True)

    def _finish_round(self, awards: List[dict], hands: dict, fold_win: bool) -> None:
        self.current = None
        self.phase = None
        for uid in self.in_hand:
            p = self.players.get(uid)
            if p is not None and not p.eliminated and self.chips.get(uid, 0) <= 0:
                p.eliminated = True
                self.sitting_out.discard(uid)
                self.bust_log.append({
                    "user_id": uid,
                    "round": self.round_number,
                    "start_chips": self.start_chips.get(uid, 0),
                })

        self.last_result = {
            "round_number": self.round_number,
            "fold_win": fold_win,
            "board": [c.to_dict() for c in self.board],
            "awards": awards,
            "hands": {
                uid: {
                    "cards": [c.to_dict() for c in self.hole[uid]],
                    "name": hand.name,
                    "best": [c.id for c in hand.cards],
                }
                for uid, hand in hands.items()
            },
            "deltas": {
                uid: self.chips.get(uid, 0) - self.start_chips.get(uid, 0)
                for uid in self.in_hand if uid in self.players
            },
            "busted": [b["user_id"] for b in self.bust_log if b["round"] == self.round_number],
        }

        rounds = int(self.settings.get("rounds", 10))
        if self.round_number >= rounds or len(self.players_with_chips()) <= 1:
            self._end_game()
        else:
            self.state = STATE_ROUND_END
            self.round_end_at = time.time() + ROUND_END_SECONDS

    def _end_game(self) -> None:
        self.current = None
        self.phase = None
        self.game_over = True
        self.state = STATE_GAME_END
        ranked = self.standings()
        self.winner = ranked[0]["user_id"] if ranked else None

    # ---- between rounds ----
    def round_end_seconds_left(self) -> Optional[int]:
        if self.state != STATE_ROUND_END:
            return None
        return max(0, int(round(self.round_end_at - time.time())))

    def next_round_due(self) -> bool:
        return self.state == STATE_ROUND_END and time.time() >= self.round_end_at

    # ---- timers, timeouts, sitting out ----
    def turn_seconds_left(self) -> Optional[int]:
        if self.current_turn_id() is None or self.state != STATE_IN_TURN:
            return None
        deadline = self.turn_start_ts + int(self.settings.get("turn_timer", 30))
        return max(0, int(round(deadline - time.time())))

    def is_timed_out(self) -> bool:
        if self.current_turn_id() is None or self.state != STATE_IN_TURN:
            return False
        return time.time() >= self.turn_start_ts + int(self.settings.get("turn_timer", 30))

    def _auto_move(self, uid: str) -> str:
        legal = self.legal_actions(uid)
        return "check" if legal and legal["check"] else "fold"

    def force_timeout(self, uid: str) -> dict:
        """The turn clock ran out: check if free, otherwise fold."""
        player = self.players[uid]
        player.timeout_count += 1
        action = self._auto_move(uid)
        self.act(uid, action, auto=True)
        sat_out = player.timeout_count >= int(self.settings.get("timeout_limit", 3))
        if sat_out:
            self.sitting_out.add(uid)
        return {"action": action, "timeout_count": player.timeout_count, "sat_out": sat_out}

    def auto_act(self, uid: str) -> str:
        """Instant check-or-fold for a player who is sat out."""
        action = self._auto_move(uid)
        self.act(uid, action, auto=True)
        return action

    def come_back(self, uid: str) -> bool:
        if uid not in self.sitting_out:
            return False
        self.sitting_out.discard(uid)
        if uid in self.players:
            self.players[uid].timeout_count = 0
        return True

    # ---- leaving ----
    def remove_participant(self, user_id: str) -> None:
        """Voluntary quit: fold any live hand, forfeit the rest of the stack."""
        if user_id not in self.players:
            return
        was_host = self.is_host(user_id)

        if self.state == STATE_IN_TURN and user_id in self.live():
            was_current = self.current == user_id
            self.folded.add(user_id)
            self.shown.discard(user_id)
            if len(self.live()) <= 1:
                self._award_fold_win()
            elif self.phase == PHASE_BETTING:
                if self._stage_done():
                    self._end_stage()
                elif was_current:
                    nxt = self._next_to_act(user_id)
                    if nxt is None:
                        self._end_stage()
                    else:
                        self.current = nxt
                        self.turn_start_ts = time.time()

        self.players.pop(user_id, None)
        self.chips.pop(user_id, None)
        self.sitting_out.discard(user_id)
        if was_host:
            self.migrate_host()

        # Between rounds a quit can leave one player holding every coin. Mid-round
        # it cannot end the game early: a live all-in player has no coins behind
        # yet may still win the pot, so the round settles first and
        # _finish_round makes the call.
        if self.state == STATE_ROUND_END and len(self.players_with_chips()) <= 1:
            self._end_game()

    # ---- ranking ----
    def standings(self) -> List[dict]:
        """Final table, best first. Equal results share a place.

        Players still holding coins rank by coins; busted players rank below
        them, the later bust first, then the bigger stack at the start of the
        round they busted in. Players who left are not ranked.
        """
        keyed = []
        for uid in self.seats:
            p = self.players.get(uid)
            if p is None or p.is_spectator or p.eliminated:
                continue
            keyed.append((uid, (0, -self.chips.get(uid, 0), 0)))
        for b in self.bust_log:
            if b["user_id"] in self.players:
                keyed.append((b["user_id"], (1, -b["round"], -b["start_chips"])))
        keyed.sort(key=lambda kv: kv[1])

        rows = []
        prev_key, place = None, 0
        for index, (uid, key) in enumerate(keyed):
            if key != prev_key:
                place = index + 1
                prev_key = key
            p = self.players[uid]
            chips = self.chips.get(uid, 0)
            rows.append({
                "user_id": uid,
                "name": p.name,
                "chips": chips,
                "net": chips - self.received.get(uid, 0),
                "place": place,
                "eliminated": p.eliminated,
                "total_score": chips,
            })
        return rows

    # ---- views ----
    def public_players(self) -> List[dict]:
        rows = []
        for uid, p in self.players.items():
            in_hand = uid in self.in_hand
            chips = self.chips.get(uid)
            rows.append({
                "user_id": uid,
                "name": p.name,
                # What they were given (starting coins or admit stack): the seat's
                # coin gauge reads the current stack against it.
                "received": self.received.get(uid),
                "connected": p.connected,
                "color": p.color_index,
                "is_bot": p.is_bot,
                "is_spectator": p.is_spectator,
                "pending_join": p.pending_join,
                "eliminated": p.eliminated,
                "chips": chips,
                "score": chips if chips is not None else 0,
                "net": self._running_net(uid),
                "bet": self.bets.get(uid, 0),
                "in_hand": in_hand,
                "folded": uid in self.folded,
                "all_in": self.is_all_in(uid),
                "sitting_out": uid in self.sitting_out,
                "card_count": HOLE_CARDS if in_hand and uid not in self.folded else 0,
            })
        return rows

    def _running_net(self, uid: str) -> int:
        """Won or lost so far this game. Mid-round, coins in the pot are at stake,
        not lost, so they still count as the player's until the round settles."""
        if uid not in self.received or uid not in self.chips:
            return 0
        at_stake = self.contributed.get(uid, 0) if self.state == STATE_IN_TURN else 0
        return self.chips[uid] + at_stake - self.received[uid]

    def shown_hands(self) -> Dict[str, List[dict]]:
        """Hole cards currently face up for the whole table."""
        return {u: [c.to_dict() for c in self.hole.get(u, [])] for u in self.shown}

    def public_round_state(self) -> dict:
        small, big = self.blinds()
        collected = {u: self.contributed.get(u, 0) - self.bets.get(u, 0) for u in self.in_hand}
        return {
            "game_type": self.game_type,
            "state": self.state,
            "phase": self.phase,
            "street": self.street,
            "round_number": self.round_number,
            "rounds_total": int(self.settings.get("rounds", 10)),
            "host_id": self.host_id,
            "settings": self.settings,
            "table_theme": self.table_theme,
            "seats": [u for u in self.seats if u in self.players],
            "turn_order": list(self.in_hand),
            "button": self.button,
            "sb_id": self.sb_id,
            "bb_id": self.bb_id,
            "blinds": {"sb": small, "bb": big},
            "board": [c.to_dict() for c in self.board],
            "pot_total": sum(self.contributed.values()),
            # Pots already gathered into the middle; this street's bets are
            # shown in front of each seat (players[].bet) until the street ends.
            "pots": potlib.build_pots(collected, self.folded),
            "current_turn": self.current_turn_id(),
            "current_bet": self.current_bet,
            "actions": self.legal_actions(self.current_turn_id()),
            "revealed": self.shown_hands(),
            "last_action": self.last_action,
            "turn_seconds_left": self.turn_seconds_left(),
            "players": self.public_players(),
        }

    def hand_for(self, user_id: str) -> List[dict]:
        return [c.to_dict() for c in self.hole.get(user_id, [])]

    def hand_label(self, user_id: str) -> Optional[str]:
        """The player's own best hand so far, for their eyes only.

        From the flop on it is the evaluator's name for their best five cards
        ("Two Pair, Kings and Sevens"); before the flop it is "Pair of Fours" or
        "High Card, Ace". Built from the player's own cards and the public board,
        so it reveals nothing they could not work out themselves.
        """
        hole = self.hole.get(user_id) or []
        if len(hole) < 2:
            return None
        if len(self.board) >= 3:
            return evaluate(hole + self.board).name
        if hole[0].rank == hole[1].rank:
            return "Pair of " + _PLURAL[poker_rank(hole[0])]
        # Two unpaired cards are, honestly, a high card — and naming it means a
        # player with hints on always sees something, instead of reading the
        # pre-flop silence as hints being broken.
        return "High Card, " + _SINGULAR[max(poker_rank(c) for c in hole)]

    def hand_rank_row(self, user_id: str) -> Optional[int]:
        """Which row of the rankings card (0 = Royal Flush ... 9 = High Card) the
        player's hand sits on, or None when there is nothing to place yet.

        Before the flop a pocket pair is One Pair and anything else High Card.
        """
        hole = self.hole.get(user_id) or []
        if len(hole) < 2:
            return None
        if len(self.board) >= 3:
            value = evaluate(hole + self.board).value
            if value == (STRAIGHT_FLUSH, 14):
                return 0                                  # Royal Flush has its own row
            return 9 - value[0]                           # 8 (straight flush) -> 1 ... 0 -> 9
        return 8 if hole[0].rank == hole[1].rank else 9

    def hints_on(self) -> bool:
        return bool(int(self.settings.get("hand_hints", 0) or 0))

    def private_view(self, user_id: str) -> dict:
        """Everything one player privately holds: their cards and, if the host
        turned hand hints on, what they make.

        ``round_number`` lets a client tell this round's hand from a late copy of
        the last one, so a new round never shows the previous round's cards.
        With hints off the hand's name and row are not sent at all — off means
        off, not merely hidden by the client.
        """
        hints = self.hints_on()
        return {
            "cards": self.hand_for(user_id),
            "round_number": self.round_number,
            "hand_name": self.hand_label(user_id) if hints else None,
            "hand_rank": self.hand_rank_row(user_id) if hints else None,
        }

    def round_end_payload(self) -> dict:
        rows = []
        result = self.last_result or {}
        deltas = result.get("deltas", {})
        for uid in self.seats:
            p = self.players.get(uid)
            if p is None or p.is_spectator:
                continue
            rows.append({
                "user_id": uid,
                "name": p.name,
                "chips": self.chips.get(uid, 0),
                "delta": deltas.get(uid, 0),
                "eliminated": p.eliminated,
                "folded": uid in self.folded,
            })
        rows.sort(key=lambda r: (r["eliminated"], -r["chips"]))
        return {
            "round_number": self.round_number,
            "rounds_total": int(self.settings.get("rounds", 10)),
            "result": result,
            "rows": rows,
            "seconds_left": self.round_end_seconds_left(),
            "host_id": self.host_id,
            "players": self.public_players(),
            "game_over": False,
        }

    def game_end_payload(self) -> dict:
        return {
            "winner": self.winner,
            "winner_name": self.players[self.winner].name if self.winner in self.players else None,
            "standings": self.standings(),
            "last_round": self.last_result,
            "rounds_played": self.round_number,
            "players": self.public_players(),
            "host_id": self.host_id,
        }

    def reset_for_rematch(self) -> None:
        original = self.players.get(self.original_host_id)
        if original is not None and original.connected:
            self.host_id = self.original_host_id
        for p in self.players.values():
            p.eliminated = False
            p.timeout_count = 0
            p.is_spectator = False
            p.pending_join = False
        self.state = STATE_LOBBY
        self.round_number = 0
        self.seats = []
        self.chips = {}
        self.received = {}
        self.bust_log = []
        self.button = None
        self.sitting_out = set()
        self.game_over = False
        self.winner = None
        self.last_result = None
        self.round_end_at = 0.0
        self._reset_round_state()
