import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker's director ticker, driven directly with a recording fake socket.

The timers are the part a socket test would have to sit and wait for: the turn
clock (30s), the round-summary auto-start (30s) and the runout steps. Here time
is moved by editing the room's deadlines, so each branch runs in milliseconds:
timeout -> check/fold, repeated timeouts -> sat out -> instant auto-play, runout
streets, the summary dealing the next round by itself, and bots taking turns.
Every room-wide broadcast is also checked against the visibility oracle.
"""
import time

from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.poker.room import Room, PHASE_RUNOUT
from game.poker.settings import DEFAULT_SETTINGS
from game.poker.visibility import public_card_ids
from sockets import director
import sockets.gameplay.poker as pk

results = []
def check(ok, msg):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + msg)


def cards_in(node, out):
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str):
            out.add(node.get("id")); return out
        for v in node.values():
            cards_in(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            cards_in(v, out)
    return out


ALL_LEAKS = []   # across every fake socket in this file, not just the last


class FakeSocket:
    def __init__(self, room):
        self.room = room
        self.sent = []
        self.leaks = ALL_LEAKS

    def emit(self, event, payload=None, to=None):
        self.sent.append((event, payload, to))
        if to == self.room.code:   # room-wide: must hold only public cards
            extra = cards_in(payload, set()) - public_card_ids(self.room)
            if extra:
                self.leaks.append((event, sorted(extra)))

    def events(self):
        return [e for e, _, _ in self.sent]


def make_room(n=2, bots=0, **settings):
    s = dict(DEFAULT_SETTINGS); s.update(settings)
    room = Room("TICK", "h0", s)
    for i in range(n):
        p = room.register_player("h%d" % i, "Human %d" % i)
        p.connected = True
        p.sid = "sid-%d" % i
    for i in range(bots):
        b = room.register_player("bot_%d" % i, "Bot %d" % i)
        b.connected = True
        b.is_bot = True
    room._pick_first_button = lambda eligible: eligible[0]
    room.start_round()
    return room


def tick(room, fake):
    pk._sio = fake
    pk._tick_room(fake, room)


check(pk.GAME in director._TICKERS, "poker registers a director ticker")
check(director._TICK_STATES.get("poker") == (STATE_IN_TURN, STATE_ROUND_END),
      "poker's ticker opts in to the round summary as well as play")
check(director._TICK_STATES.get("super_seven") == (STATE_IN_TURN,)
      and director._TICK_STATES.get("bluff") == (STATE_IN_TURN,)
      and director._TICK_STATES.get("super_four") == (STATE_IN_TURN,),
      "every other game still ticks only mid-round (unchanged behaviour)")

# ---- nothing happens before the clock runs out ----
room = make_room(2)
fake = FakeSocket(room)
tick(room, fake)
check(fake.sent == [], "a fresh turn with time left: the ticker does nothing")

# ---- timeout: fold when facing a bet, and count it ----
cur = room.current_turn_id()
room.turn_start_ts -= 1000
tick(room, fake)
check(room.state == STATE_ROUND_END and cur in room.folded, "timeout facing the big blind folds")
check("player_timed_out" in fake.events() and "poker_round_end" in fake.events(),
      "the timeout is announced and the summary is broadcast")
check(room.players[cur].timeout_count == 1, "the timeout is counted")

# ---- the round summary deals the next round by itself ----
fake.sent.clear()
tick(room, fake)
check(room.state == STATE_ROUND_END, "summary waits while its countdown runs")
room.round_end_at = time.time() - 1
tick(room, fake)
check(room.state == STATE_IN_TURN and room.round_number == 2 and "round_start" in fake.events(),
      "after the countdown the next round deals automatically")
check(sum(1 for e, _, to in fake.sent if e == "your_hand") == 2,
      "each human gets their new private hand, addressed to their own socket")
check(all(to.startswith("sid-") for e, _, to in fake.sent if e == "your_hand"),
      "private hands never go to the room")

# ...but not into an empty room.
for p in room.players.values():
    p.connected = False
room.act(room.current_turn_id(), "fold")
room.round_end_at = time.time() - 1
tick(room, fake)
check(room.state == STATE_ROUND_END, "with nobody connected the next round is not dealt")

# ---- timeout with a free check checks ----
room = make_room(3)
fake = FakeSocket(room)
room.act("h0", "call"); room.act("h1", "call")      # BB h2 now has the option
room.turn_start_ts -= 1000
tick(room, fake)
check("h2" not in room.folded and room.street == "flop", "timeout with a free check checks")

# ---- repeated timeouts sit you out; then you act instantly ----
room = make_room(3, timeout_limit=1)
fake = FakeSocket(room)
room.turn_start_ts -= 1000
tick(room, fake)                                     # h0 times out -> sat out
check("h0" in room.sitting_out, "reaching the timeout limit sits the player out")
room.act("h1", "fold")                               # round ends (h2 wins)
room.start_round()                                   # button h1: h2 SB, h0 BB, h1 first
room.act("h1", "call"); room.act("h2", "call")       # action reaches sat-out h0
fake.sent.clear()
tick(room, fake)
check(room.street == "flop" and any(e == "poker_acted" and p.get("reason") == "sitting_out"
                                    for e, p, _ in fake.sent),
      "a sat-out player is auto-played at once, without waiting out the clock")
check(room.come_back("h0") and "h0" not in room.sitting_out, "I'm back returns them to play")

# ---- all-in runout is dealt street by street ----
room = make_room(2)
fake = FakeSocket(room)
room.act(room.current_turn_id(), "allin")
room.act(room.current_turn_id(), "call")
check(room.phase == PHASE_RUNOUT and len(room.board) == 0, "both all-in: runout begins")
tick(room, fake)
check(len(room.board) == 0, "the next street waits for its step time")
for expected in (3, 4):
    room.runout_next_at = time.time() - 1
    tick(room, fake)
    check(len(room.board) == expected, "runout step deals the board to %d cards" % expected)
room.runout_next_at = time.time() - 1
tick(room, fake)
check(room.state in (STATE_ROUND_END, STATE_GAME_END) and len(room.board) == 5,
      "the last runout step completes the board and settles the pot")

# ---- bots take their turns ----
room = make_room(1, bots=3, rounds=2)
fake = FakeSocket(room)
moves = 0
for _ in range(400):
    if room.state == STATE_GAME_END:
        break
    cur = room.current_turn_id()
    if room.state == STATE_IN_TURN and cur == "h0":
        # Same path as the poker_action handler: act, announce, broadcast.
        done = room.act("h0", "check" if room.legal_actions("h0")["check"] else "call")
        pk._announce(room, done)
        pk._broadcast(room)
        continue
    for key in list(pk._bot_act_at):
        pk._bot_act_at[key] = 0          # no thinking time in a test
    room.runout_next_at = 0
    room.round_end_at = 0
    before = len(fake.sent)
    tick(room, fake)
    moves += len(fake.sent) > before
check(room.state == STATE_GAME_END, "a human calling down against three bots reaches the game end")
check(moves > 5 and "game_end" in fake.events(), "bots acted through the ticker and the podium was broadcast")

check(not ALL_LEAKS, "no room-wide broadcast in any scenario carried a hidden card%s"
      % ("" if not ALL_LEAKS else " (%s)" % (ALL_LEAKS[0],)))

print("\n%d/%d poker ticker checks passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
