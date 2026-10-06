"""Poker gameplay: socket handlers + turn-timer / runout / bot / round-end ticker.

All authority lives in game/poker/room.py. A client sends one ``poker_action``
(fold / check / call / bet / raise / allin, with a raise-to amount); the server
decides whether it is legal and what follows. After every change the room gets a
public ``poker_state`` (board, stacks, bets, pots — never a hidden card) and each
player privately gets ``your_hand`` with their own two cards.

Event vocabulary (all prefixed, so nothing collides with another game):
  round_start      public state at a fresh deal (shared lobby uses this name)
  poker_state      public state after any change
  poker_acted      one decision, for the action log / toasts
  poker_round_end  the round summary popup (coins left, 30s auto-start)
  game_end         the medal podium

Every emit goes through ``_sio.emit`` — the socketio server, which
sockets/audience.py has wrapped — rather than flask's contextual emit, because
the same broadcasts are made from handlers and from the director's background
ticker, where there is no request context.
"""
import time

from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.poker import ai
from game.poker.room import PHASE_RUNOUT, ACTIONS
from game.poker.visibility import public_card_ids
from sockets import audience, director, presenter
from sockets.common import error

audience.register("poker", public_card_ids)

GAME = "poker"

# Set by register(); see the module docstring for why emits do not use flask's.
_sio = None


def _send(event, payload, to):
    _sio.emit(event, payload, to=to)


# ---- private + public broadcasts -----------------------------------------
def _deal_private(room, user_id=None):
    """Each human dealt into the round receives their own two cards only."""
    targets = [room.players.get(user_id)] if user_id else list(room.players.values())
    for p in targets:
        if not p or p.is_bot or not p.sid or not p.connected:
            continue
        if p.user_id not in room.hole:
            continue          # not dealt in (spectator / busted): nothing private
        _send("your_hand", room.private_view(p.user_id), p.sid)


def _broadcast(room):
    """Public state, each player's private view, then any overlay.

    The private hand rides along with every broadcast rather than only with the
    deal. It is a couple of cards per player, and it means a deal message that
    was lost, or that arrived before the round it belongs to, is repaired by the
    very next update instead of leaving a player looking at an empty hand. It
    also keeps each player's own hand label current as the board grows.
    """
    _send("poker_state", room.public_round_state(), room.code)
    if room.state in (STATE_IN_TURN, STATE_ROUND_END):
        _deal_private(room)
    if room.state == STATE_ROUND_END:
        _send("poker_round_end", room.round_end_payload(), room.code)
    elif room.state == STATE_GAME_END:
        _send("game_end", room.game_end_payload(), room.code)


def _start_next_round(room):
    room.start_round()
    if room.state == STATE_GAME_END:
        _send("game_end", room.game_end_payload(), room.code)
        return
    _send("round_start", room.public_round_state(), room.code)
    _deal_private(room)


def _announce(room, done, auto=False, reason=None):
    payload = dict(done)
    payload["auto"] = auto
    if reason:
        payload["reason"] = reason
    _send("poker_acted", payload, room.code)


def _refresh_public(room):
    """After a structural change (a quit): everyone re-syncs."""
    _broadcast(room)


def _resync_one(room, user_id):
    """Everything one player needs to repaint from scratch, at any state."""
    player = room.players.get(user_id)
    if not player or not player.sid:
        return
    if room.state == STATE_IN_TURN:
        _send("round_start", room.public_round_state(), player.sid)
        _deal_private(room, user_id)
    elif room.state == STATE_ROUND_END:
        _send("poker_state", room.public_round_state(), player.sid)
        _deal_private(room, user_id)
        _send("poker_round_end", room.round_end_payload(), player.sid)
    elif room.state == STATE_GAME_END:
        _send("poker_state", room.public_round_state(), player.sid)
        _send("game_end", room.game_end_payload(), player.sid)


presenter.register(GAME, _deal_private)
presenter.register_refresh(GAME, _refresh_public)
presenter.register_resync(GAME, _resync_one)


def register(socketio, manager):
    global _sio
    _sio = socketio

    def _room_for(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        room = manager.get_room(code)
        if room is None:
            error("This room no longer exists.")
            return None, None
        if room.game_type != GAME:
            return None, None    # another variant's room: not our event
        return room, data.get("user_id")

    @socketio.on("poker_action")
    def on_action(data):
        room, user_id = _room_for(data)
        if room is None:
            return
        if room.state != STATE_IN_TURN:
            return error("The round is not in play.")
        action = (data or {}).get("action")
        if action not in ACTIONS:
            return error("Unknown action.")
        try:
            done = room.act(user_id, action, (data or {}).get("amount"))
        except ValueError as exc:
            return error(str(exc))
        _announce(room, done)
        _broadcast(room)

    @socketio.on("poker_back")
    def on_back(data):
        """A sat-out player says "I'm back"."""
        room, user_id = _room_for(data)
        if room is None:
            return
        if room.come_back(user_id):
            _send("poker_state", room.public_round_state(), room.code)

    @socketio.on("poker_next_round")
    def on_next_round(data):
        room, user_id = _room_for(data)
        if room is None:
            return
        if not room.is_host(user_id):
            return error("Only the host can start the next round.")
        if room.state != STATE_ROUND_END:
            return error("There's no round to start.")
        _start_next_round(room)


# ---- director ticker ---------------------------------------------------------
# (room_code, bot_id) -> earliest time that bot may act. Keyed per bot so two
# bots in one rotation never share a deadline (see super_seven.py).
_bot_act_at: dict = {}


def _tick_room(socketio, room):
    code = room.code

    if room.state == STATE_ROUND_END:
        # Nobody watching: do not keep dealing rounds to an empty room.
        if room.next_round_due() and director.bots_should_act(room):
            _start_next_round(room)
        return

    if room.phase == PHASE_RUNOUT:
        if room.runout_due():
            room.step_runout()
            _broadcast(room)
        return

    cur = room.current_turn_id()
    player = room.players.get(cur) if cur else None
    if player is None:
        return

    if player.is_bot:
        if director.bots_should_act(room):
            _tick_bot(room, cur)
        return

    # Turn is with a human: no bot may carry a stale deadline into its next turn.
    for stale in [k for k in _bot_act_at if k[0] == code]:
        _bot_act_at.pop(stale, None)

    if cur in room.sitting_out:
        action = room.auto_act(cur)
        _announce(room, {"user_id": cur, "action": action}, auto=True, reason="sitting_out")
        _broadcast(room)
        return

    if not room.is_timed_out():
        return
    info = room.force_timeout(cur)
    _announce(room, {"user_id": cur, "action": info["action"]}, auto=True, reason="timeout")
    _send("player_timed_out", {
        "user_id": cur,
        "name": player.name,
        "timeout_count": info["timeout_count"],
        "sat_out": info["sat_out"],
    }, code)
    _broadcast(room)


def _tick_bot(room, bot_id):
    key = (room.code, bot_id)
    now = time.time()
    if key not in _bot_act_at:
        _bot_act_at[key] = now + ai.bot_delay()
        return
    if now < _bot_act_at[key]:
        return
    del _bot_act_at[key]

    move = ai.decide_move(room, bot_id)
    if move is None:
        return
    try:
        done = room.act(bot_id, move["action"], move["amount"])
    except ValueError:
        # Never let a bad suggestion stall the table: fall back to check/fold.
        done = {"user_id": bot_id, "action": room.auto_act(bot_id)}
    _announce(room, done)
    _broadcast(room)


director.register_ticker(GAME, _tick_room, states=(STATE_IN_TURN, STATE_ROUND_END))
