"""The turn-timer director — the only background routine in the app.

Once a second it scans active rooms and hands each one to the per-game ticker
registered for its game_type. The scan loop itself is game-agnostic; all
game-specific timeout / auto-play / bot logic lives in the variant's socket
module, which registers a ticker via `register_ticker` (Super Seven does this in
sockets/gameplay/super_seven.py).

Run as an eventlet background task started in app.py.
"""
import logging
import traceback

from game.core.states import STATE_IN_TURN

logger = logging.getLogger(__name__)

# game_type -> tick(socketio, room) callable, provided by each variant.
_TICKERS: dict = {}


def register_ticker(game_type: str, fn) -> None:
    """Register a per-game per-room tick handler. Called by variant modules."""
    _TICKERS[game_type] = fn


def bots_should_act(room) -> bool:
    """False when nobody is connected to watch — every ticker's bot branch asks.

    A host can seat up to five computer players (game/core/bots.py), so a room
    whose humans have all gone can still be a full table of bots playing to an
    empty seat. That room is already reapable (game/core/manager.py), so every
    move until then is work no one will ever see — and this process has one
    worker, so it is taken from rooms that do have people in them.

    Deliberately gates the *bot* branch only. Pausing the human turn timer as
    well would look tempting and be wrong: ``turn_start_ts`` would go stale while
    the room idled, and the first player to reconnect would be timed out on
    arrival for a turn they never got to take.
    """
    return room.any_human_connected()


def register(socketio, manager):
    def loop():
        while True:
            socketio.sleep(1)
            try:
                _tick(socketio, manager)
            except Exception:
                # A background loop must never die on a transient error.
                logger.error("director tick failed:\n%s", traceback.format_exc())

    socketio.start_background_task(loop)


def _tick(socketio, manager):
    for code, room in list(manager.rooms.items()):
        if room.state != STATE_IN_TURN:
            continue
        ticker = _TICKERS.get(room.game_type)
        if ticker is None:
            continue
        try:
            ticker(socketio, room)
        except Exception:
            # One broken room must never stall the ticker for every other room.
            logger.error("ticker failed for room %s (%s):\n%s",
                         code, room.game_type, traceback.format_exc())
