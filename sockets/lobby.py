"""Lobby handlers.

Flow (keeps one socket per client, no flicker, no accidental room deletion):
  index page  --create_room--> register room + host, reply {code}, then navigate
  index page  --join_room---->  validate + register player, reply {code}, navigate
  game page   --enter_room--->  bind this socket, mark connected, broadcast roster
  host        --start_game-->   validate, flip state, broadcast game_started

Only enter_room binds the sid and joins the Socket.IO room, so navigating away
from the index page never marks anyone disconnected.
"""
from flask import request
from flask_socketio import join_room as sio_join, leave_room as sio_leave
# Guarded drop-in for flask_socketio.emit — this module deals rounds and
# broadcasts round_start/round_end, so it carries card payloads too.
from sockets.audience import emit

from game.core import bots, registry
from game.core.states import STATE_LOBBY, STATE_ROUND_END, STATE_GAME_END
from sockets import presenter
from sockets.common import bind_sid, unbind_sid, error

NAME_MAX = 20


def _clean_name(raw) -> str:
    return (raw or "").strip()[:NAME_MAX]


def _clean_settings(raw, spec) -> dict:
    """Sanitise host-supplied settings against a game's default/bounds spec."""
    settings = dict(spec.default_settings)
    if isinstance(raw, dict):
        for key in settings:
            if key in raw:
                try:
                    settings[key] = int(raw[key])
                except (TypeError, ValueError):
                    pass
    for key, (lo, hi) in spec.settings_bounds.items():
        settings[key] = max(lo, min(hi, settings[key]))
    return settings


def register(socketio, manager):

    @socketio.on("create_room")
    def on_create(data):
        data = data or {}
        name = _clean_name(data.get("name"))
        user_id = data.get("user_id")
        if not user_id:
            return error("Missing identity.")
        if not name:
            return error("Pick a name first.")
        game_type = data.get("game_type") or registry.DEFAULT_GAME
        spec = registry.get(game_type)
        if spec is None:
            return error("Unknown game type.")
        settings = _clean_settings(data.get("settings"), spec)
        room = manager.create_room(user_id, name, settings, game_type)
        emit("room_created", {"code": room.code, "game_type": game_type})

    # ---- single-player mode ----
    @socketio.on("create_solo")
    def on_create_solo(data):
        """Create a room and pre-register the default computer player as player 2.

        The bot has a fixed user_id so the director can identify it cheaply.
        The human is the host and can still edit settings before starting.
        """
        data = data or {}
        name = _clean_name(data.get("name"))
        user_id = data.get("user_id")
        if not user_id:
            return error("Missing identity.")
        if not name:
            return error("Pick a name first.")
        game_type = data.get("game_type") or registry.DEFAULT_GAME
        spec = registry.get(game_type)
        if spec is None:
            return error("Unknown game type.")
        settings = _clean_settings(data.get("settings"), spec)
        room = manager.create_room(user_id, name, settings, game_type)

        # Same path a host takes when adding a bot from the lobby, so there is
        # exactly one way a computer player enters a room.
        bots.add_to(room)

        emit("room_created", {"code": room.code, "solo": True, "game_type": game_type})

    @socketio.on("join_room")
    def on_join(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        name = _clean_name(data.get("name"))
        user_id = data.get("user_id")
        if not user_id:
            return error("Missing identity.")
        room = manager.get_room(code)
        if room is None:
            return error("No room with that code.")

        already_in = user_id in room.players
        if not already_in:
            if room.is_full():
                return error("That room is full.")
            if not name:
                return error("Pick a name first.")
            
            player = room.register_player(user_id, name)
            if room.state != STATE_LOBBY:
                player.is_spectator = True
        else:
            room.register_player(user_id, name)

        emit("join_ok", {"code": code})

    @socketio.on("admit_spectator")
    def on_admit_spectator(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        target_id = data.get("target_id")
        penalty = int(data.get("penalty", 0))

        room = manager.get_room(code)
        if room is None: return error("Room not found.")
        if not room.is_host(user_id): return error("Only the host can admit spectators.")
        
        target = room.players.get(target_id)
        if target is None: return error("Spectator not found.")
        if not target.is_spectator: return error("Player is already in the game.")
        
        target.pending_join = True
        target.join_penalty_pct = penalty
        
        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )

    @socketio.on("enter_room")
    def on_enter(data):
        """Game page attaches its live socket and gets the room snapshot."""
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        name = _clean_name(data.get("name"))
        user_id = data.get("user_id")
        if not user_id:
            return error("Missing identity.")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")

        player = room.attach(user_id, request.sid, name)
        if player is None:
            return error("You are not in this room.")

        sio_join(code)
        bind_sid(request.sid, code, user_id)

        emit(
            "room_joined",
            {
                "code": code,
                "you": user_id,
                "game_type": room.game_type,
                "state": room.state,
                "host_id": room.host_id,
                "settings": room.settings,
                "table_theme": getattr(room, "table_theme", "casino"),
                "players": room.public_players(),
            },
        )
        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )

        # Reconnecting mid-game: hand off to the game's own resync hook. This
        # branch used to be written in Super Seven's event vocabulary for every
        # game, which left a reconnecting Super 4 player with a stale table that
        # a page reload could not repair — the reload took the same branch. The
        # shared layer no longer knows any game's event names.
        presenter.resync(room, user_id)

    @socketio.on("add_bot")
    def on_add_bot(data):
        """Host seats a computer player. Lobby only, and only up to the caps.

        A bot is worth having in a room full of real people — three friends and
        two bots is a better game than three friends alone — so this is not
        limited to single-player rooms. It is limited to the lobby, because the
        turn order is built when the round is dealt and inserting a player into a
        live rotation is a different feature with different failure modes.
        """
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can add a computer player.")
        if room.state != STATE_LOBBY:
            return error("You can only add players before the game starts.")
        if room.is_full():
            return error("The table is full.")
        if bots.is_full(room):
            return error("You can have at most %d computer players." % bots.MAX_BOTS)

        key = data.get("bot")
        if key and bots.profile(key) is None:
            return error("No such computer player.")

        bot = bots.add_to(room, key)
        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )
        emit("bot_added", {"user_id": bot.user_id, "name": bot.name}, to=code)

    @socketio.on("start_game")
    def on_start(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can start the game.")
        if room.state != STATE_LOBBY:
            return error("The game has already started.")
        min_players = registry.get(room.game_type).min_players
        if len(room.connected_players()) < min_players:
            return error(f"Need at least {min_players} players to start.")

        # Deal the first round and tell everyone.
        room.start_round()
        emit("round_start", room.public_round_state(), to=code)
        # Each player privately receives only their own view (per-game presenter).
        presenter.deal(room)

    @socketio.on("rematch")
    def on_rematch(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can start a rematch.")
        if room.state not in (STATE_ROUND_END, STATE_GAME_END):
            return error("You can only rematch once a game has finished.")

        room.reset_for_rematch()
        emit(
            "room_reset",
            {"players": room.public_players(), "host_id": room.host_id,
             "settings": room.settings, "table_theme": getattr(room, "table_theme", "casino")},
            to=code,
        )

    @socketio.on("kick_player")
    def on_kick(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        target = data.get("target")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can remove players.")
        if room.state != STATE_LOBBY:
            return error("You can only remove players in the lobby.")
        if not target or target not in room.players:
            return error("That player isn't in the room.")
        if target == room.host_id:
            return error("You can't remove yourself.")

        target_sid = room.players[target].sid
        room.remove_player(target)
        if target_sid:
            emit("kicked", {"code": code}, to=target_sid)
        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )

    @socketio.on("quit_game")
    def on_quit(data):
        """A player voluntarily leaves the room.

        Only that player is removed — their instance and scores are dropped and
        the game continues for everyone else. If the host quits, a new host is
        promoted; if the removal leaves one (or zero) players, the game ends and
        the survivor is declared the winner. Works in the lobby and mid-game, in
        every variant, via the game-agnostic Room.remove_participant().
        """
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None or user_id not in room.players:
            emit("quit_ok")   # nothing to leave; let the client navigate away
            return

        in_game = room.state != STATE_LOBBY
        room.remove_participant(user_id)

        # This socket is done with the room: drop its sid mapping so a later
        # disconnect for the same sid is a no-op rather than re-processing a
        # player who is already gone.
        unbind_sid(request.sid)
        sio_leave(code)

        # Acknowledge to the quitter so their client can navigate home.
        emit("quit_ok")

        if not room.any_connected():
            return   # empty room; the manager's reaper will clean it up

        # Everyone else re-syncs their roster / scoreboard...
        emit(
            "player_list",
            {"players": room.public_players(), "host_id": room.host_id},
            to=code,
        )
        # ...and, if a game was in progress, the current public game state
        # (updated turn order, or a round/game end triggered by the removal).
        if in_game:
            presenter.refresh(room)

    @socketio.on("update_settings")
    def on_update_settings(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can change the settings.")
        if room.state != STATE_LOBBY:
            return error("Settings can only be changed in the lobby.")

        room.settings = _clean_settings(data.get("settings"), registry.get(room.game_type))
        emit("settings_updated", {"settings": room.settings}, to=code)

    @socketio.on("change_table_theme")
    def on_change_table_theme(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        theme = data.get("theme", "casino")
        room = manager.get_room(code)
        if room is None:
            return error("This room no longer exists.")
        if not room.is_host(user_id):
            return error("Only the host can change the table theme.")

        room.table_theme = theme
        emit("table_theme_updated", {"theme": theme}, to=code)

