import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker over real sockets with two human clients.

What the engine tests cannot see: that each player's private deal reaches only
their own socket, that nothing either client receives ever carries the other's
hole cards (except at a showdown both reached), that the host alone can start
the next round, and that a quit ends a heads-up game for the player left.

Every event each client receives is recorded through a catch-all handler, so a
leak in *any* payload — not just the ones this test thinks to look at — fails it.

Needs a server on 5005; run_tests.py starts one with LEAK_GUARD=raise.
"""
import time

import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def card_ids(node, out=None):
    """Every serialized card id anywhere in a payload."""
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str):
            out.add(node.get("id"))
            return out
        for v in node.values():
            card_ids(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            card_ids(v, out)
    return out


class Player:
    def __init__(self, uid, name):
        self.uid, self.name = uid, name
        self.cli = socketio.Client()
        self.events = []          # (event, payload) in arrival order
        self.last = {}            # event -> latest payload
        self.cli.on("*", self._record)

    def _record(self, event, data=None):
        self.events.append((event, data))
        self.last[event] = data if data is not None else {}

    def wait(self, event, timeout=8.0, since=0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev, data in self.events[since:]:
                if ev == event and (pred is None or pred(data or {})):
                    return data or {}
            time.sleep(0.05)
        return None

    def emit(self, event, payload):
        self.cli.emit(event, payload)


def latest_state(p):
    """The freshest public table state this client holds."""
    for ev, data in reversed(p.events):
        if ev in ("poker_state", "round_start"):
            return data or {}
    return {}


A = Player("pk-sock-a", "Asha")
B = Player("pk-sock-b", "Ben")
code = None
try:
    A.cli.connect(BASE, wait_timeout=10)
    B.cli.connect(BASE, wait_timeout=10)

    A.emit("create_room", {"name": A.name, "user_id": A.uid, "game_type": "poker",
                           "settings": {"rounds": 3, "starting_chips": 100000}})
    created = A.wait("room_created")
    code = (created or {}).get("code")
    log(bool(code) and created.get("game_type") == "poker", "host created a poker room")

    B.emit("join_room", {"code": code, "name": B.name, "user_id": B.uid})
    log(B.wait("join_ok") is not None, "second player joined")
    A.emit("enter_room", {"code": code, "name": A.name, "user_id": A.uid})
    B.emit("enter_room", {"code": code, "name": B.name, "user_id": B.uid})
    joined = B.wait("room_joined")
    log(joined and joined.get("settings", {}).get("starting_chips") == 100000,
        "host's starting coins (100,000) reached the room settings")
    A.wait("player_list", pred=lambda d: len(d.get("players", [])) == 2)

    B.emit("poker_next_round", {"code": code, "user_id": B.uid})
    log(B.wait("error") is not None, "a guest cannot start rounds")

    A.emit("start_game", {"code": code, "user_id": A.uid})
    start = A.wait("round_start")
    log(start is not None and start.get("blinds") == {"sb": 500, "bb": 1000},
        "round 1 dealt with blinds 500 / 1,000 (1% of 100,000)")
    hand_a = A.wait("your_hand")
    hand_b = B.wait("your_hand")
    ids_a = {c["id"] for c in (hand_a or {}).get("cards", [])}
    ids_b = {c["id"] for c in (hand_b or {}).get("cards", [])}
    log(len(ids_a) == 2 and len(ids_b) == 2 and not (ids_a & ids_b),
        "each player privately received two different hole cards")

    # ---- round 1: whoever is on turn folds -> fold win, nothing revealed ----
    mark_a, mark_b = len(A.events), len(B.events)
    turn = start.get("current_turn")
    actor = A if turn == A.uid else B
    actor.emit("poker_action", {"code": code, "user_id": actor.uid, "action": "fold"})
    end_a = A.wait("poker_round_end", since=mark_a)
    end_b = B.wait("poker_round_end", since=mark_b)
    log(end_a is not None and end_b is not None, "fold ends the round; both see the summary")
    if end_a:
        log(end_a["result"]["fold_win"] and end_a["result"]["hands"] == {},
            "an uncontested win reveals no cards")
        log(25 <= (end_a.get("seconds_left") or 0) <= 30,
            "summary carries the 30s auto-start countdown")
        log(sorted(r["chips"] for r in end_a["rows"]) == [99500, 100500],
            "coins left after the blinds moved: 99,500 / 100,500")

    # Over the whole round, neither client ever saw the other's hole cards.
    seen_a = set().union(*(card_ids(d) for _, d in A.events))
    seen_b = set().union(*(card_ids(d) for _, d in B.events))
    log(not (seen_a & ids_b) and not (seen_b & ids_a),
        "neither player ever received the other's cards (fold win)")

    # ---- host starts round 2 early ----
    mark_a, mark_b = len(A.events), len(B.events)
    A.emit("poker_next_round", {"code": code, "user_id": A.uid})
    r2 = A.wait("round_start", since=mark_a)
    log(r2 is not None and r2.get("round_number") == 2, "host started round 2 before the countdown")
    h2a = A.wait("your_hand", since=mark_a)
    h2b = B.wait("your_hand", since=mark_b)
    ids2_a = {c["id"] for c in (h2a or {}).get("cards", [])}
    ids2_b = {c["id"] for c in (h2b or {}).get("cards", [])}

    # ---- round 2: check / call down to a showdown ----
    deadline = time.time() + 20
    end2 = None
    while time.time() < deadline:
        end2 = A.wait("poker_round_end", timeout=0.05, since=mark_a)
        if end2:
            break
        st = latest_state(A)
        cur = st.get("current_turn")
        acts = st.get("actions") or {}
        if cur in (A.uid, B.uid) and acts:
            who = A if cur == A.uid else B
            n = len(A.events)
            who.emit("poker_action", {"code": code, "user_id": who.uid,
                                      "action": "check" if acts.get("check") else "call"})
            A.wait("poker_state", timeout=3, since=n)
        else:
            time.sleep(0.1)
    log(end2 is not None, "round 2 reached the summary by checking and calling down")
    if end2:
        res = end2["result"]
        log(not res["fold_win"] and set(res["hands"]) == {A.uid, B.uid} and len(res["board"]) == 5,
            "showdown: both hands and the full board are in the summary")
        log(all(a.get("hand_name") for a in res["awards"]), "every pot names the winning hand")
        log(sum(r["chips"] for r in end2["rows"]) == 200000, "no coin created or destroyed")
        # Showdown makes both hands public — but only from the showdown on.
        pre = [d for ev, d in B.events[mark_b:] if ev != "poker_round_end"
               and not (isinstance(d, dict) and d.get("state") in ("ROUND_END", "GAME_END"))]
        log(not (set().union(*(card_ids(d) for d in pre)) & ids2_a),
            "B never saw A's round-2 cards before the showdown")

    log(not [d for ev, d in A.events + B.events if ev == "error" and d
             and "turn" not in (d.get("message") or "") and "host" not in (d.get("message") or "")],
        "no unexpected errors")

    # ---- hand hints default OFF: no private payload named anyone's hand ----
    named = [d for p in (A, B) for ev, d in p.events if ev == "your_hand" and d and d.get("hand_name")]
    log(not named, "hand hints off (default): no your_hand ever carried a hand name")

    # ---- B quits: heads-up game ends for A ----
    mark_a = len(A.events)
    B.emit("quit_game", {"code": code, "user_id": B.uid})
    over = A.wait("game_end", since=mark_a)
    log(over is not None and over.get("winner") == A.uid,
        "the other player quitting ends a heads-up game; the one left wins")
    if over:
        st = over.get("standings") or []
        log(len(st) == 1 and st[0]["user_id"] == A.uid and st[0]["place"] == 1,
            "a player who left is not ranked")

    # ---- a second table with the host's hand hints switched ON ----
    A2 = Player("pk-sock-a2", "Asha")
    B2 = Player("pk-sock-b2", "Ben")
    try:
        A2.cli.connect(BASE, wait_timeout=10)
        B2.cli.connect(BASE, wait_timeout=10)
        A2.emit("create_room", {"name": A2.name, "user_id": A2.uid, "game_type": "poker"})
        code2 = (A2.wait("room_created") or {}).get("code")
        B2.emit("join_room", {"code": code2, "name": B2.name, "user_id": B2.uid})
        B2.wait("join_ok")
        A2.emit("enter_room", {"code": code2, "name": A2.name, "user_id": A2.uid})
        B2.emit("enter_room", {"code": code2, "name": B2.name, "user_id": B2.uid})
        A2.wait("player_list", pred=lambda d: len(d.get("players", [])) == 2)
        # The lobby switch saves the whole form; the server keeps only valid keys.
        A2.emit("update_settings", {"code": code2, "user_id": A2.uid,
                                    "settings": {"starting_chips": 100000, "rounds": 2, "turn_timer": 30,
                                                 "timeout_limit": 3, "blind_up_every": 0, "hand_hints": 1}})
        upd = B2.wait("settings_updated")
        log(upd is not None and upd["settings"].get("hand_hints") == 1,
            "host switched hand hints on; every player's client is told")
        A2.emit("start_game", {"code": code2, "user_id": A2.uid})
        ha = A2.wait("your_hand", pred=lambda d: d.get("round_number") == 1)
        hb = B2.wait("your_hand", pred=lambda d: d.get("round_number") == 1)
        log(bool(ha and ha.get("hand_name")) and bool(hb and hb.get("hand_name")),
            "hints on: each player privately receives their own hand's name (%s / %s)"
            % ((ha or {}).get("hand_name"), (hb or {}).get("hand_name")))
        log(isinstance((ha or {}).get("hand_rank"), int) and isinstance((hb or {}).get("hand_rank"), int),
            "hints on: each player receives their row on the rankings card")
        others = {c["id"] for c in (hb or {}).get("cards", [])}
        seen = set().union(*(card_ids(d) for _, d in A2.events))
        log(not (seen & others), "hints on still never shows a player the other's cards")
    finally:
        for p in (A2, B2):
            try:
                p.cli.disconnect()
            except Exception:
                pass
finally:
    for p in (A, B):
        try:
            p.cli.disconnect()
        except Exception:
            pass

print("\n%d/%d poker socket checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
