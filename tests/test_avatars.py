import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Player avatars (game/core/avatars.py) and the invite redirect.

An avatar is a motif name chosen on the player's device and echoed to the whole
room, so the property that matters most is that the server only ever stores a
name from its own list — anything else becomes "" (show the initial). The rest
pins the three places that must agree: the server's list, the home page's list,
and the icon set that draws them.
"""
os.environ.setdefault("LEAK_GUARD", "raise")

import re

from game.core import avatars, bots, registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


# ---- the list and its sanitiser ----
check(len(avatars.MOTIFS) == len(set(avatars.MOTIFS)) == 16, "16 distinct motifs")
check(all(avatars.clean(m) == m for m in avatars.MOTIFS), "every motif survives clean()")
for bad in ["", None, 3, "Crown", "crown ", "<svg onload=x>", "i-crown", "x" * 500, ["crown"], {"m": 1}]:
    check(avatars.clean(bad) == "", "clean() rejects %r" % (bad if not isinstance(bad, str) or len(bad) < 20 else bad[:12] + "…"))

icons = open(os.path.join(ROOT, "templates/partials/icons.html"), encoding="utf-8").read()
symbols = set(re.findall(r'<symbol id="i-([\w-]+)"', icons))
check(all(m in symbols for m in avatars.MOTIFS),
      "every motif has a symbol in partials/icons.html (missing: %s)" % [m for m in avatars.MOTIFS if m not in symbols])

icons_js = open(os.path.join(ROOT, "static/js/core/icons.js"), encoding="utf-8").read()
block = icons_js.split("SS.AVATARS = [", 1)[1].split("];", 1)[0]
check(tuple(re.findall(r'"([a-z]+)"', block)) == avatars.MOTIFS,
      "the client's avatar list (SS.AVATARS) is exactly the server's motifs, in order")

# ---- bots ----
check(all(avatars.clean(p.avatar) == p.avatar and p.avatar for p in bots.ROSTER),
      "every computer player has a valid avatar")
check(all("avatar" in row for row in bots.public_roster()), "the lobby's bot roster carries avatars")

# ---- every game's public roster carries it ----
for game_type in ("super_seven", "super_four", "bluff", "poker"):
    spec = registry.get(game_type)
    room = spec.room_class("AVTR", "p0", dict(spec.default_settings))
    room.register_player("p0", "Asha").avatar = "moon"
    room.register_player("p1", "Ben")
    rows = {r["user_id"]: r for r in room.public_players()}
    check(rows["p0"].get("avatar") == "moon" and rows["p1"].get("avatar") == "",
          "[%s] public_players() carries each player's avatar" % game_type)

# ---- over sockets: only a known motif is ever stored and broadcast ----
from flask import Flask
from flask_socketio import SocketIO
from game.core.manager import RoomManager
from sockets import register_handlers

app = Flask(__name__)
sio = SocketIO(app, async_mode="threading")
manager = RoomManager(restore=False)
register_handlers(sio, manager)


def received(client, name=None):
    return [e for e in client.get_received() if name is None or e["name"] == name]


host, guest, stranger = (sio.test_client(app) for _ in range(3))
host.emit("create_room", {"name": "Host", "user_id": "h1", "game_type": "super_seven", "avatar": "crown"})
code = received(host, "room_created")[0]["args"][0]["code"]
guest.emit("join_room", {"code": code, "name": "Guest", "user_id": "g1", "avatar": "<img src=x onerror=alert(1)>"})
room = manager.get_room(code)
check(room.players["h1"].avatar == "crown", "create_room stores the host's avatar")
check(room.players["g1"].avatar == "", "join_room turns an unknown avatar into the initial")

host.emit("enter_room", {"code": code, "name": "Host", "user_id": "h1", "avatar": "gem"})
roster = received(host, "player_list")[-1]["args"][0]["players"]
check({p["user_id"]: p["avatar"] for p in roster} == {"h1": "gem", "g1": ""},
      "enter_room updates the avatar and the roster broadcast carries it")

host.emit("add_bot", {"code": code, "user_id": "h1"})
bot = next(p for p in room.players.values() if p.is_bot)
check(bot.avatar in avatars.MOTIFS, "a seated bot gets its profile's avatar (%r)" % bot.avatar)

# A shared /room/<code> link opened by someone who never joined: the error
# carries a reason the page uses to send them to the join screen.
stranger.emit("enter_room", {"code": code, "name": "Who", "user_id": "s1"})
errs = [e["args"][0] for e in received(stranger, "error")]
check(errs and errs[0].get("reason") == "not_in_room",
      "entering a room you have not joined says why (reason=not_in_room)")

for c in (host, guest, stranger):
    if c.is_connected():
        c.disconnect()

print("\n%d/%d avatar checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
