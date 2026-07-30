"""Light social handlers — currently just in-game emoji reactions.

The server only relays a whitelisted emoji to everyone at the table; the float
animation lives entirely on the client. Whitelisting keeps the channel from
being used to broadcast arbitrary text.
"""
import time
from flask_socketio import emit

ALLOWED_REACTIONS = {
    "😂", "😲", "🤯", "😭", "😡", "🔥", "⚡", "👏", "😎", "🎉",
    "🤡", "💀", "🤫", "🥱", "💩", "👶", "🍿", "🐔", "🦖", "🤦",
    "🤥", "🐌", "🤏", "🚮", "👎"
}


def register(socketio, manager):

    @socketio.on("reaction")
    def on_reaction(data):
        data = data or {}
        code = (data.get("code") or "").strip().upper()
        user_id = data.get("user_id")
        emoji = data.get("emoji")
        room = manager.get_room(code)
        if room is None or user_id not in room.players:
            return
        if emoji not in ALLOWED_REACTIONS:
            return
            
        player = room.players[user_id]
        now = time.time()
        
        # Token bucket rate limiting: max 10 tokens, refills at 10 tokens / 3 seconds
        capacity = 10.0
        fill_rate = 10.0 / 3.0
        
        last_time = getattr(player, '_reaction_last_time', now)
        tokens = getattr(player, '_reaction_tokens', capacity)
        
        # Refill tokens based on elapsed time
        elapsed = now - last_time
        tokens = min(capacity, tokens + elapsed * fill_rate)
        
        if tokens < 1.0:
            return
            
        player._reaction_last_time = now
        player._reaction_tokens = tokens - 1.0
            
        emit(
            "reaction",
            {"user_id": user_id, "name": player.name, "emoji": emoji},
            to=code,
        )
