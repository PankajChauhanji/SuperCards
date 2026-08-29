import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Seating computer players over the wire: the rules, and that they actually play.

tests/test_bots.py covers identity and caps at the engine level. This covers the
half that only exists once a socket is involved — who is allowed to seat a bot,
when, and whether a room of humans plus bots really advances without anyone
touching it.

Driven against a live server on port 5005 (run_tests.py boots one).
"""
import collections
import time

import socketio

BASE = "http://localhost:5005"
RANKS = {1: "A", 11: "J", 12: "Q", 13: "K"}

results = []


def check(ok, msg, extra=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + msg + (("  " + str(extra)) if not ok and extra else ""))


class Client:
    def __init__(self, uid, name):
        self.uid, self.name = uid, name
        self.events = collections.OrderedDict()
        self.hand = []
        self.sio = socketio.Client()
        self.sio.on("*", self._on)
        self.sio.connect(BASE, transports=["polling"], wait_timeout=10)

    def _on(self, event, data=None):
        self.events[event] = data
        if event == "your_hand":
            self.hand = data["cards"]

    def emit(self, event, data=None):
        self.sio.emit(event, data or {})

    def roster(self):
        snap = self.events.get("player_list") or self.events.get("room_joined") or {}
        return snap.get("players", [])

    def error(self, timeout=4.0):
        """The next error message, waiting for it to arrive, then consuming it.

        Waiting inside the accessor rather than at each call site: reading the
        error before the server has sent it does not just fail that check, it
        leaves the message in the queue for the *next* one to consume, so a
        single race reports as two unrelated failures.
        """
        deadline = time.time() + timeout
        while "error" not in self.events and time.time() < deadline:
            time.sleep(0.05)
        return (self.events.pop("error", None) or {}).get("message", "")

    def close(self):
        try:
            self.sio.disconnect()
        except Exception:
            pass


def wait_for(predicate, timeout=6.0, step=0.05):
    """Poll until the server has caught up, rather than guessing with sleep().

    These tests share one server with every other socket file, so a fixed sleep
    that is comfortable on an idle machine becomes a coin flip on a busy one —
    and a flaky gate is worse than no gate.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def close_room(clients, code):
    """Leave the room properly, so it does not outlive the test.

    A room whose humans have all gone still holds bots, and bots keep taking
    turns until the reaper gets to the room — which loads the director for every
    test that runs after this one on the same server. Quitting first ends the
    game rather than leaving it running headless.
    """
    for c in clients:
        try:
            c.emit("quit_game", {"code": code, "user_id": c.uid})
        except Exception:
            pass
    time.sleep(0.4)
    for c in clients:
        c.close()


def open_room(game_type, humans=2, settings=None):
    clients = [Client("h%d" % i, "H%d" % i) for i in range(humans)]
    clients[0].emit("create_room", {
        "name": "H0", "user_id": "h0", "game_type": game_type,
        "settings": settings or {"turn_timer": 180},
    })
    assert wait_for(lambda: "room_created" in clients[0].events), "room was never created"
    code = clients[0].events["room_created"]["code"]
    for c in clients[1:]:
        c.emit("join_room", {"code": code, "name": c.name, "user_id": c.uid})
        wait_for(lambda c=c: "join_ok" in c.events)
    for c in clients:
        c.emit("enter_room", {"code": code, "name": c.name, "user_id": c.uid})
    for c in clients:
        wait_for(lambda c=c: "room_joined" in c.events)
    wait_for(lambda: len(clients[0].roster()) == humans)
    return clients, code


# ---- who may seat a bot, and when ---------------------------------------
clients, code = open_room("super_seven")
host, guest = clients

guest.emit("add_bot", {"code": code, "user_id": guest.uid})
check(guest.error().startswith("Only the host"), "a non-host cannot seat a bot")

host.emit("add_bot", {"code": code, "user_id": "h0", "bot": "not_a_bot"})
check(host.error() == "No such computer player.", "an unknown profile key is refused")

host.emit("add_bot", {"code": code, "user_id": "h0", "bot": "smriti"})
wait_for(lambda: any(p["is_bot"] for p in host.roster()))
seated = [p for p in host.roster() if p["is_bot"]]
check([p["name"] for p in seated] == ["Smriti Mandhana"], "the host seats the profile they picked",
      [p["name"] for p in seated])
check("bot_added" in guest.events, "and every player in the room is told")

# The cap holds no matter how often it is asked.
for i in range(6):
    want = min(i + 2, 5)
    host.emit("add_bot", {"code": code, "user_id": "h0"})
    wait_for(lambda w=want: len([p for p in host.roster() if p["is_bot"]]) >= w, timeout=2.0)
seated = [p for p in host.roster() if p["is_bot"]]
check(len(seated) == 5, "the bot cap holds at 5", [p["name"] for p in seated])
check(len({p["name"] for p in seated}) == 5, "and all five have distinct names",
      [p["name"] for p in seated])
check("at most" in host.error(), "the refusal explains the cap")
host.events.pop("error", None)   # drain the rest of the cap loop's refusals

# A bot can be taken back off the table, unlike before.
host.emit("kick_player", {"code": code, "user_id": "h0", "target": seated[0]["user_id"]})
wait_for(lambda: len([p for p in host.roster() if p["is_bot"]]) == 4)
check(len([p for p in host.roster() if p["is_bot"]]) == 4, "the host can remove a bot")

host.emit("start_game", {"code": code, "user_id": "h0"})
# Wait for the round to actually be dealt: asserting on a fixed sleep here
# raced the server and passed or failed depending on machine load.
check(wait_for(lambda: "round_start" in host.events), "the game starts with bots seated")
host.emit("add_bot", {"code": code, "user_id": "h0"})
check("before the game starts" in host.error(),
      "a bot cannot be seated once the game is under way")
close_room(clients, code)


# ---- a game's own table limit still applies -----------------------------
clients, code = open_room("bluff", humans=1)
host = clients[0]
for i in range(7):
    want = min(i + 2, 6)
    host.emit("add_bot", {"code": code, "user_id": "h0"})
    wait_for(lambda w=want: len(host.roster()) >= w, timeout=2.0)
check(len(host.roster()) == 6,
      "Bluff's 6-seat table fills at 1 human + 5 bots and stops", len(host.roster()))
close_room(clients, code)


# ---- humans and bots at one table, actually playing ---------------------
for game_type in ("super_seven", "bluff"):
    clients, code = open_room(game_type, humans=2)
    host = clients[0]
    for n, key in enumerate(("rajnikant", "rashmika"), start=1):
        host.emit("add_bot", {"code": code, "user_id": "h0", "bot": key})
        wait_for(lambda w=n: len([p for p in host.roster() if p["is_bot"]]) >= w)
    host.emit("start_game", {"code": code, "user_id": "h0"})
    wait_for(lambda: "round_start" in host.events)

    start = host.events.get("round_start") or {}
    check(len(start.get("turn_order", [])) == 4,
          "%s: two humans and two bots are all dealt in" % game_type,
          start.get("turn_order"))
    check(all(c.hand for c in clients),
          "%s: both humans received a private hand" % game_type)

    # Each human plays once; everything after that is the bots' doing.
    by_id = {c.uid: c for c in clients}
    played = set()
    bots_seen = set()
    for _ in range(60):
        state = host.events.get("table_state") or host.events.get("round_start") or {}
        turn = state.get("current_turn")
        if turn and turn.startswith("bot_"):
            bots_seen.add(turn)
        actor = by_id.get(turn)
        # Once per human: in Super Seven a play owes a draw, so the turn lingers
        # for a beat and acting again would only produce an error.
        if actor is not None and actor.hand and actor.uid not in played:
            played.add(actor.uid)
            card = actor.hand[0]
            if game_type == "super_seven":
                actor.emit("play_cards", {"code": code, "user_id": actor.uid,
                                          "card_ids": [card["id"]]})
            else:
                actor.emit("bluff_play", {
                    "code": code, "user_id": actor.uid, "card_ids": [card["id"]],
                    "declared_rank": state.get("target_rank")
                                     or RANKS.get(card["rank"], str(card["rank"])),
                })
        time.sleep(0.5)
        if len(bots_seen) >= 2:
            break

    check(len(bots_seen) >= 2,
          "%s: both bots took their own turn and play moved on" % game_type,
          sorted(bots_seen))
    close_room(clients, code)


print("\n%d/%d bot socket checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
