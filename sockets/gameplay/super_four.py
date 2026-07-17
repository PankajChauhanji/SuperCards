"""Super 4 gameplay: socket handlers + turn-timer / bot ticker.

All authority lives in the Room; the client only sends slot/target selections.
Hidden information is strict: after every action the server broadcasts the public
`s4_state` (no faces) plus each connected player's private `your_view` (only the
cards they know), and peeks are sent to the acting socket alone. Handlers guard on
room.game_type == "super_four".

Every table event is announced with a short on-screen toast (rules.txt: "For
each event we need proper messages in screen"). The act_* wrappers pair a Room
mutation with its announcement so humans, bots and timeout auto-play all produce
the same messages.
"""
import time

from flask import request
from flask_socketio import emit as _femit

from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.super_four import ai, powers
from game.super_four.room import PHASE_DRAW, PHASE_DECIDE, PHASE_POWER, PHASE_MATCH, PHASE_PREVIEW
from sockets import director, presenter
from sockets.common import error

GAME = "super_four"
TOAST_MS = 1600                      # rules.txt: messages stay ~1.5 seconds
_SUIT_GLYPH = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}


def _label(card) -> str:
    if card is None:
        return "a card"
    return f"{card.to_dict()['code']}{_SUIT_GLYPH.get(card.suit, '')}"


def _name(room, uid) -> str:
    p = room.players.get(uid)
    return p.name if p else "Someone"


def _toast(socketio, room, message, ms=TOAST_MS):
    socketio.emit("toast", {"message": message, "ms": ms}, to=room.code)


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


# ================= actions + their announcements =================
# Each wrapper mutates through the Room and, on success, tells the whole table
# what just happened. They are used by the human handlers AND the director
# (bots, timeouts) so messages are consistent no matter who acted.

def act_draw(socketio, room, uid):
    res = room.draw(uid)
    if res is not None:
        msg = f"{_name(room, uid)} drew from the deck"
        if res.get("reshuffled"):
            msg += " (🔀 discards reshuffled in)"
        _toast(socketio, room, msg)
    return res


def act_keep(socketio, room, uid, slot):
    ok = room.keep(uid, slot)
    if ok:
        _toast(socketio, room, f"{_name(room, uid)} kept the drawn card in slot {slot + 1}")
    return ok


def act_discard(socketio, room, uid):
    res = room.discard(uid)
    if res is not None:
        msg = f"{_name(room, uid)} threw {_label(room.center)} on the table"
        if res.get("power_rank"):
            msg += f" — {powers.power_label(res['power_rank'])}"
        _toast(socketio, room, msg, 2200)
    return res


def act_match_own(socketio, room, uid, slot):
    res = room.match_own(uid, slot)
    if res is not None:
        if res.get("success"):
            _toast(socketio, room,
                   f"⚡ {_name(room, uid)} matched their own card — slot {res['slot'] + 1} emptied!",
                   2200)
        else:
            _toast(socketio, room, f"{_name(room, uid)} guessed wrong — penalty card", 2200)
    return res


def act_react_match(socketio, room, uid, targets, replacements):
    res = room.react_match(uid, targets, replacements)
    if res is not None:
        if res.get("success"):
            n = len(res.get("discarded", []))
            _toast(socketio, room,
                   f"⚡ {_name(room, uid)} matched {n} card{'s' if n != 1 else ''} first!",
                   2200)
        else:
            _toast(socketio, room,
                   f"{_name(room, uid)} threw a wrong match — penalty card", 2200)
    return res


def act_power_peek_own(socketio, room, uid, slot):
    res = room.power_peek_own(uid, slot)
    if res is not None:
        _toast(socketio, room, f"{_name(room, uid)} peeked at their own card #{slot + 1}")
    return res


def act_power_peek_opp(socketio, room, uid, opp, slot):
    res = room.power_peek_opp(uid, opp, slot)
    if res is not None:
        _toast(socketio, room,
               f"{_name(room, uid)} peeked at {_name(room, opp)}'s card #{slot + 1}")
    return res


def act_power_blind_swap(socketio, room, uid, own_slot, opp, opp_slot):
    res = room.power_blind_swap(uid, own_slot, opp, opp_slot)
    if res is not None:
        _toast(socketio, room,
               f"{_name(room, uid)} blind-swapped their #{own_slot + 1} "
               f"with {_name(room, opp)}'s #{opp_slot + 1}")
    return res


def act_power_king_decide(socketio, room, uid, do_swap):
    res = room.power_king_decide(uid, do_swap)
    if res is not None:
        what = "swapped the two cards" if res.get("swapped") else "left the cards in place"
        _toast(socketio, room, f"{_name(room, uid)} used the King and {what}")
    return res


def act_power_skip(socketio, room, uid):
    ok = room.power_skip(uid)
    if ok:
        _toast(socketio, room, f"{_name(room, uid)} skipped their power")
    return ok


def act_stop(socketio, room, uid):
    res = room.call_stop(uid)
    if res is not None:
        _toast(socketio, room,
               f"✋ {_name(room, uid)} called STOP — everyone gets one final turn!",
               2600)
    return res


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
        if act_draw(socketio, room, uid) is None:
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
        _toast(socketio, room, "Cards are face-down — play from memory!", 2200)
        _emit_state(socketio, room)

    @socketio.on("s4_keep")
    def on_keep(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if not act_keep(socketio, room, uid, _int(data, "slot")):
            return error("You can't keep into that slot.")
        _emit_state(socketio, room)

    @socketio.on("s4_discard")
    def on_discard(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if act_discard(socketio, room, uid) is None:
            return error("You can't discard right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_own")
    def on_match_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if act_match_own(socketio, room, uid, _int(data, "slot")) is None:
            return error("You can't match that card.")
        _emit_state(socketio, room)

    @socketio.on("s4_power_peek_own")
    def on_peek_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = act_power_peek_own(socketio, room, uid, _int(data, "slot"))
        if res is None:
            return error("Invalid target.")
        socketio.emit("s4_peek", res["peeked"], to=request.sid)
        _emit_state(socketio, room)

    @socketio.on("s4_power_peek_opp")
    def on_peek_opp(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = act_power_peek_opp(socketio, room, uid, (data or {}).get("opp"), _int(data, "slot"))
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
        res = act_power_blind_swap(socketio, room, uid,
                                   _int(d, "own_slot"), d.get("opp"), _int(d, "opp_slot"))
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
        if act_power_king_decide(socketio, room, uid, bool((data or {}).get("swap"))) is None:
            return error("No King decision pending.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_center_own")
    def on_match_center_own(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        res = act_react_match(socketio, room, uid,
                              [{"owner": uid, "slot": _int(data, "slot")}], [])
        if res is None:
            return error("You can't match right now.")
        _emit_state(socketio, room)

    @socketio.on("s4_react_match")
    def on_react_match(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        d = data or {}
        res = act_react_match(socketio, room, uid, d.get("targets"), d.get("replacements", []))
        if res is None:
            if room.phase != PHASE_MATCH:
                return error("Too late — the match window is closed.")
            return error("That match isn't valid.")
        _emit_state(socketio, room)

    @socketio.on("s4_match_pass")
    def on_match_pass(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        # Decline this window: mark passed so the prompt clears for this player.
        if room.match_decline(uid):
            _emit_state(socketio, room)

    @socketio.on("s4_stop")
    def on_stop(data):
        room, uid = _room_uid(data)
        if room is None:
            return
        if act_stop(socketio, room, uid) is None:
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


def _auto_play(socketio, room, uid):
    """Keep the table moving when a human times out."""
    if room.phase == PHASE_POWER:
        act_power_skip(socketio, room, uid)
    elif room.phase == PHASE_DECIDE:
        act_discard(socketio, room, uid)
        if room.phase == PHASE_POWER:
            act_power_skip(socketio, room, uid)
    else:  # PHASE_DRAW
        if act_draw(socketio, room, uid) is not None:
            act_discard(socketio, room, uid)
            if room.phase == PHASE_POWER:
                act_power_skip(socketio, room, uid)


def _bot_move(socketio, room, bot_id):
    """Play one complete bot turn (draw -> decide -> power)."""
    if room.phase == PHASE_DRAW:
        if ai.should_stop(room, bot_id) and act_stop(socketio, room, bot_id) is not None:
            return
        if act_draw(socketio, room, bot_id) is None:
            return
    if room.phase == PHASE_DECIDE and room.drawn_by == bot_id:
        action, slot = ai.decide_after_draw(room, bot_id, room.drawn)
        if action == "match_own":
            act_match_own(socketio, room, bot_id, slot)
        elif action == "keep":
            act_keep(socketio, room, bot_id, slot)
        else:
            act_discard(socketio, room, bot_id)
    if room.phase == PHASE_POWER and (room.pending_power or {}).get("by") == bot_id:
        plan = ai.resolve_power(room, bot_id, room.pending_power["rank"])
        if plan is None:
            act_power_skip(socketio, room, bot_id)
        elif plan[0] == "peek_own":
            act_power_peek_own(socketio, room, bot_id, plan[1])
        elif plan[0] == "peek_opp":
            act_power_peek_opp(socketio, room, bot_id, plan[1], plan[2])
        elif plan[0] == "blind_swap":
            act_power_blind_swap(socketio, room, bot_id, plan[1], plan[2], plan[3])
        elif plan[0] == "king_look":
            _own, opp, opp_slot = plan[1], plan[2], plan[3]
            look = room.power_king_look(bot_id, _own, opp, opp_slot)
            do_swap = False
            if look is not None:
                do_swap = ai.king_should_swap(room.slots[bot_id][_own], room.slots[opp][opp_slot])
            act_power_king_decide(socketio, room, bot_id, do_swap)
        # Anti-freeze: never leave a bot stranded on an unresolvable power —
        # if the chosen plan failed for any reason, skip it and move on.
        if room.phase == PHASE_POWER and (room.pending_power or {}).get("by") == bot_id:
            act_power_skip(socketio, room, bot_id)


def _tick_room(socketio, room):
    if room.phase == PHASE_PREVIEW:
        if room.expire_preview():
            _toast(socketio, room, "Preview over — play from memory!", 2200)
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
            res = act_react_match(socketio, room, uid, [{"owner": uid, "slot": plan[1]}], [])
            if res is not None:
                acted = True
            if room.phase != PHASE_MATCH:
                break
        # A bot that is next to play doesn't wait the window out: after its usual
        # thinking delay it starts its turn, which closes the window early (the
        # same rule humans get).
        if room.phase == PHASE_MATCH:
            nxt = room.next_player_id()
            np = room.players.get(nxt) if nxt else None
            if np and np.is_bot:
                now = time.time()
                key = room.code + ":mw"
                if key not in _bot_act_at:
                    _bot_act_at[key] = now + ai.bot_delay()
                elif now >= _bot_act_at[key]:
                    del _bot_act_at[key]
                    if ai.should_stop(room, nxt) and act_stop(socketio, room, nxt) is not None:
                        acted = True
                    else:
                        acted = act_draw(socketio, room, nxt) is not None
        if room.phase == PHASE_MATCH and room.expire_match_window():
            acted = True
        if acted:
            _emit_state(socketio, room)
        return
    _bot_act_at.pop(room.code + ":mw", None)

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
        _bot_move(socketio, room, cur)
        _emit_state(socketio, room)
        return
    # human timeout: strike first — at the limit the player is benched to
    # spectator (Super Seven behavior); otherwise auto-play keeps things moving.
    if room.turn_seconds_left() <= 0:
        info = room.timeout_strike(cur)
        name = p.name if p else "Someone"
        if info["removed"]:
            _toast(socketio, room,
                   f"⏱ {name} missed {info['timeout_count']} turns — moved to spectators. "
                   "The host can admit them back.", 3000)
            socketio.emit("player_list",
                          {"players": room.public_players(), "host_id": room.host_id},
                          to=room.code)
        else:
            _auto_play(socketio, room, cur)
            _toast(socketio, room, f"⏱ {name} ran out of time — turn auto-played", 2200)
        socketio.emit("s4_timeout",
                      {"user_id": cur, "name": name,
                       "timeout_count": info["timeout_count"],
                       "removed": info["removed"]},
                      to=room.code)
        _emit_state(socketio, room)


director.register_ticker(GAME, _tick_room)
presenter.register(GAME, _deal_private)
