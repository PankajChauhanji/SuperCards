"""Socket handler registration.

Each concern lives in its own module (connection / lobby / ... gameplay later)
so the event contract stays easy to audit. `register_handlers` wires them all
to the SocketIO instance against a shared RoomManager.
"""
from sockets import audience, connection, lobby, gameplay, director, social, sync, seat_guard


def register_handlers(socketio, manager):
    # Install first: it wraps socketio.emit, so it must be in place before any
    # module captures a reference to it.
    audience.install(socketio, manager)
    # Also before any handler registers: it wraps socketio.on, so every handler
    # registered below checks that the caller is the player it claims to be.
    seat_guard.install(socketio)
    connection.register(socketio, manager)
    # State reconciliation heartbeat — see sockets/sync.py.
    sync.register(socketio, manager)
    lobby.register(socketio, manager)
    gameplay.register(socketio, manager)
    director.register(socketio, manager)
    social.register(socketio, manager)
