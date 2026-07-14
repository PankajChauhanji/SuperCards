"""The turn-timer director — the only background routine in the app.

Once a second it scans active rooms and hands each one to the per-game ticker
registered for its game_type. The scan loop itself is game-agnostic; all
game-specific timeout / auto-play / bot logic lives in the variant's socket
module, which registers a ticker via `register_ticker` (Super Seven does this in
sockets/gameplay/super_seven.py).

Run as an eventlet background task started in app.py.
"""
from game.core.states import STATE_IN_TURN

# game_type -> tick(socketio, room) callable, provided by each variant.
_TICKERS: dict = {}


def register_ticker(game_type: str, fn) -> None:
    """Register a per-game per-room tick handler. Called by variant modules."""
    _TICKERS[game_type] = fn


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
    for _code, room in list(manager.rooms.items()):
        if room.state != STATE_IN_TURN:
            continue
        ticker = _TICKERS.get(room.game_type)
        if ticker is None:
            continue
        ticker(socketio, room)
