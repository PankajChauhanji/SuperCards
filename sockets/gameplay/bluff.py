"""Bluff gameplay: socket handlers + turn-timer ticker.
"""
from flask_socketio import emit
from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from sockets import director, presenter
from sockets.common import error

GAME = "bluff"

def _deal_private(room, user_id=None):
    targets = ([room.players.get(user_id)] if user_id else room.connected_players())
    for player in targets:
        if not player or player.is_bot or not player.sid:
            continue
        emit("your_hand", {"cards": room.hand_for(player.user_id)}, to=player.sid)

presenter.register(GAME, _deal_private)

def register(socketio, manager):

    def _resolve(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            error("This room no longer exists.")
            return None, None
        if room.game_type != GAME:
            return None, None
        if room.state != STATE_IN_TURN:
            error("The game is not in play.")
            return None, None
        if getattr(room, "is_showing", False):
            error("Cards are being revealed.")
            return None, None
        if room.current_turn_id() != user_id:
            error("It's not your turn.")
            return None, None
        return room, user_id

    @socketio.on("bluff_play")
    def on_bluff_play(data):
        room, user_id = _resolve(data)
        if room is None:
            return
        
        card_ids = data.get("card_ids") or []
        declared_rank = data.get("declared_rank")

        if not card_ids or len(card_ids) > 4:
            return error("You must throw between 1 and 4 cards.")
        if not declared_rank:
            return error("You must declare a rank.")
        if room.target_rank is not None and declared_rank != room.target_rank:
            return error(f"You must match the target rank of {room.target_rank}.")

        cards = room.card_objects(user_id, card_ids)
        if cards is None:
            return error("Those cards aren't in your hand.")

        room.apply_play(user_id, cards, declared_rank)
        
        emit("cards_played", {
            "by": user_id,
            "count": len(cards),
            "declared_rank": declared_rank
        }, to=room.code)
        
        emit("your_hand", {"cards": room.hand_for(user_id)})
        
        if room.state == STATE_GAME_END:
            emit("game_end", room.game_end_payload(), to=room.code)
            return

        emit("table_state", room.public_round_state(), to=room.code)

    @socketio.on("bluff_pass")
    def on_bluff_pass(data):
        room, user_id = _resolve(data)
        if room is None:
            return

        room.apply_pass(user_id)
        
        emit("player_passed", {"by": user_id}, to=room.code)

        if room.state == STATE_GAME_END:
            emit("game_end", room.game_end_payload(), to=room.code)
            return

        emit("table_state", room.public_round_state(), to=room.code)

    @socketio.on("bluff_show")
    def on_bluff_show(data):
        room, user_id = _resolve(data)
        if room is None:
            return

        if not room.last_play:
            return error("There's nothing to show!")
            
        result = room.apply_show(user_id)
        room.is_showing = True

        emit("bluff_show_result", result, to=room.code)
        
        import eventlet
        eventlet.sleep(3)
        
        room.resolve_show(result)
        room.is_showing = False
        
        # Give the loser their new hand
        loser_id = result["loser"]
        loser = room.players.get(loser_id)
        if loser and loser.connected and loser.sid:
            emit("your_hand", {"cards": room.hand_for(loser_id)}, to=loser.sid)

        emit("table_state", room.public_round_state(), to=room.code)

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
        if room.state not in (STATE_ROUND_END, STATE_LOBBY):
            return error("There's no round to advance.")

        room.start_round()
        emit("round_start", room.public_round_state(), to=room.code)
        _deal_private(room)


_bot_act_at: dict = {}

def _tick_room(socketio, room):
    code = room.code
    if getattr(room, "is_showing", False):
        return

    cur = room.current_turn_id()
    if cur is None:
        return

    cur_player = room.players.get(cur)
    if cur_player and cur_player.is_bot:
        _tick_bot(socketio, room, cur)
        return

    if code in _bot_act_at:
        _bot_act_at.pop(code, None)

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

    if room.state == STATE_GAME_END:
        socketio.emit("game_end", room.game_end_payload(), to=code)
        return

    if sid:
        socketio.emit("your_hand", {"cards": room.hand_for(cur)}, to=sid)
    socketio.emit("table_state", room.public_round_state(), to=code)

def _tick_bot(socketio, room, bot_id: str):
    import time
    from game.bluff.ai import decide_move, bot_delay

    code = room.code
    now = time.time()

    if room.state == STATE_GAME_END:
        _bot_act_at.pop(code, None)
        return

    if code not in _bot_act_at:
        _bot_act_at[code] = now + bot_delay()
        return

    if now < _bot_act_at[code]:
        return

    del _bot_act_at[code]

    move = decide_move(room, bot_id)
    
    if move["action"] == "pass":
        room.apply_pass(bot_id)
        socketio.emit("player_passed", {"by": bot_id}, to=code)
    
    elif move["action"] == "show":
        result = room.apply_show(bot_id)
        room.is_showing = True
        socketio.emit("bluff_show_result", result, to=code)
        
        import eventlet
        eventlet.sleep(3)
        
        room.resolve_show(result)
        room.is_showing = False
        
        loser_id = result["loser"]
        loser = room.players.get(loser_id)
        if loser and loser.connected and loser.sid:
            socketio.emit("your_hand", {"cards": room.hand_for(loser_id)}, to=loser.sid)
            
    elif move["action"] == "play":
        cards = room.card_objects(bot_id, move["cards"])
        room.apply_play(bot_id, cards, move["declared_rank"])
        socketio.emit("cards_played", {
            "by": bot_id,
            "count": len(cards),
            "declared_rank": move["declared_rank"]
        }, to=code)

    if room.state == STATE_GAME_END:
        socketio.emit("game_end", room.game_end_payload(), to=code)
        return

    socketio.emit("table_state", room.public_round_state(), to=code)

director.register_ticker(GAME, _tick_room)
