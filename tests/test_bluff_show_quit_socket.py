import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Bluff over real sockets: someone quits while a Show's cards are face up.

The engine half is tests/test_bluff_show_quit.py. This is the half players
felt: the Show handler holds the cards up for a few seconds with the room
locked (``is_showing``). A quit inside that window used to crash the handler
after the pause, so the lock was never released — every move from then on was
refused with "Cards are being revealed" and the table was dead for everyone.

Four clients: A throws, B calls Show, and the leaver (B, then — at a fresh
table — A) quits during the reveal. The table must come back: a fresh
public state, a turn on someone still racing, and that player's move accepted.

Needs a server on 5005; run_tests.py starts one with LEAK_GUARD=raise.
"""
import time

import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


class Client:
    def __init__(self, uid, name):
        self.uid, self.name = uid, name
        self.events = []
        self.times = []           # arrival time of each event
        self.state = {}
        self.hand = []
        self.cli = socketio.Client(reconnection=False)
        self.cli.on("*", self._record)
        self.cli.connect(BASE, wait_timeout=10)

    def _record(self, event, data=None):
        data = data if data is not None else {}
        self.events.append((event, data))
        self.times.append(time.time())
        if event in ("round_start", "table_state"):
            self.state = data
        elif event == "your_hand":
            self.hand = data.get("cards") or []

    def emit(self, event, payload):
        self.cli.emit(event, payload)

    def wait(self, event, timeout=8.0, since=0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev, data in self.events[since:]:
                if ev == event and (pred is None or pred(data)):
                    return data
            time.sleep(0.03)
        return None


def table(tag, leaver_role):
    cl = [Client("bsq-%s-%d" % (tag, i), n) for i, n in enumerate(["Asha", "Ben", "Chen", "Dev"])]
    host = cl[0]
    try:
        host.emit("create_room", {"name": host.name, "user_id": host.uid, "game_type": "bluff"})
        code = (host.wait("room_created") or {}).get("code")
        for c in cl[1:]:
            c.emit("join_room", {"code": code, "name": c.name, "user_id": c.uid})
            c.wait("join_ok")
        for c in cl:
            c.emit("enter_room", {"code": code, "name": c.name, "user_id": c.uid})
        host.wait("player_list", pred=lambda d: len(d.get("players", [])) == 4)
        host.emit("start_game", {"code": code, "user_id": host.uid})
        st = host.wait("round_start")
        log(st is not None, "%s: game started" % tag)
        for c in cl:
            c.wait("your_hand")
        by = {c.uid: c for c in cl}
        cur = by[st["current_turn"]]
        # The leader throws one card, honestly or not — it does not matter.
        card = cur.hand[0]
        mark = len(host.events)
        cur.emit("bluff_play", {"code": code, "user_id": cur.uid, "card_ids": [card["id"]], "declared_rank": "K"})
        st2 = host.wait("table_state", since=mark)
        nxt = by[st2["current_turn"]]
        mark = len(host.events)
        nxt.emit("bluff_show", {"code": code, "user_id": nxt.uid})
        shown = host.wait("bluff_show_result", since=mark, timeout=4)
        shown_at = time.time()
        log(shown is not None, "%s: the Show's cards were turned up" % tag)
        leaver = nxt if leaver_role == "challenger" else cur
        stay = [c for c in cl if c is not leaver]
        leaver.emit("quit_game", {"code": code, "user_id": leaver.uid})
        # The quit itself re-broadcasts the table while the cards are still up
        # (moves are rightly refused then). The reveal lasts 3s; the table must
        # come back after it.
        deadline = time.time() + 8
        back = None
        while time.time() < deadline and back is None:
            for (ev, d), t in zip(stay[0].events, stay[0].times):
                if ev in ("table_state", "game_end") and t >= shown_at + 2.8:
                    back = d
                    break
            time.sleep(0.05)
        log(back is not None, "%s: %s quit during the reveal and the table came back" % (tag, leaver_role))
        if back is None:
            return
        time.sleep(0.3)
        turn = stay[0].state.get("current_turn")
        log(turn in {c.uid for c in stay}, "%s: the turn is with a player still at the table" % tag)
        mover = by.get(turn)
        if mover is None:
            return
        n = len(mover.events)
        mover.emit("bluff_play", {"code": code, "user_id": mover.uid,
                                  "card_ids": [mover.hand[0]["id"]], "declared_rank": "A"})
        moved = mover.wait("table_state", since=n, timeout=5,
                           pred=lambda d: d.get("current_turn") != turn)
        errs = [d for ev, d in mover.events[n:] if ev == "error"]
        log(moved is not None and not errs,
            "%s: the next move is accepted (no 'Cards are being revealed' lock) %s" % (tag, errs[:1]))
    finally:
        for c in cl:
            try:
                c.cli.disconnect()
            except Exception:
                pass


table("t1", "challenger")
table("t2", "defender")

print("\n%d/%d bluff show-quit socket checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
