"""The turn-timer director — the only background routine in the app.

Once a second it scans active rooms for a turn that has run past its deadline
and resolves it: auto-play a discard (or auto-draw if one was owed), and remove
a player who hits the timeout limit. It then broadcasts the consequences. This
is what keeps an AFK player from freezing the table.

For single-player rooms the bot (Suryavanshi) is detected here and its moves
are scheduled with a random human-feel delay without touching the group-play
code paths at all.

Run as an eventlet background task started in app.py.
"""
import time
from game.super_seven.room import STATE_IN_TURN, STATE_GAME_END

# Per-room bot scheduling: room_code -> float (earliest time to act)
# Only populated for solo rooms; never touches group rooms.
_bot_act_at: dict = {}


def register(socketio, manager):
    def loop():
        while True:
            socketio.sleep(1)
            try:
                _tick(socketio, manager)
            except Exception:
                # A background loop must never die on a transient error.
                pass

    socketio.start_background_task(loop)


def _tick(socketio, manager):
    for code, room in list(manager.rooms.items()):
        if room.state != STATE_IN_TURN:
            continue
        cur = room.current_turn_id()
        if cur is None:
            continue

        # ---- single-player bot branch (only when it is the bot's turn) ----
        cur_player = room.players.get(cur)
        if cur_player and cur_player.is_bot:
            _tick_bot(socketio, room, cur)
            continue  # bot handles everything; skip human timeout logic

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
            continue

        # 2) Turn timer: penalised auto-play / removal (only when no draw owed).
        if not room.is_timed_out():
            continue

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
            continue

        # If the auto-play left nobody able to act, the round ends now.
        # active_count <= 1: if 0 players or only 1 player remains active
        # (everyone else safe/eliminated), the round ends — the last player
        # should not be forced to keep playing alone with nobody to beat.
        if room.active_count() <= 1:
            result = room.end_round(None)
            socketio.emit("round_end", room.round_end_payload(result), to=code)
            continue

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
    """Drive Suryavanshi's turn with a human-feel random delay.

    Uses _bot_act_at[room.code] as a scheduled timestamp:
      • If not yet set, schedule the move BOT_THINK_MIN..MAX seconds from now.
      • Once the timestamp passes, ask ai.decide_move() for the best action
        and execute it exactly the same way a human socket event would.
    """
    from game.super_seven.ai import decide_move, bot_delay
    from game.super_seven.rules import infer_action

    code = room.code
    now = time.time()

    # Clear any stale schedule if the room is no longer in a playable state
    # (e.g. round ended, rematch reset) so the next round starts cleanly.
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
