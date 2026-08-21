"""Socket handler registration.

Each concern lives in its own module (connection / lobby / ... gameplay later)
so the event contract stays easy to audit. `register_handlers` wires them all
to the SocketIO instance against a shared RoomManager.
"""
from sockets import audience, connection, lobby, gameplay, director, social


def register_handlers(socketio, manager):
    # Install first: it wraps socketio.emit, so it must be in place before any
    # module captures a reference to it.
    audience.install(socketio, manager)
    connection.register(socketio, manager)
    lobby.register(socketio, manager)
    gameplay.register(socketio, manager)
    director.register(socketio, manager)
    social.register(socketio, manager)

# Minor: recorded a non-functional comment for commit grouping.
