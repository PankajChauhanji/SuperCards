"""Super 4 gameplay: socket handlers + turn-timer / bot ticker.

All authority lives in the Room; the client only sends slot/target selections.
Hidden information is strict: after every action the server broadcasts the public
`s4_state` (no faces) plus each connected player's private `your_view` (only the
cards they know), and peeks are sent to the acting socket alone. Handlers guard on
room.game_type == "super_four".
"""
import time

from flask import request
from flask_socketio import emit as _femit

from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.super_four import ai
from game.super_four.room import PHASE_DRAW, PHASE_DECIDE, PHASE_POWER, PHASE_MATCH, PHASE_PREVIEW
from sockets import director, presenter
from sockets.common import error

GAME = "super_four"


# ---- state broadcast (public + per-player private) ----
def _emit_state(socketio, room):
    socketio.emit("s4_state", room.public_round_state(), to=room.code)
    for p in room.connected_players():
        if p.is_bot or not p.sid:
            continue
        socketio.emit("your_view", room.private_view(p.user_id), to=p.sid)
    if room.state in (STATE_ROUND_END, STATE_GAME_END):
        socketio.emit("s4_round_end", room.round_end_payload(), to=room.code)


def _deal_private(room, user_id=None):
    """Presenter hook: private deal on start/reconnect (only cards you know)."""
    targets = [room.players.get(user_id)] if user_id else room.connected_players()
    for p in targets:
        if not p or p.is_bot or not p.sid:
            continue
        _femit("your_view", room.private_view(p.user_id), to=p.sid)


def _int(d, key, default=-1):
    try:
        return int(d.get(key, default))
    except (TypeError, ValueError):
        return default


def register(socketio, manager):

    def _room_uid(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        uid = data.get("user_id")
        room = manager.get_room(code)
        if room is None or room.game_type != GAME:
            return None, None
        return room, uid

    @socketio.on("s4_draw")
    def on_draw(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.draw(uid) is None:
            return error("You can't draw right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_begin_play")
    def on_begin_play(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if not room.is_host(uid):
            return error("Only the host can end the preview.")
        if not room.begin_play():
            return error("The preview is not active.")
        _emit_state(socketio, room)

    @socketio.on("s4_keep")
    def on_keep(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if not room.keep(uid, _int(data, "slot")):
            return error("You can't keep into that slot.")
        player = room.players.get(uid)
        if player:
            socketio.emit("toast", {"message": f"{player.name} kept a card"}, to=room.code)
        _emit_state(socketio, room)

    @socketio.on("s4_discard")
    def on_discard(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.discard(uid) is None:
            return error("You can't discard right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_own")
    def on_match_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.match_own(uid, _int(data, "slot")) is None:
            return error("You can't match that card.")
        _emit_state(socketio, room)

    @socketio.on("s4_power_peek_own")
    def on_peek_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = room.power_peek_own(uid, _int(data, "slot"))
        if res is None:
            return error("Invalid target.")
        socketio.emit("s4_peek", res["peeked"], to=request.sid)
        _emit_state(socketio, room)

    @socketio.on("s4_power_peek_opp")
    def on_peek_opp(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = room.power_peek_opp(uid, (data or {}).get("opp"), _int(data, "slot"))
        if res is None:
            return error("Invalid target.")
        socketio.emit("s4_peek", res["peeked"], to=request.sid)
        _emit_state(socketio, room)

    @socketio.on("s4_power_blind_swap")
    def on_blind_swap(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        d = data or {}
        res = room.power_blind_swap(uid, _int(d, "own_slot"), d.get("opp"), _int(d, "opp_slot"))
        if res is None:
            return error("Invalid swap target.")
        _emit_state(socketio, room)

    @socketio.on("s4_power_king_look")
    def on_king_look(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        d = data or {}
        res = room.power_king_look(uid, _int(d, "own_slot"), d.get("opp"), _int(d, "opp_slot"))
        if res is None:
            return error("Invalid target.")
        socketio.emit("s4_king_look", {"looked": res["looked"]}, to=request.sid)
        _emit_state(socketio, room)

    @socketio.on("s4_power_king_decide")
    def on_king_decide(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.power_king_decide(uid, bool((data or {}).get("swap"))) is None:
            return error("No King decision pending.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_center_own")
    def on_match_center_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.match_center_own(uid, _int(data, "slot")) is None:
            return error("You can't match right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_react_match")
    def on_react_match(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        d = data or {}
        res = room.react_match(uid, d.get("targets"), d.get("replacements", []))
        if res is None:
            return error("That match is no longer valid.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_center_opp")
    def on_match_center_opp(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = room.match_center_opp(uid, (data or {}).get("target"), _int(data, "slot"))
        if res is None:
            return error("You can't match that card.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_pass")
    def on_match_pass(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        # Decline this window: mark attempted so the prompt clears for this player.
        if room.phase == PHASE_MATCH and room._can_attempt_match(uid):
            room.match_attempted.add(uid)
            _emit_state(socketio, room)

    @socketio.on("s4_stop")
    def on_stop(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if room.call_stop(uid) is None:
            return error("You can't call Stop right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_next_round")
    def on_next_round(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if not room.is_host(uid):
            return error("Only the host can start the next round.")
        if room.state != STATE_ROUND_END:
            return error("There's no round to advance.")
        room.start_round()
        _emit_state(socketio, room)


# ================= director ticker (turn timer + bot) =================
_bot_act_at: dict = {}


def _auto_play(room, uid):
    """Keep the table moving when a human times out."""
    if room.phase == PHASE_POWER:
        room.power_skip(uid)
    elif room.phase == PHASE_DECIDE:
        room.discard(uid)
        if room.phase == PHASE_POWER:
            room.power_skip(uid)
    else:  # PHASE_DRAW
        if room.draw(uid) is not None:
            room.discard(uid)
            if room.phase == PHASE_POWER:
                room.power_skip(uid)


def _bot_move(room, bot_id):
    """Play one complete bot turn (draw -> decide -> power)."""
    if room.phase == PHASE_DRAW:
        if ai.should_stop(room, bot_id):
            room.call_stop(bot_id)
            return
        if room.draw(bot_id) is None:
            return
    if room.phase == PHASE_DECIDE and room.drawn_by == bot_id:
        action, slot = ai.decide_after_draw(room, bot_id, room.drawn)
        if action == "match_own":
            room.match_own(bot_id, slot)
        elif action == "keep":
            room.keep(bot_id, slot)
        else:
            room.discard(bot_id)
    if room.phase == PHASE_POWER and (room.pending_power or {}).get("by") == bot_id:
        plan = ai.resolve_power(room, bot_id, room.pending_power["rank"])
        if plan is None:
            room.power_skip(bot_id)
        elif plan[0] == "peek_own":
            room.power_peek_own(bot_id, plan[1])
        elif plan[0] == "peek_opp":
            room.power_peek_opp(bot_id, plan[1], plan[2])
        elif plan[0] == "blind_swap":
            room.power_blind_swap(bot_id, plan[1], plan[2], plan[3])
        elif plan[0] == "king_look":
            _own, opp, opp_slot = plan[1], plan[2], plan[3]
            look = room.power_king_look(bot_id, _own, opp, opp_slot)
            do_swap = False
            if look is not None:
                do_swap = ai.king_should_swap(room.slots[bot_id][_own], room.slots[opp][opp_slot])
            room.power_king_decide(bot_id, do_swap)


def _tick_room(socketio, room):
    if room.phase == PHASE_PREVIEW:
        if room.expire_preview():
            _emit_state(socketio, room)
        return

    # Match window: bots may react (only to matches they know), then expire on time.
    if room.phase == PHASE_MATCH:
        acted = False
        for uid, p in list(room.players.items()):
            if not p.is_bot or not room._can_attempt_match(uid):
                continue
            plan = ai.find_match(room, uid)
            if plan is None:
                continue
            res = room.react_match(uid, [{"owner": uid, "slot": plan[1]}], [])
            if res is not None:
                acted = True
                if res.get("success"):
                    break
            if room.phase != PHASE_MATCH:
                break
        if room.phase == PHASE_MATCH and room.expire_match_window():
            acted = True
        if acted:
            _emit_state(socketio, room)
        return

    cur = room.current_turn_id()
    if cur is None:
        return
    p = room.players.get(cur)
    if p and p.is_bot:
        now = time.time()
        if room.code not in _bot_act_at:
            _bot_act_at[room.code] = now + ai.bot_delay()
            return
        if now < _bot_act_at[room.code]:
            return
        del _bot_act_at[room.code]
        _bot_move(room, cur)
        _emit_state(socketio, room)
        return
    # human timeout
    if room.turn_seconds_left() <= 0:
        _auto_play(room, cur)
        if p:
            p.timeout_count += 1
            socketio.emit("s4_timeout", {"user_id": cur, "name": p.name}, to=room.code)
        _emit_state(socketio, room)


director.register_ticker(GAME, _tick_room)
presenter.register(GAME, _deal_private)
