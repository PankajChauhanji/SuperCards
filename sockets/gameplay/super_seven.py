"""Super Seven gameplay: socket handlers + turn-timer/bot ticker.

All authority lives here and in the room — the client only sends a selection of
card ids; the server decides whether it is legal, what action it is, and what
happens next. After every change the room broadcasts an authoritative
`table_state` snapshot (counts only) plus a private `your_hand` to whoever's hand
changed, so clients never drift from server truth.

Every handler guards on room.game_type == "super_seven" so an event aimed at a
different variant's room is ignored rather than misapplied. The director ticker
(registered at the bottom) drives auto-play, the post-discard pick timer, and the
single-player Suryavanshi bot.
"""
import time

from flask_socketio import emit

from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.super_seven.rules import infer_action
from sockets import director, presenter
from sockets.common import error

GAME = "super_seven"


def _deal_private(room, user_id=None):
    """Private deal for Super Seven: each player gets their own hand only."""
    targets = ([room.players.get(user_id)] if user_id else room.connected_players())
    for player in targets:
        if not player or player.is_bot or not player.sid:
            continue
        emit("your_hand", {"cards": room.hand_for(player.user_id)}, to=player.sid)


presenter.register(GAME, _deal_private)


def register(socketio, manager):

    def _resolve(data):
        """Common guard: returns (room, user_id) or (None, None) after erroring."""
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            error("This room no longer exists.")
            return None, None
        if room.game_type != GAME:
            # Another variant owns this room; not our event to handle.
            return None, None
        if room.state != STATE_IN_TURN:
            error("The game is not in play.")
            return None, None
        if room.current_turn_id() != user_id:
            error("It's not your turn.")
            return None, None
        return room, user_id

    def _auto_end_if_stuck(room):
        """End the round automatically if no one can act (everyone safe)."""
        if room.state == STATE_IN_TURN and room.active_count() <= 1:
            result = room.end_round(None)
            emit("round_end", room.round_end_payload(result), to=room.code)
            return True
        return False

    @socketio.on("play_cards")
    def on_play(data):
        room, user_id = _resolve(data)
        if room is None:
            return
        if room.awaiting_draw:
            return error("Draw a card before playing again.")

        card_ids = (data or {}).get("card_ids") or []
        cards = room.card_objects(user_id, card_ids)
        if cards is None:
            return error("Those cards aren't in your hand.")

        action = infer_action(
            [c.rank for c in cards],
            room.center_rank_set(),
        )
        if action is None:
            return error("That's not a legal play.")

        owes_draw = room.apply_throw(user_id, cards, action)

        # Notify the table what was played (faces are public — they're on the table).
        emit(
            "cards_played",
            {
                "by": user_id,
                "action_type": action,
                "played": [c.to_dict() for c in cards],
                "owes_draw": owes_draw,
            },
            to=room.code,
        )
        # The thrower's hand changed — send it privately, including owes_draw
        # so the client updates awaitingDraw immediately without waiting for table_state.
        emit("your_hand", {"cards": room.hand_for(user_id), "owes_draw": owes_draw})
        # If that throw left nobody able to act, the round auto-ends.
        if _auto_end_if_stuck(room):
            return
        # Authoritative snapshot for everyone.
        emit("table_state", room.public_round_state(), to=room.code)

    @socketio.on("draw_card")
    def on_draw(data):
        room, user_id = _resolve(data)
        if room is None:
            return
        if not room.awaiting_draw:
            return error("There's no draw to take right now.")

        result = room.draw_one(user_id)
        drawn_id = result["card"].id if result["card"] else None

        emit("your_hand", {"cards": room.hand_for(user_id), "drawn": drawn_id})
        if result["reshuffled"]:
            emit("deck_reshuffled", {}, to=room.code)
        if _auto_end_if_stuck(room):
            return
        emit("table_state", room.public_round_state(), to=room.code)

    @socketio.on("call_stop")
    def on_stop(data):
        room, user_id = _resolve(data)
        if room is None:
            return
        if room.awaiting_draw:
            return error("Finish your draw first.")
        if not room.first_orbit_complete:
            return error("Stop can't be called during the first orbit.")
        if room.players[user_id].is_safe:
            return error("You're already safe — no need to call Stop.")

        result = room.end_round(user_id)
        emit("round_end", room.round_end_payload(result), to=room.code)

    @socketio.on("next_round")
    def on_next_round(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if room.game_type != GAME:
            return
        if not room.is_host(user_id):
            return error("Only the host can start the next round.")
        if room.state != STATE_ROUND_END:
            return error("There's no round to advance.")

        room.start_round()
        emit("round_start", room.public_round_state(), to=room.code)
        # Deal hands privately; eliminated players receive an empty hand so
        # their old cards clear and they continue as spectators.
        # Bot players have no socket — skip them.
        for player in room.connected_players():
            if player.is_bot:
                continue
            emit("your_hand", {"cards": room.hand_for(player.user_id)}, to=player.sid)


# ---- director ticker (turn timer + bot) -------------------------------------
# Per-room bot scheduling: room_code -> float (earliest time to act).
# Only populated for solo rooms; never touches group rooms.
_bot_act_at: dict = {}


def _tick_room(socketio, room):
    """Resolve one in-turn Super Seven room's timers / bot move."""
    code = room.code
    cur = room.current_turn_id()
    if cur is None:
        return

    # ---- single-player bot branch (only when it is the bot's turn) ----
    cur_player = room.players.get(cur)
    if cur_player and cur_player.is_bot:
        _tick_bot(socketio, room, cur)
        return  # bot handles everything; skip human timeout logic

    # 1) Post-discard pick timer: auto-draw after the fixed 3s, NO penalty.
    #    While a draw is owed, the turn timer does not also fire.
    if room.awaiting_draw:
        if room.pick_timed_out():
            sid = room.players[cur].sid
            name = room.players[cur].name
            result = room.draw_one(cur)
            drawn_id = result["card"].id if result["card"] else None
            socketio.emit("auto_picked", {"user_id": cur, "name": name}, to=code)
            if result["reshuffled"]:
                socketio.emit("deck_reshuffled", {}, to=code)
            if sid:
                socketio.emit("your_hand",
                              {"cards": room.hand_for(cur), "drawn": drawn_id}, to=sid)
            socketio.emit("table_state", room.public_round_state(), to=code)
        return

    # 2) Turn timer: penalised auto-play / removal (only when no draw owed).
    if not room.is_timed_out():
        return

    name = room.players[cur].name
    sid = room.players[cur].sid
    info = room.force_timeout(cur)

    socketio.emit(
        "player_timed_out",
        {"user_id": cur, "name": name,
         "timeout_count": info["timeout_count"], "removed": info["removed"]},
        to=code,
    )
    if info["removed"]:
        socketio.emit(
            "player_eliminated",
            {"user_id": cur, "name": name, "reason": "timeouts"},
            to=code,
        )

    # A mid-round removal can end the whole game.
    if room.state == STATE_GAME_END:
        socketio.emit("game_end", room.game_end_payload(), to=code)
        return

    # If the auto-play left nobody able to act, the round ends now.
    if room.active_count() <= 1:
        result = room.end_round(None)
        socketio.emit("round_end", room.round_end_payload(result), to=code)
        return

    # Normal case: the turn moved on. Update the timed-out player's hand
    # (if still connected) and broadcast the new table state.
    if sid:
        socketio.emit("your_hand",
                      {"cards": room.hand_for(cur), "drawn": info.get("drawn")},
                      to=sid)
    socketio.emit("table_state", room.public_round_state(), to=code)


# ---- single-player bot logic ------------------------------------------------
# SINGLE-PLAYER MODE ONLY — this function is never reached in group rooms.

def _tick_bot(socketio, room, bot_id: str):
    """Drive Suryavanshi's turn with a human-feel random delay."""
    from game.super_seven.ai import decide_move, bot_delay
    from game.super_seven.rules import infer_action

    code = room.code
    now = time.time()

    # Clear any stale schedule if the room is no longer in a playable state.
    if room.state != STATE_IN_TURN:
        _bot_act_at.pop(code, None)
        return

    # Schedule the bot's action if not already scheduled.
    if code not in _bot_act_at:
        _bot_act_at[code] = now + bot_delay()
        return

    # Not yet time to act.
    if now < _bot_act_at[code]:
        return

    # Time to act — clear the schedule entry so the next step re-schedules.
    del _bot_act_at[code]

    move = decide_move(room, bot_id)
    if move is None:
        return

    # ---- draw owed ----
    if move["action"] == "draw":
        result = room.draw_one(bot_id)
        drawn_id = result["card"].id if result["card"] else None
        if result["reshuffled"]:
            socketio.emit("deck_reshuffled", {}, to=code)
        socketio.emit("table_state", room.public_round_state(), to=code)
        return

    # ---- call Stop ----
    if move["action"] == "stop":
        result = room.end_round(bot_id)
        socketio.emit("round_end", room.round_end_payload(result), to=code)
        return

    # ---- play cards ----
    cards = move["cards"]
    action_type = move["action_type"]

    # Re-validate with infer_action so the room never gets into an illegal state.
    inferred = infer_action([c.rank for c in cards], room.center_rank_set())
    if inferred is None:
        # AI suggested an illegal move; fall back to discarding the highest card.
        from game.super_seven.rules import ACTION_SINGLE
        highest = max(room.players[bot_id].hand, key=lambda c: c.value)
        cards = [highest]
        action_type = ACTION_SINGLE

    owes_draw = room.apply_throw(bot_id, cards, action_type)

    socketio.emit(
        "cards_played",
        {
            "by": bot_id,
            "action_type": action_type,
            "played": [c.to_dict() for c in cards],
            "owes_draw": owes_draw,
        },
        to=code,
    )

    # Round auto-end if everyone is now safe.
    if room.state == STATE_IN_TURN and room.active_count() <= 1:
        result = room.end_round(None)
        socketio.emit("round_end", room.round_end_payload(result), to=code)
        return

    socketio.emit("table_state", room.public_round_state(), to=code)

    # If the throw owed a draw, schedule the draw separately.
    if owes_draw:
        _bot_act_at[code] = time.time() + bot_delay()


# Register this variant's ticker at import time so the director dispatches
# super_seven rooms to _tick_room. The socketio instance is supplied per call by
# the director's scan loop (never closed over here), which also lets the engine
# tests drive _tick_room with a fake socket.
director.register_ticker(GAME, _tick_room)
