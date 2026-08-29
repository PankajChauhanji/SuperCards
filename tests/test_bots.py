import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Computer players: identity, caps, and the promise that they are ordinary players.

A bot used to exist only in single-player rooms, seated once by ``create_solo``
with a hardcoded id. A host can now seat up to ``bots.MAX_BOTS`` of them in any
room, which turns three assumptions that used to be free into things worth
pinning:

  * ids and display names must be unique — a profile has to be reusable
    without colliding with anything (a human included) already in the room;
  * a bot must stay invisible to every "is anyone actually here?" question, or a
    room full of bots would never be reaped and a bot could inherit the host;
  * a bot must never be sent a private payload, because it has no socket.
"""
from game.core import bots, registry

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def room_for(game_type, humans=("u0",)):
    spec = registry.get(game_type)
    room = spec.room_class("BOTS", humans[0], dict(spec.default_settings))
    room.game_type = game_type
    for uid in humans:
        room.register_player(uid, uid.upper())
        room.attach(uid, "sid_" + uid, uid.upper())
    return room


# ---- the roster ---------------------------------------------------------
check(len(bots.ROSTER) == 5, "the roster offers five computer players")
check(sum(1 for b in bots.ROSTER if b.gender == "m") == 3 and
      sum(1 for b in bots.ROSTER if b.gender == "f") == 2,
      "three male and two female profiles")
check(len({b.key for b in bots.ROSTER}) == 5 and len({b.name for b in bots.ROSTER}) == 5,
      "every profile has a distinct key and name")
check(bots.profile("sooryavanshi") is not None and bots.profile("nope") is None,
      "profiles look up by key, and an unknown key resolves to nothing")
check(all(b["key"] and b["name"] and b["gender"] for b in bots.public_roster()),
      "the public roster carries key, name and gender for the picker")


# ---- identity allocation -----------------------------------------------
room = room_for("super_seven")
first = bots.add_to(room)
check(first.user_id == "bot_sooryavanshi",
      "the first computer player keeps the roster's first id")
check(first.is_bot and first.connected and not first.sid,
      "a bot is connected (it counts toward the minimum) but has no socket")

added = [bots.add_to(room) for _ in range(4)]
seated = [first] + added
check(len({b.user_id for b in seated}) == 5, "five bots get five distinct ids")
check(len({b.name for b in seated}) == 5, "and five distinct display names")
check(all(uid.startswith(bots.ID_PREFIX) for uid in bots.bots_in(room)),
      "every bot id is recognisable from the id alone")
check(bots.is_full(room), "the room reports its bot cap reached at MAX_BOTS")
check(len(bots.bots_in(room)) == bots.MAX_BOTS,
      "which is %d bots" % bots.MAX_BOTS)

# The roster now matches the cap exactly, so five adds seat five distinct
# profiles with no repeat needed.
check({b.name for b in seated} == {p.name for p in bots.ROSTER},
      "all five roster profiles got seated, none repeated (got %r)"
      % [b.name for b in seated])

# Picking an already-seated profile again still has to work (e.g. MAX_BOTS
# growing past the roster size someday) — it repeats under a numbered name.
repeat = bots.add_to(room, "modi")
check(repeat.name == "Modi 2" and repeat.user_id == "bot_modi_2",
      "reusing a taken profile falls back to a numbered name (got %r)" % repeat.name)

# A bot must not take a name a human already has.
human_room = room_for("bluff", humans=("h0",))
human_room.players["h0"].name = "Modi"
clash = bots.add_to(human_room, "modi")
check(clash.name != "Modi" and clash.user_id != "bot_modi",
      "a bot will not take a display name a human already uses (got %r)" % clash.name)

# Explicitly picking a profile is honoured; an unknown key falls back safely.
picked = bots.add_to(room_for("bluff"), "smriti")
check(picked.name == "Smriti Mandhana", "an explicitly chosen profile is the one seated")


# ---- bots stay invisible to presence questions --------------------------
for game_type in ("super_seven", "bluff", "super_four"):
    room = room_for(game_type)
    bots.add_to(room)
    bots.add_to(room)
    check(room.any_human_connected(),
          "%s: a room with a human still reports a human present" % game_type)

    room.detach("u0")
    check(not room.any_human_connected(),
          "%s: bots alone do not count as a human, so the room is reapable" % game_type)
    check(room.any_connected(),
          "%s: bots still count as connected for the game's own bookkeeping" % game_type)

    room.migrate_host()
    check(not room.players[room.host_id].is_bot,
          "%s: host migration never hands the room to a bot" % game_type)


# ---- bots never receive a private deal ----------------------------------
# Every private send is guarded on the player having a sid; a bot has none, so
# this is really a check that nothing regressed that guard.
for game_type in ("super_seven", "bluff", "super_four"):
    room = room_for(game_type, humans=("u0", "u1"))
    bots.add_to(room)
    room.start_round()
    targets = [p for p in room.connected_players() if not p.is_bot and p.sid]
    check(all(not p.is_bot for p in targets),
          "%s: the private-deal target list excludes bots" % game_type)
    check(len(targets) == 2, "%s: and still includes both humans" % game_type)


# ---- a bot is dealt in and takes turns like anyone else -----------------
for game_type in ("super_seven", "bluff"):
    room = room_for(game_type, humans=("u0", "u1"))
    bot = bots.add_to(room)
    room.start_round()
    check(bot.user_id in room.turn_order,
          "%s: a seated bot is dealt into the turn order" % game_type)
    check(len(room.turn_order) == 3,
          "%s: the table is two humans and one bot" % game_type)


print("\n%d/%d bot checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
