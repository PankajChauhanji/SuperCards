"""Room snapshots, so a restart stops destroying live games.

Today every room lives only in memory, so any restart — a crash, an idle
spin-down on the free tier, a deploy — silently ends every game in progress.
Players see it as the app breaking. Clients already re-emit ``enter_room`` on
reconnect (static/js/core/connection.js), so if the rooms survive, recovery is
close to invisible.

Design, and the one real tradeoff
---------------------------------
Snapshots are **pickled** rather than hand-serialized. Rooms are pure state
machines with no I/O, so pickle captures them with full fidelity — including
Super 4's per-viewer ``known`` sets and its live ``MatchWindow`` — and, crucially,
without a per-game ``to_dict``/``from_dict`` pair that every future field would
have to be remembered in. That kind of duplication is exactly the drift this
codebase keeps getting bitten by.

Pickle's weakness is version skew: unpickling old state into changed code can
produce a half-built object that looks fine and behaves wrongly. That weakness
lands precisely on the deploy case, which is when a restart is most likely. So
the snapshot is gated on a **fingerprint of the game/socket source**. Same code
(crash, restart, spin-down) → restore. Changed code (deploy) → the snapshot is
discarded and logged, and players start fresh, which is the honest outcome
rather than a subtly corrupt table.

Timers are absolute ``time.time()`` values, so a naive restore would instantly
time out whoever was on turn. Every timestamp is therefore shifted forward by
the downtime, preserving *remaining* time rather than wall-clock.

Failure is never fatal: every entry point swallows its own errors. Losing a
snapshot costs the rooms; letting a snapshot bug reach the game loop would cost
the app.
"""
import hashlib
import os
import pickle
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ephemeral by nature. On Render this survives a process restart within an
# instance but not a redeploy (the filesystem is wiped) — and a redeploy would
# fail the fingerprint check anyway, so nothing is lost by that.
SNAPSHOT_PATH = os.environ.get(
    "ROOM_SNAPSHOT_PATH", os.path.join(REPO, ".room_snapshot")
)
ENABLED = os.environ.get("ROOM_PERSIST", "1") != "0"

# Source trees whose contents define "same code" for snapshot compatibility.
_FINGERPRINT_ROOTS = ("game", "sockets")

_fingerprint_cache = None


def _log(message: str) -> None:
    print("ROOM-STORE: " + message, file=sys.stderr, flush=True)


def fingerprint() -> str:
    """Hash of the game/socket source — the compatibility gate for a snapshot."""
    global _fingerprint_cache
    if _fingerprint_cache is not None:
        return _fingerprint_cache
    digest = hashlib.sha256()
    for root in _FINGERPRINT_ROOTS:
        base = os.path.join(REPO, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                digest.update(os.path.relpath(path, REPO).encode())
                try:
                    with open(path, "rb") as fh:
                        digest.update(fh.read())
                except OSError:
                    digest.update(b"<unreadable>")
    _fingerprint_cache = digest.hexdigest()[:16]
    return _fingerprint_cache


# ── timestamp rebasing ───────────────────────────────────────────────────

# Absolute-time attributes are named consistently across the three games
# (``*_ts``, ``*_deadline``, ``created_at``), so they can be found generically
# instead of each game maintaining its own list that a new field would miss.
_TIME_SUFFIXES = ("_ts", "_deadline", "_at", "deadline")
# A plausible epoch-seconds value. Guards against shifting a float that merely
# happens to sit on a matching attribute name.
_MIN_EPOCH = 1_000_000_000


def _looks_like_timestamp(name: str, value) -> bool:
    if not isinstance(value, float) and not isinstance(value, int):
        return False
    if isinstance(value, bool):
        return False
    if value < _MIN_EPOCH:
        return False
    return any(name.endswith(suffix) for suffix in _TIME_SUFFIXES)


def _rebase(obj, delta: float, depth: int = 0) -> int:
    """Shift every timestamp attribute on obj forward by delta. Returns count."""
    if depth > 2 or obj is None:
        return 0
    shifted = 0
    holder = getattr(obj, "__dict__", None)
    if not isinstance(holder, dict):
        return 0
    for name, value in list(holder.items()):
        if _looks_like_timestamp(name, value):
            holder[name] = value + delta
            shifted += 1
        elif hasattr(value, "__dict__") and not isinstance(value, type):
            # e.g. Super 4's live MatchWindow, which carries its own deadline.
            shifted += _rebase(value, delta, depth + 1)
    return shifted


# ── save / load ──────────────────────────────────────────────────────────

def save(rooms: dict) -> bool:
    """Write a snapshot of the rooms dict. Returns True if one was written."""
    if not ENABLED:
        return False
    try:
        if not rooms:
            # Nothing to keep: drop any stale file so a later boot cannot
            # resurrect rooms that have already been abandoned.
            if os.path.exists(SNAPSHOT_PATH):
                os.remove(SNAPSHOT_PATH)
            return False
        blob = {
            "fingerprint": fingerprint(),
            "saved_at": time.time(),
            "rooms": rooms,
        }
        tmp = SNAPSHOT_PATH + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(blob, fh, protocol=pickle.HIGHEST_PROTOCOL)
            fh.flush()
            os.fsync(fh.fileno())
        # Atomic replace: a crash mid-write must not leave a torn snapshot that
        # the next boot would try to load.
        os.replace(tmp, SNAPSHOT_PATH)
        return True
    except Exception as exc:                      # never let this break shutdown
        _log("save failed (%s: %s)" % (type(exc).__name__, exc))
        return False


def load() -> dict:
    """Restore rooms from a snapshot, or return {} if there is nothing usable."""
    if not ENABLED or not os.path.exists(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "rb") as fh:
            blob = pickle.load(fh)
    except Exception as exc:
        _log("snapshot unreadable, ignoring (%s: %s)" % (type(exc).__name__, exc))
        _discard()
        return {}

    if blob.get("fingerprint") != fingerprint():
        # Almost certainly a deploy. Restoring old state into new code is how
        # you get a table that looks right and plays wrong.
        _log("snapshot is from different code (deploy?) — starting fresh")
        _discard()
        return {}

    rooms = blob.get("rooms") or {}
    delta = max(0.0, time.time() - float(blob.get("saved_at") or 0))
    restored = {}
    for code, room in rooms.items():
        try:
            _revive(room, delta)
            restored[code] = room
        except Exception as exc:
            _log("dropping room %s (%s: %s)" % (code, type(exc).__name__, exc))

    _discard()   # one-shot: a snapshot must never be replayed twice
    if restored:
        _log("restored %d room(s) after %.0fs downtime" % (len(restored), delta))
    return restored


def _revive(room, delta: float) -> None:
    """Make a deserialized room safe to serve: dead sockets out, clocks forward."""
    # Every sid belonged to a socket that died with the old process. Leaving them
    # would emit private payloads into the void and, worse, let the room believe
    # players are still connected (so it would not migrate the host or reap).
    for player in room.players.values():
        player.sid = ""
        player.connected = False
    _rebase(room, delta)
    # Reconnect grace. Because nobody is marked connected yet, RoomManager's
    # reaper considers this room abandoned, and it reaps anything older than
    # EMPTY_ROOM_TTL on the next create_room. A restored room that happened to
    # be more than a minute old would therefore be deleted moments after boot —
    # destroying exactly the live game this snapshot exists to save. Restarting
    # the clock gives the players a full TTL window to come back. created_at
    # feeds nothing but that reaper, so nothing else shifts.
    room.created_at = time.time()


def _discard() -> None:
    try:
        if os.path.exists(SNAPSHOT_PATH):
            os.remove(SNAPSHOT_PATH)
    except OSError:
        pass
