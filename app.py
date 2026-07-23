"""Super Seven — application entrypoint.

eventlet is monkey-patched first (before any stdlib networking import) so the
single eventlet worker can run cooperative sockets and the turn-timer director
background task. All room state lives in one in-memory RoomManager, which is
why production must run exactly one worker.

Deployment: use `python3 app.py` (not gunicorn) so eventlet's own server
handles the process — this guarantees start_background_task() works correctly.
"""
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, url_for
from flask_socketio import SocketIO

import config
from game.core import registry
from game.core.manager import RoomManager
from sockets import register_handlers

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins=config.CORS_ORIGINS)

manager = RoomManager()
register_handlers(socketio, manager)


@app.route("/")
def index():
    # The landing-page picker is driven by the registry. A game is selectable
    # only once its frontend bundle exists; others render as disabled "coming
    # soon" tiles. (Super 4's backend is registered before its UI is built.)
    ready = {"super_seven", "super_four", "bluff"}
    games = [
        {"key": spec.key, "display_name": spec.display_name, "ready": spec.key in ready}
        for spec in registry.all_games().values()
    ]
    return render_template("index.html", games=games)


@app.route("/room/<code>")
def room(code):
    code = code.strip().upper()
    game_room = manager.get_room(code)
    if game_room is None:
        return redirect(url_for("index"))
    # game_type + display_name let the game page bootstrap the correct variant
    # bundle and branding (Phase 2).
    spec = registry.get(game_room.game_type)
    return render_template(
        "game.html",
        code=code,
        game_type=game_room.game_type,
        display_name=spec.display_name if spec else game_room.game_type,
    )


def _port_already_serving(port: int) -> bool:
    """True if some process already accepts connections on the port.

    eventlet's listener can share a port with an existing server instead of
    failing, which silently splits clients between two processes — each with
    its own in-memory rooms ("Invalid session" spam, "room not exists" for
    other players). Refuse to start into that trap.
    """
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    if _port_already_serving(config.PORT):
        raise SystemExit(
            f"ERROR: something is already serving port {config.PORT} — a second "
            "instance would split players across processes and break rooms.\n"
            f"Find it with:  ss -ltnp | grep :{config.PORT}   and stop it, or "
            "start this server on another port:  PORT=5001 python3 app.py"
        )
    socketio.run(
        app,
        host="0.0.0.0",
        port=config.PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False,   # reloader spawns a child process which breaks
                              # the single-worker eventlet model and background tasks
        log_output=True,
    )
