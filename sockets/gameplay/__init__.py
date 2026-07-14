"""Gameplay handler registration, dispatched per game variant.

Each variant ships its own module here (super_seven, later super_four) that
registers its socket event handlers and its director ticker. Handlers guard on
room.game_type so an event for the wrong game is rejected rather than misapplied,
even though the variants' event names generally differ.
"""
from sockets.gameplay import super_seven, super_four


def register(socketio, manager):
    super_seven.register(socketio, manager)
    super_four.register(socketio, manager)
