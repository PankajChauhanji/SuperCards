import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker over real sockets: four clients and two computer players, random play.

The engine fuzz (test_poker_fuzz.py) proves the rules; this proves what each
*player's device* is told, in the order it is told it, through a whole game:
random legal and illegal moves, the host dealing early, and players dropping
their connection mid-round and coming back.

Each client keeps the same model the browser does (static/js/poker/game.js):
the latest public state, and its own hand for the round it belongs to. After
the game, every client's event stream is checked:

  * one private hand per round, never changing within the round, two cards,
    different from every other player's;
  * a reconnect mid-round gets back exactly the cards it had (resync);
  * the hand hint the player was last told is the hand the summary shows for
    them, and the summary shows their own cards — "it says I made a pair I
    never had" cannot happen;
  * nobody ever receives another player's hole cards unless they are face up
    for the whole table (an all-in runout or a showdown);
  * whenever the public state says it is this client's turn it also carries
    what they may do, and an action sent then is accepted;
  * rounds arrive in order, coins are conserved in every summary, and every
    client ends on the same podium.

Needs a server on 5005; run_tests.py starts one with LEAK_GUARD=raise.
"""
import random
import time

import socketio

BASE = "http://localhost:5005"
results = []


def log(ok, msg):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg)


def ids(cards):
    return [c["id"] for c in (cards or [])]


def card_ids(node, out=None):
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


class Client:
    def __init__(self, uid, name):
        self.uid, self.name = uid, name
        self.events = []          # (time, event, payload) across every connection
        self.state = {}
        self.hand_round = 0
        self.hands = {}           # round -> list of card-id lists received
        self.hints = {}           # round -> last hand_name received
        self.sent_bad = 0         # illegal moves sent on purpose
        self.cli = None
        self.connect()

    def connect(self):
        self.cli = socketio.Client(reconnection=False)
        self.cli.on("*", self._record)
        self.cli.connect(BASE, wait_timeout=10)

    def _record(self, event, data=None):
        data = data if data is not None else {}
        self.events.append((time.time(), event, data))
        if event in ("round_start", "poker_state"):
            self.state = data
        elif event == "your_hand":
            rn = data.get("round_number", 0)
            self.hands.setdefault(rn, []).append(ids(data.get("cards")))
            self.hints[rn] = data.get("hand_name")

    def emit(self, event, payload):
        self.cli.emit(event, payload)

    def wait(self, event, timeout=8.0, since=0, pred=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for _, ev, data in self.events[since:]:
                if ev == event and (pred is None or pred(data)):
                    return data
            time.sleep(0.03)
        return None


rng = random.Random(4242)
names = ["Asha", "Ben", "Chen", "Dev"]
C = [Client("pk-fz-%d" % i, n) for i, n in enumerate(names)]
host = C[0]
code = None
reconnects = 0
acted = 0
try:
    host.emit("create_room", {"name": host.name, "user_id": host.uid, "game_type": "poker"})
    code = (host.wait("room_created") or {}).get("code")
    log(bool(code), "room created")
    for c in C[1:]:
        c.emit("join_room", {"code": code, "name": c.name, "user_id": c.uid})
        c.wait("join_ok")
    for c in C:
        c.emit("enter_room", {"code": code, "name": c.name, "user_id": c.uid})
    host.wait("player_list", pred=lambda d: len(d.get("players", [])) == 4)
    host.emit("update_settings", {"code": code, "user_id": host.uid, "settings": {
        "starting_chips": 10000, "rounds": 7, "turn_timer": 15, "timeout_limit": 3,
        "blind_up_every": 2, "hand_hints": 1}})
    host.wait("settings_updated")
    for _ in range(2):
        host.emit("add_bot", {"code": code, "user_id": host.uid})
    host.wait("player_list", pred=lambda d: len(d.get("players", [])) == 6)
    host.emit("start_game", {"code": code, "user_id": host.uid})
    log(host.wait("round_start") is not None, "game started with 4 clients and 2 bots")

    deadline = time.time() + 240
    last_act = {}
    while time.time() < deadline:
        if all(c.wait("game_end", timeout=0.01) is not None for c in C):
            break
        st = host.state
        if st.get("state") == "ROUND_END" and rng.random() < 0.02:
            host.emit("poker_next_round", {"code": code, "user_id": host.uid})
        for c in C:
            s = c.state
            if s.get("state") != "IN_TURN" or s.get("current_turn") != c.uid:
                continue
            a = s.get("actions")
            if not a:
                log(False, "%s: on turn but the state does not say what they may do" % c.name)
                continue
            key = (s.get("round_number"), s.get("street"), s.get("current_bet"), len(c.events))
            if last_act.get(c.uid) == key:
                continue
            last_act[c.uid] = key
            r = rng.random()
            if r < 0.05:
                c.sent_bad += 1
                c.emit("poker_action", {"code": code, "user_id": c.uid, "action": "raise", "amount": -1})
                continue
            if r < 0.14:
                move = ("fold", None)
            elif r < 0.17:
                move = ("allin", None)
            elif r < 0.45 and a.get("raise"):
                move = ("raise", rng.randint(a["min_to"], a["max_to"]))
            else:
                move = ("check" if a.get("check") else "call", None)
            c.emit("poker_action", {"code": code, "user_id": c.uid, "action": move[0], "amount": move[1]})
            acted += 1
        # Now and then a player's connection drops and comes back mid-round.
        if rng.random() < 0.015 and host.state.get("state") == "IN_TURN":
            c = rng.choice(C[1:])
            rn = c.state.get("round_number")
            before = list(c.hands.get(rn, [[]])[-1]) if rn in c.hands else None
            mark = len(c.events)
            c.cli.disconnect()
            time.sleep(0.3)
            c.connect()
            c.emit("enter_room", {"code": code, "name": c.name, "user_id": c.uid})
            reconnects += 1
            got = c.wait("your_hand", since=mark, timeout=5)
            if got is not None and before and got.get("round_number") == rn:
                log(ids(got.get("cards")) == before,
                    "%s reconnected in round %s and got the same two cards back" % (c.name, rn))
        time.sleep(0.05)

    ends = [c.wait("game_end", timeout=1) for c in C]
    log(all(e is not None for e in ends), "every client reached the podium")
    if all(ends):
        log(len({e.get("winner") for e in ends}) == 1, "every client shows the same winner")
        st = ends[0].get("standings") or []
        log(st and st[0]["user_id"] == ends[0]["winner"] and st[0]["place"] == 1, "the winner tops the standings")

    # ---- per-client stream checks ----
    all_hands = {}     # round -> {uid: cards}
    for c in C:
        for rn, lists in c.hands.items():
            uniq = {tuple(x) for x in lists if x}
            log(len(uniq) <= 1, "%s: one hand in round %d, never swapped (%s)" % (c.name, rn, uniq))
            if uniq:
                cards = list(uniq)[0]
                log(len(cards) == 2, "%s: two hole cards in round %d" % (c.name, rn))
                all_hands.setdefault(rn, {})[c.uid] = set(cards)
    for rn, hs in all_hands.items():
        seen = set()
        clash = False
        for u, cards in hs.items():
            clash |= bool(seen & cards)
            seen |= cards
        log(not clash, "round %d: no two players were dealt the same card" % rn)

    rounds_checked = 0
    for c in C:
        last_round = 0
        for _, ev, d in c.events:
            if ev == "round_start" and d.get("round_number", 0) > last_round:
                if last_round:
                    log(d["round_number"] == last_round + 1,
                        "%s: round %d follows round %d" % (c.name, d["round_number"], last_round))
                last_round = d["round_number"]
            if ev in ("poker_round_end", "game_end"):
                res = d.get("result") if ev == "poker_round_end" else d.get("last_round")
                if not res:
                    continue
                rn = res.get("round_number")
                shown = (res.get("hands") or {}).get(c.uid)
                mine = all_hands.get(rn, {}).get(c.uid)
                if shown and mine:
                    rounds_checked += 1
                    log(set(ids(shown["cards"])) == mine,
                        "%s: round %s summary shows the cards they held" % (c.name, rn))
                    log(c.hints.get(rn) == shown["name"],
                        "%s: round %s hint %r matches the summary %r" % (c.name, rn, c.hints.get(rn), shown["name"]))
        # Another player's cards only ever arrive once they are face up.
        for rn, hs in all_hands.items():
            others = set().union(*[v for u, v in hs.items() if u != c.uid]) if len(hs) > 1 else set()
            if not others:
                continue
            for _, ev, d in c.events:
                if ev in ("poker_round_end", "game_end"):
                    continue
                if ev in ("round_start", "poker_state", "your_hand") and d.get("round_number") not in (rn, None):
                    continue
                leaked = card_ids({k: v for k, v in d.items() if k != "revealed"} if isinstance(d, dict) else d) & others
                if leaked:
                    log(False, "%s received another player's card %s outside a reveal (%s)" % (c.name, leaked, ev))
                    break
    log(rounds_checked > 0, "showdowns were reached and checked (%d)" % rounds_checked)

    # Coins: every summary's coins add up to the 6 x 10,000 handed out.
    for c in C[:1]:
        for _, ev, d in c.events:
            if ev == "poker_round_end":
                total = sum(r["chips"] for r in d.get("rows", []))
                log(total == 60000, "round %s summary holds all 60,000 coins (%d)" % (d.get("round_number"), total))

    errors = [d for c in C for _, ev, d in c.events if ev == "error"]
    unexpected = [e for e in errors if "minimum" not in (e.get("message") or "").lower()
                  and "turn" not in (e.get("message") or "").lower()
                  and "raise" not in (e.get("message") or "").lower()]
    log(not unexpected, "no unexpected errors (%s)" % unexpected[:3])
    print("actions sent %d, illegal on purpose %d, reconnects %d" % (acted, sum(c.sent_bad for c in C), reconnects))
    log(acted >= 5, "the clients actually played (%d actions)" % acted)
finally:
    for c in C:
        try:
            c.cli.disconnect()
        except Exception:
            pass

print("\n%d/%d poker socket fuzz checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
