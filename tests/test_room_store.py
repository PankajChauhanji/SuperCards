import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Snapshots must restore a game faithfully, or they are worse than nothing.

A restart that resurrects a *subtly wrong* table is worse than one that drops
the room: players keep playing and the game misbehaves. So these checks care
about fidelity, not just that a file round-trips — hands, slots, turn order and
Super 4's per-viewer knowledge sets all have to come back intact, dead sockets
have to be cleared, and clocks have to be rebased so nobody is instantly timed
out by the downtime.
"""
import time

from game.core import registry, store
from game.core.manager import RoomManager
from game.core.states import STATE_IN_TURN

results = []


def check(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


# Keep the real snapshot file out of this: tests must not clobber a dev server's.
store.SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".room_snapshot_test"
)
store.ENABLED = True


def cleanup():
    for path in (store.SNAPSHOT_PATH, store.SNAPSHOT_PATH + ".tmp"):
        if os.path.exists(path):
            os.remove(path)


cleanup()


def seed_manager():
    """A manager holding one live room of each game, mid-play."""
    mgr = RoomManager()
    for game_type in ("super_seven", "super_four", "bluff"):
        # Real rooms are created with the game's defaults (the lobby fills them
        # in); an empty dict would leave timer settings missing.
        settings = dict(registry.get(game_type).default_settings)
        room = mgr.create_room("h_%s" % game_type, "Host", settings, game_type=game_type)
        room.players["h_%s" % game_type].connected = True
        for i in range(2):
            uid = "%s_p%d" % (game_type, i)
            player = room.register_player(uid, "P%d" % i)
            player.connected = True
            player.sid = "sid-%s" % uid
        room.start_round()
    return mgr


# ── round trip fidelity ──────────────────────────────────────────────────
mgr = seed_manager()
before = {}
for code, room in mgr.rooms.items():
    before[code] = {
        "game_type": room.game_type,
        "state": room.state,
        "turn_order": list(room.turn_order),
        "current_turn": room.current_turn_id(),
        "host_id": room.host_id,
        "hands": {u: [c.id for c in p.hand] for u, p in room.players.items()},
        "slots": (
            {u: [c.id if c else None for c in cards]
             for u, cards in room.slots.items()}
            if hasattr(room, "slots") else None
        ),
        "known": (
            {u: sorted(v) for u, v in room.known.items()}
            if hasattr(room, "known") else None
        ),
    }

check(mgr.snapshot(), "snapshot writes a file when rooms exist")
check(os.path.exists(store.SNAPSHOT_PATH), "the snapshot file is on disk")

restored = RoomManager(restore=True)
check(sorted(restored.rooms) == sorted(mgr.rooms),
      "every room code comes back (%d rooms)" % len(mgr.rooms))

for code, expected in before.items():
    room = restored.rooms.get(code)
    tag = "[%s]" % expected["game_type"]
    if room is None:
        check(False, "%s room %s came back" % (tag, code))
        continue
    check(room.game_type == expected["game_type"], "%s game_type survives" % tag)
    check(room.state == expected["state"] == STATE_IN_TURN,
          "%s room is still mid-play after restore" % tag)
    check(list(room.turn_order) == expected["turn_order"], "%s turn order survives" % tag)
    check(room.current_turn_id() == expected["current_turn"],
          "%s it is still the same player's turn" % tag)
    check(room.host_id == expected["host_id"], "%s host survives" % tag)

    hands = {u: [c.id for c in p.hand] for u, p in room.players.items()}
    check(hands == expected["hands"], "%s every hand is byte-for-byte identical" % tag)

    if expected["slots"] is not None:
        slots = {u: [c.id if c else None for c in cards]
                 for u, cards in room.slots.items()}
        check(slots == expected["slots"], "%s all four slots per player survive" % tag)
    if expected["known"] is not None:
        known = {u: sorted(v) for u, v in room.known.items()}
        check(known == expected["known"],
              "%s per-viewer knowledge sets survive (no memory reset, no leak)" % tag)

    # Sockets died with the old process.
    check(all(p.sid == "" for p in room.players.values()),
          "%s stale socket ids are cleared" % tag)
    check(not any(p.connected for p in room.players.values()),
          "%s nobody is left marked connected" % tag)

check(not os.path.exists(store.SNAPSHOT_PATH),
      "the snapshot is consumed on load (never replayed twice)")

# ── clocks are rebased, so downtime does not eat someone's turn ───────────
# Unit-level first, so the arithmetic is pinned exactly rather than within a
# tolerance: every timestamp attribute moves forward by the downtime, and
# nothing else is touched.
mgr = seed_manager()
room = [r for r in mgr.rooms.values() if r.game_type == "super_seven"][0]
ts_before, created_before = room.turn_start_ts, room.created_at
order_before = list(room.turn_order)
shifted = store._rebase(room, 100.0)
check(shifted >= 2, "rebase finds the room's timestamp fields (%d shifted)" % shifted)
check(room.turn_start_ts == ts_before + 100.0, "turn_start_ts moves by exactly the gap")
check(room.created_at == created_before + 100.0, "created_at moves with the gap")
check(list(room.turn_order) == order_before, "rebase leaves non-time state alone")

s4 = [r for r in mgr.rooms.values() if r.game_type == "super_four"][0]
pd_before = s4.preview_deadline
store._rebase(s4, 100.0)
check(s4.preview_deadline == pd_before + 100.0,
      "Super 4's preview deadline is rebased as well")

# Then end-to-end over a real gap: without rebasing, the remaining turn time
# would visibly decay while the process was down.
mgr = seed_manager()
room = [r for r in mgr.rooms.values() if r.game_type == "super_seven"][0]
code = room.code
left_before = room.turn_seconds_left()
mgr.snapshot()
time.sleep(3)
restored = RoomManager(restore=True)
room2 = restored.rooms[code]
left_after = room2.turn_seconds_left()
check(left_after is not None and abs(left_after - left_before) <= 1,
      "a real 3s outage does not consume the active player's turn timer "
      "(%ss before, %ss after)" % (left_before, left_after))
check(not room2.is_timed_out(),
      "the player on turn is not instantly timed out by the downtime")

# ── a restored room must not be reaped before players can reconnect ───────
# Nobody is marked connected right after a restore, so the reaper sees every
# restored room as abandoned. An old room would be deleted on the next
# create_room — killing the very game the snapshot saved.
import config

mgr = seed_manager()
old = [r for r in mgr.rooms.values() if r.game_type == "super_seven"][0]
old_code = old.code
old.created_at = time.time() - (config.EMPTY_ROOM_TTL + 600)   # a 10-minute-old game
mgr.snapshot()

restored = RoomManager(restore=True)
check(old_code in restored.rooms, "the long-lived room is restored at all")
age = time.time() - restored.rooms[old_code].created_at
check(age < config.EMPTY_ROOM_TTL,
      "a restored room gets a fresh reconnect window (age %.0fs < TTL %ds)"
      % (age, config.EMPTY_ROOM_TTL))
# The reaper runs on create_room; that must not sweep the restored game away.
restored.create_room("someone-else", "Other", dict(
    registry.get("super_seven").default_settings), game_type="super_seven")
check(old_code in restored.rooms,
      "creating an unrelated room does not reap the restored game")

# ── a code change must invalidate the snapshot, not corrupt a table ───────
mgr = seed_manager()
mgr.snapshot()
real = store.fingerprint()
store._fingerprint_cache = "deadbeefdeadbeef"      # simulate a deploy
after_deploy = RoomManager(restore=True)
store._fingerprint_cache = real
check(after_deploy.rooms == {},
      "a snapshot from different code is refused (deploy starts fresh)")
check(not os.path.exists(store.SNAPSHOT_PATH),
      "the incompatible snapshot is deleted rather than retried forever")

# ── robustness: nothing here may ever raise into the game loop ───────────
with open(store.SNAPSHOT_PATH, "wb") as fh:
    fh.write(b"this is not a pickle")
try:
    junk = RoomManager(restore=True)
    check(junk.rooms == {}, "a corrupt snapshot loads as empty instead of crashing")
except Exception as exc:
    check(False, "a corrupt snapshot raised %r" % exc)

empty = RoomManager()
check(empty.snapshot() is False, "an empty manager writes no snapshot")
check(not os.path.exists(store.SNAPSHOT_PATH),
      "snapshotting zero rooms clears any stale file")

store.ENABLED = False
mgr = seed_manager()
check(mgr.snapshot() is False, "ROOM_PERSIST=0 disables snapshotting entirely")
check(RoomManager(restore=True).rooms == {}, "and disables restoring too")
store.ENABLED = True

cleanup()
print("\n%d/%d room-store checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
