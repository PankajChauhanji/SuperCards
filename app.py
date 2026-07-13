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
from game.core.manager import RoomManager
from sockets import register_handlers

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins=config.CORS_ORIGINS)

manager = RoomManager()
register_handlers(socketio, manager)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/room/<code>")
def room(code):
    code = code.strip().upper()
    if manager.get_room(code) is None:
        return redirect(url_for("index"))
    return render_template("game.html", code=code)


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=config.PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False,   # reloader spawns a child process which breaks
                              # the single-worker eventlet model and background tasks
        log_output=True,
    )
