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

import os
import time
import uuid

from flask import Flask, render_template, redirect, url_for, send_from_directory, jsonify, abort
from flask_socketio import SocketIO

import config
from game.core import registry
from game.core.manager import RoomManager
from sockets import register_handlers

# Identifies this process. Two consecutive /healthz calls returning different
# boot_ids means more than one process is serving — the split-room failure the
# single-worker rule exists to prevent. Cheaper than reading it off symptoms.
BOOT_ID = uuid.uuid4().hex[:12]
BOOT_TS = time.time()

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins=config.CORS_ORIGINS)

# restore=True picks up rooms left by a previous process (same code only — see
# game/core/store.py), so a crash or idle restart does not end live games.
manager = RoomManager(restore=True)
register_handlers(socketio, manager)


@app.route("/")
def index():
    # The landing-page picker is driven entirely by the registry, including
    # readiness — see GameSpec.ready. Nothing here needs editing to add a game.
    games = [
        {"key": spec.key, "display_name": spec.display_name, "ready": spec.ready}
        for spec in registry.all_games().values()
    ]
    return render_template("index.html", games=games)


# ── PWA routes ───────────────────────────────────────────────────────
# The service worker must be served from "/" so its scope covers the
# entire site.  The manifest needs a clean root-level URL too.

@app.route("/sw.js")
def service_worker():
    return send_from_directory(
        app.static_folder, "sw.js",
        mimetype="application/javascript",
        max_age=0,   # never cache the SW itself — browser manages updates
    )


@app.route("/manifest.json")
def manifest():
    return send_from_directory(
        app.static_folder, "manifest.json",
        mimetype="application/manifest+json",
    )


@app.route("/.well-known/assetlinks.json")
def assetlinks():
    """Digital Asset Links — ties the Android TWA package to this domain.

    Chrome fetches this when the installed app launches; a match is what lets it
    drop the URL bar and render full-screen. 404s while unconfigured rather than
    serving a half-filled file, since a malformed link fails verification in a
    way that is harder to diagnose than a missing one.
    """
    if not config.TWA_PACKAGE_NAME or not config.TWA_SHA256_FINGERPRINT:
        abort(404)
    return jsonify([
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": config.TWA_PACKAGE_NAME,
                "sha256_cert_fingerprints": [config.TWA_SHA256_FINGERPRINT],
            },
        }
    ])


@app.route("/healthz")
def healthz():
    """Liveness + a way to *detect* a split-brain instead of diagnosing one.

    Deliberately exposes counts only — never room codes. A code is the sole
    credential needed to walk into someone's game, so listing them here would
    turn a health check into a lobby-crasher.
    """
    rooms = manager.rooms
    by_game = {}
    connected = 0
    for game_room in rooms.values():
        key = getattr(game_room, "game_type", "unknown")
        by_game[key] = by_game.get(key, 0) + 1
        connected += sum(1 for p in game_room.players.values() if p.connected)
    return jsonify({
        "ok": True,
        "boot_id": BOOT_ID,          # differs per process — compare across calls
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - BOOT_TS),
        "rooms": len(rooms),
        "rooms_by_game": by_game,
        "players_connected": connected,
        "games_registered": sorted(registry.all_games()),
    })


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


def _install_shutdown_snapshot():
    """Snapshot rooms on SIGTERM/SIGINT — the signal a deploy or restart sends.

    Also snapshots periodically, because a hard kill (SIGKILL, OOM, a yanked
    container) never runs a handler. The periodic write is cheap: it only fires
    while rooms actually exist.
    """
    import signal

    def on_signal(signum, _frame):
        saved = manager.snapshot()
        print("shutting down on signal %d — rooms snapshotted: %s"
              % (signum, saved), flush=True)
        raise SystemExit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_signal)
        except (ValueError, OSError):
            pass  # not the main thread / unsupported platform: periodic save covers it

    def periodic():
        while True:
            socketio.sleep(20)
            try:
                if manager.rooms:
                    manager.snapshot()
            except Exception:
                pass  # persistence must never take the server down
    socketio.start_background_task(periodic)


if __name__ == "__main__":
    if _port_already_serving(config.PORT):
        raise SystemExit(
            f"ERROR: something is already serving port {config.PORT} — a second "
            "instance would split players across processes and break rooms.\n"
            f"Find it with:  ss -ltnp | grep :{config.PORT}   and stop it, or "
            "start this server on another port:  PORT=5001 python3 app.py"
        )
    _install_shutdown_snapshot()
    socketio.run(
        app,
        host="0.0.0.0",
        port=config.PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False,   # reloader spawns a child process which breaks
                              # the single-worker eventlet model and background tasks
        log_output=True,
    )
