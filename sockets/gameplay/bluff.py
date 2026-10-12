"""Bluff gameplay: socket handlers + turn-timer ticker.
"""
from game.bluff.visibility import public_card_ids
from game.core.cards import RANKS, rank_code
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from sockets import audience, director, presenter
# Guarded drop-in for flask_socketio.emit — see sockets/audience.py.
from sockets.audience import emit
from sockets.common import error

audience.register("bluff", public_card_ids)

GAME = "bluff"
# The ranks a player may declare: A, 2..10, J, Q, K.
_RANK_CODES = {rank_code(r) for r in RANKS}

def _deal_private(room, user_id=None):
    targets = ([room.players.get(user_id)] if user_id else room.connected_players())
    for player in targets:
        if not player or player.is_bot or not player.sid:
            continue
        emit("your_hand", {"cards": room.hand_for(player.user_id)}, to=player.sid)

def _refresh_public(room):
    """Re-broadcast public state after a structural change such as a quit."""
    if room.state == STATE_GAME_END:
        emit("game_end", room.game_end_payload(), to=room.code)
    else:
        emit("table_state", room.public_round_state(), to=room.code)

def _resync_one(room, user_id):
    """Send one player the complete current state (see presenter.register_resync).

    Bluff is a single race to an empty hand, so it has no ROUND_END branch —
    it goes straight from in-round to STATE_GAME_END.
    """
    player = room.players.get(user_id)
    if not player or not player.sid:
        return
    if room.in_round():
        emit("round_start", room.public_round_state(), to=player.sid)
        _deal_private(room, user_id)
    elif room.state == STATE_GAME_END:
        emit("game_end", room.game_end_payload(), to=player.sid)


presenter.register(GAME, _deal_private)
presenter.register_refresh(GAME, _refresh_public)
presenter.register_resync(GAME, _resync_one)

# How long the challenged cards stay face up before the pile moves.
SHOW_SECONDS = 3


def _run_show(socketio, room, challenger_id, background=False):
    """A Show, start to finish: reveal, hold the cards up, settle, broadcast.

    One routine for a human's Show and a bot's. While the cards are face up the
    room refuses moves (``is_showing``); _finish_show clears that flag in
    ``finally`` so no surprise during the pause — a player leaving, the game
    ending — can leave the table stuck mid-reveal, which used to freeze the
    room for everyone.

    ``background``: a bot's Show comes from the director, whose one loop ticks
    every room on the server in turn, so a 3-second pause there used to freeze
    every other table's timers and computer players with it. The pause then
    runs as its own task; the lock keeps this room still meanwhile.
    """
    result = room.apply_show(challenger_id)
    if not result:
        return
    room.is_showing = True
    try:
        socketio.emit("bluff_show_result", result, to=room.code)
    except Exception:
        room.is_showing = False
        raise
    start = getattr(socketio, "start_background_task", None) if background else None
    if start is not None:
        start(_finish_show, socketio, room, result)
    else:
        _finish_show(socketio, room, result)


def _finish_show(socketio, room, result):
    import eventlet

    try:
        eventlet.sleep(SHOW_SECONDS)
        room.resolve_show(result)
    finally:
        room.is_showing = False

    # Give the loser their new hand
    loser = room.players.get(result["loser"])
    if loser and loser.connected and loser.sid:
        socketio.emit("your_hand", {"cards": room.hand_for(loser.user_id)}, to=loser.sid)

    # A challenge can settle the game outright: a defender who truthfully
    # played their last cards is out the moment the show resolves, and that
    # can be the finish that fills the podium (or a quit during the reveal
    # ended it). Without this the room would sit in STATE_GAME_END while the
    # clients were only told the table changed.
    if room.state == STATE_GAME_END:
        socketio.emit("game_end", room.game_end_payload(), to=room.code)
        return
    socketio.emit("table_state", room.public_round_state(), to=room.code)


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

        # Any number of cards, up to the whole hand — whether a big claim is
        # believable is for the next player to judge with Show, not for the
        # server to cap. card_objects() below still rejects cards not in hand
        # and duplicates.
        if not card_ids:
            return error("Select at least one card to throw.")
        if not declared_rank:
            return error("You must declare a rank.")
        if declared_rank not in _RANK_CODES:
            return error("That isn't a card rank.")
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
        if room.last_play.get("user_id") == user_id:
            return error("You can't call Show on your own play.")

        _run_show(socketio, room, user_id)

    @socketio.on("bluff_shuffle_seats")
    def on_shuffle_seats(data):
        """Host's in-game "Shuffle seats" (see Room.request_shuffle).

        Not a turn action — the host may press it whenever — so it does not go
        through _resolve(). It never moves anyone mid-play: at a fresh round it
        re-seats at once, otherwise it is queued for the moment the pile clears.
        Pressing again while queued cancels. Everyone learns the outcome from
        the table state itself (shuffle_pending / seat_shuffles), so a client
        that misses this broadcast still catches up on its next sync.
        """
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if room.game_type != GAME:
            return
        if not room.is_host(user_id):
            return error("Only the host can shuffle the seats.")
        if room.state != STATE_IN_TURN or room.game_over:
            return error("Seats can be shuffled during a game.")

        room.request_shuffle()
        emit("table_state", room.public_round_state(), to=room.code)

    @socketio.on("bluff_next_round")
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


# Bot scheduling: (room_code, bot_id) -> float (earliest time to act). Keyed per
# bot because a room may now hold several — see sockets/gameplay/super_seven.py
# for the failure a room-wide key allows.
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
        if not director.bots_should_act(room):
            return  # nobody left to play for — see director.bots_should_act
        _tick_bot(socketio, room, cur)
        return

    # Turn moved to a human: drop every bot schedule for this room so none of
    # them carries a stale deadline into its next turn.
    for stale in [k for k in _bot_act_at if k[0] == code]:
        _bot_act_at.pop(stale, None)

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

    key = (code, bot_id)

    if room.state == STATE_GAME_END:
        _bot_act_at.pop(key, None)
        return

    if key not in _bot_act_at:
        _bot_act_at[key] = now + bot_delay()
        return

    if now < _bot_act_at[key]:
        return

    del _bot_act_at[key]

    move = decide_move(room, bot_id)
    
    if move["action"] == "pass":
        room.apply_pass(bot_id)
        socketio.emit("player_passed", {"by": bot_id}, to=code)
    
    elif move["action"] == "show":
        _run_show(socketio, room, bot_id, background=True)
        return

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
