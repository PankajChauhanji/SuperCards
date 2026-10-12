import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Bluff engine under fire: thousands of seeded random games.

Every game is driven through the real authority path — the socket handlers in
sockets/gameplay/bluff.py (bluff_play / bluff_pass / bluff_show /
bluff_shuffle_seats / bluff_next_round, which is where move validation lives)
and the director ticker (_tick_room: turn timer, computer players) — with a
fake socketio object, so no server is needed. The three-second reveal inside a
Show (``eventlet.sleep(3)``) is replaced by a hook that lets the table misbehave
*during* the reveal: people quit, act out of turn, the timer fires, the host
shuffles. Quits go through Room.remove_participant and rematches through
Room.reset_for_rematch, exactly as the lobby handlers call them.

Invariants, after every step (rules: docs/bluff_rules.md, static/rules/bluff/en.html):
  * every card is accounted for exactly once (hands + centre pile + dead pile),
    minus the hands of players who quit;
  * while the game is in play the turn belongs to a present, non-eliminated,
    unfinished player holding cards; at least two are still in the race and the
    podium is not full; every game terminates;
  * a move is accepted iff the rules say it is legal (play 1+ of your own cards,
    declaring a real rank, the locked rank if one is set; Show only by the
    immediate next player, before any other action); a refused move leaves the
    table exactly as it was;
  * a Show flips exactly the challenged play; a caught bluffer, or a wrong
    challenger, picks up the whole pile; the winner of the Show leads;
  * a full pass sweeps the pile to the dead pile exactly when the turn would
    come back round to the player who played last;
  * a player who shed their last cards is banked once the next player acts
    without calling Show; the game ends at 3 places or one player left; places
    and the winner follow finish order, then fewest cards;
  * no public view or broadcast carries a card face (game/bluff/visibility.py)
    except the Show reveal, and private hands go only to their owner;
  * game_end_payload always builds, after any quit; there is always a usable host.

Scale with BLUFF_FUZZ_GAMES (default 2000).
"""
import random
import time
import traceback
import types
from collections import Counter

from game.core import bots as botlib
from game.core.cards import build_deck
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_GAME_END
from game.core.visibility import EVERYTHING
from game.bluff.room import Room
from game.bluff.settings import DEFAULT_SETTINGS, PODIUM_PLACES
from game.bluff.visibility import public_card_ids
import sockets.gameplay.bluff as gb

# See pass_closes_window: the strict "next player only" Show rule, or the house rule.
STRICT_SHOW = os.environ.get("BLUFF_STRICT_SHOW") == "1"

results = []
failures = Counter()
stats = Counter()
CODE = "BLUF"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def check(ok, msg):
    results.append(bool(ok))
    if not ok:
        key = msg.split(":")[0]
        failures[key] += 1
        if failures[key] <= int(os.environ.get("FUZZ_SHOW", "3")):
            print("FAIL " + msg)
    return ok


def code_of(card):
    """The rank a card really is, written independently of game.core.cards.rank_code."""
    return RANKS[card.rank - 1]


def card_ids_in(node, out):
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str):
            out.add(node.get("id"))
            return out
        for v in node.values():
            card_ids_in(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            card_ids_in(v, out)
    return out


# ---------------------------------------------------------------------------
# Fake socket plumbing
# ---------------------------------------------------------------------------
class Wire:
    def __init__(self):
        self.table = None
        self.handlers = {}
        self.errors = []
        self.requester = None

    def on(self, name):
        def deco(fn):
            self.handlers[name] = fn
            return fn
        return deco

    def emit(self, event, data=None, to=None, **_kw):
        t = self.table
        if event == "error":
            self.errors.append((data or {}).get("message"))
            return
        if t is None:
            return
        room = t.room
        ids = card_ids_in(data, set())
        if event == "bluff_show_result":
            t.on_reveal(data)
            return
        if not ids:
            return
        if to == room.code:
            allowed = public_card_ids(room)
            leaked = [i for i in ids if i not in allowed]
            check(not leaked, "leak: broadcast %r in %s carries %s (%s)" % (
                event, room.state, sorted(leaked)[:4], t.tag))
        else:
            owner = self.requester if to is None else t.sid_owner.get(to)
            p = room.players.get(owner)
            mine = {c.id for c in p.hand} if p else set()
            check(ids <= mine, "leak: private %r to %s carries cards not theirs %s (%s)" % (
                event, owner, sorted(ids - mine)[:4], t.tag))

    def get_room(self, code):
        if self.table and code == self.table.room.code:
            return self.table.room
        return None


WIRE = Wire()
gb.emit = WIRE.emit
gb.error = lambda message, reason="": WIRE.emit("error", {"message": message})
gb.register(WIRE, WIRE)
H = WIRE.handlers


def _reveal_sleep(_seconds=0):
    """Stands in for the 3 s reveal: whatever the table does meanwhile."""
    if WIRE.table is not None:
        WIRE.table.during_reveal()


try:   # the handlers do `import eventlet; eventlet.sleep(3)` inside the Show path
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import eventlet
    eventlet.sleep = _reveal_sleep
except ImportError:  # pragma: no cover
    sys.modules["eventlet"] = types.SimpleNamespace(sleep=_reveal_sleep)


# What the bot decided on its last tick (game.bluff.ai.decide_move is imported
# by the ticker at call time, so wrapping the module attribute catches it).
import game.bluff.ai as _bluff_ai
LAST_BOT_MOVE = {}
_real_decide = _bluff_ai.decide_move


def _recording_decide(room, bot_id):
    mv = _real_decide(room, bot_id)
    LAST_BOT_MOVE["move"] = mv
    return mv


_bluff_ai.decide_move = _recording_decide


def snapshot(room):
    lp = room.last_play
    return (
        room.state, room.turn_index, tuple(room.turn_order), room.target_rank, room.pass_count,
        tuple(c.id for c in room.center_pile), tuple(c.id for c in room.dead_pile),
        (lp["user_id"], tuple(c.id for c in lp["cards"]), lp["declared_rank"]) if lp else None,
        tuple(room.finish_order), room.host_id, room.game_over, room.winner, room.is_showing,
        room.shuffle_pending, room.seat_shuffles,
        tuple(sorted((u, tuple(c.id for c in p.hand), p.eliminated, p.timeout_count, p.is_spectator)
                     for u, p in room.players.items())),
    )


class Pre:
    def __init__(self, room):
        self.key = snapshot(room)
        self.state = room.state
        self.order = list(room.turn_order)
        self.cur = room.current_turn_id() if room.state == STATE_IN_TURN else None
        self.hands = {u: [c for c in p.hand] for u, p in room.players.items()}
        self.center = [c.id for c in room.center_pile]
        self.dead = [c.id for c in room.dead_pile]
        self.target = room.target_rank
        self.last_play = dict(room.last_play) if room.last_play else None
        self.last_play_obj = room.last_play      # identity of the live play
        self.finish = list(room.finish_order)
        self.elim = {u for u, p in room.players.items() if p.eliminated}
        self.timeouts = {u: p.timeout_count for u, p in room.players.items()}
        self.shuffle_pending = room.shuffle_pending


# ---------------------------------------------------------------------------
class Table:
    def __init__(self, seed):
        self.seed = seed
        self.rng = rng = random.Random(seed)
        random.seed(seed * 104729 + 3)
        self.tag = "seed %d" % seed
        settings = dict(DEFAULT_SETTINGS)
        settings.update({
            "timeout_limit": rng.choice([1, 2, 3, 3, 5]),
            "num_decks": rng.choice([1, 1, 1, 2]),
        })
        n_humans = rng.choice([1, 2, 2, 3, 3, 4, 4, 5, 6, 8])
        n_bots = rng.choice([0, 0, 0, 1, 2]) if n_humans > 1 else rng.choice([1, 2])
        self.room = room = Room(CODE, "h0", settings)
        self.sid_owner = {}
        for i in range(n_humans):
            self.add_human("h%d" % i)
        for _ in range(n_bots):
            botlib.add_to(room)
        self.gone = set()
        self.window = None        # reference: the play that may still be challenged
        self.chain_key, self.passers = None, set()   # reference: who passed on the live play
        self.steps = 0
        self.rematches = 0
        self.over = False
        self.reveal = None
        self.in_reveal = False

    def add_human(self, uid):
        p = self.room.register_player(uid, uid.upper())
        p.connected = True
        p.sid = "sid-" + uid
        self.sid_owner[p.sid] = uid
        return p

    def humans_connected(self):
        return any(p.connected and not p.is_bot for p in self.room.players.values())

    def call(self, event, actor, **payload):
        """Fire a real handler as `actor`: True accepted, False refused, None crashed.

        Re-entrant: a Show's reveal hook fires further calls from inside the
        handler, so each call keeps its own error list and requester.
        """
        saved = (WIRE.errors, WIRE.requester)
        mine = WIRE.errors = []
        WIRE.requester = actor
        data = {"code": CODE, "user_id": actor}
        data.update(payload)
        try:
            H[event](data)
        except Exception as exc:
            check(False, "crash: handler %s raised %s: %r (%s)\n%s" % (
                event, type(exc).__name__, exc, self.tag, traceback.format_exc(limit=4)))
            self.crashed = True
            return None
        finally:
            WIRE.errors, WIRE.requester = saved
        self.last_errors = mine
        return not mine

    def tick(self):
        try:
            gb._tick_room(WIRE, self.room)
        except Exception as exc:
            check(False, "crash: director tick raised %s: %r (%s)\n%s" % (
                type(exc).__name__, exc, self.tag, traceback.format_exc(limit=4)))
            self.crashed = True

    # ---- reference helpers ---------------------------------------------------
    def in_race(self, u):
        p = self.room.players.get(u)
        return p is not None and not p.eliminated and u not in self.room.finish_order

    def ref_next(self, order, after):
        if after not in order:
            return None
        n = len(order)
        i = order.index(after)
        for k in range(1, n + 1):
            u = order[(i + k) % n]
            if self.in_race(u):
                return u
        return None

    def lead_after_departure(self, pre, gone):
        """Who should be on turn after `gone` (on turn) leaves or is removed.

        Normally the next player still racing. If the departure means everyone
        left in the race has now passed on the live play, the pile is swept and
        the claimant leads (accepted either way: the current engine does not
        sweep here, which the turn-back-to-the-claimant invariant reports).
        """
        room = self.room
        seats = [u for u in pre.order if u in room.players or u == gone]
        nxt = self.ref_next(seats, gone)
        lp = pre.last_play
        if lp and room.last_play is None and lp["user_id"] in room.players:
            actor = lp["user_id"]
            if self.in_race(actor) and room.players[actor].hand:
                return actor
        return nxt

    def after_deal(self, offset_before):
        room = self.room
        stats["games dealt"] += 1
        self.gone = set()
        self.window = None
        want = [u for u, p in room.players.items()
                if p.connected and not p.eliminated and not p.is_spectator]
        check(room.turn_order == want, "deal: %s order %s, expected %s" % (self.tag, room.turn_order, want))
        sizes = [len(room.players[u].hand) for u in room.turn_order]
        check(sizes and max(sizes) - min(sizes) <= 1 and sum(sizes) == 52 * room.settings["num_decks"],
              "deal: %s uneven or incomplete deal %s" % (self.tag, sizes))
        if room.turn_order:
            check(room.current_turn_id() == room.turn_order[offset_before % len(room.turn_order)],
                  "deal: %s lead did not rotate" % self.tag)
        check(not room.finish_order and room.last_play is None and room.target_rank is None,
              "deal: %s carries old table state" % self.tag)

    # ---- invariants -------------------------------------------------------------
    def invariants(self, tag):
        room = self.room
        tag = "%s %s" % (self.tag, tag)
        if room.state != STATE_LOBBY:
            deck = {c.id for c in build_deck(room.settings["num_decks"])}
            cards = list(room.center_pile) + list(room.dead_pile)
            for p in room.players.values():
                cards.extend(p.hand)
            ids = [c.id for c in cards]
            check(len(ids) == len(set(ids)) and set(ids) == deck - self.gone,
                  "cards: %s %d held (%d distinct), %d expected; missing %s extra %s" % (
                      tag, len(ids), len(set(ids)), len(deck - self.gone),
                      sorted(deck - self.gone - set(ids))[:4], sorted(set(ids) - (deck - self.gone))[:4]))
            if room.last_play:
                lp = [c.id for c in room.last_play["cards"]]
                check(room.center_pile and [c.id for c in room.center_pile[-len(lp):]] == lp,
                      "pile: %s last play is not on top of the pile" % tag)
                check(room.target_rank == room.last_play["declared_rank"],
                      "pile: %s locked rank %r vs last claim %r" % (tag, room.target_rank, room.last_play["declared_rank"]))
            else:
                check(not room.center_pile, "pile: %s cards on the pile with no live play" % tag)
        fo = room.finish_order
        check(len(fo) == len(set(fo)), "places: %s duplicate finisher %s" % (tag, fo))
        for u in fo:
            p = room.players.get(u)
            check(p is None or not p.hand, "places: %s finisher %s holds %d cards" % (tag, u, len(p.hand) if p else 0))
        if room.state == STATE_IN_TURN:
            cur = room.current_turn_id()
            p = room.players.get(cur)
            check(p is not None and not p.eliminated and cur not in fo and not p.is_spectator,
                  "turn: %s turn on %s, who is out of play" % (tag, cur))
            if p is not None and not room.is_showing:
                check(len(p.hand) > 0, "turn: %s %s on turn with no cards (last play %s, pass_count %d)" % (
                    tag, cur, room.last_play and room.last_play["user_id"], room.pass_count))
            if room.last_play is not None and not room.is_showing:
                check(room.last_play["user_id"] != cur,
                      "turn back to the claimant: %s turn reached %s while their own play is still live "
                      "(pile not swept; pass_count %d, in race %s)" % (
                          tag, cur, room.pass_count, room.still_holding()))
            holding = room.still_holding()
            check(len(holding) >= 2 and len(fo) < PODIUM_PLACES,
                  "game end: %s still in play with %d in the race and %d finished" % (tag, len(holding), len(fo)))
            check(not room.game_over, "game end: %s game_over set mid-play" % tag)
        # Nothing public carries a face while in play.
        allowed = public_card_ids(room)
        if allowed is not EVERYTHING:
            for label, view in (("public_round_state", room.public_round_state()),
                                ("public_players", room.public_players())):
                leaked = card_ids_in(view, set()) - allowed
                check(not leaked, "leak: %s %s carries %s" % (tag, label, sorted(leaked)[:4]))
        if room.state == STATE_GAME_END:
            try:
                room.game_end_payload()
            except Exception as exc:
                check(False, "game-end payload: %s raised %s: %r" % (tag, type(exc).__name__, exc))
        if self.humans_connected():
            h = room.players.get(room.host_id)
            check(h is not None and not h.is_bot,
                  "host: %s host %r is %s" % (tag, room.host_id, "gone" if h is None else "a bot"))
        self.check_end_state(tag)

    def check_end_state(self, tag):
        room = self.room
        if room.state not in (STATE_IN_TURN, STATE_GAME_END):
            return
        holding = room.still_holding()
        should_end = len(room.finish_order) >= PODIUM_PLACES or len(holding) <= 1
        check((room.state == STATE_GAME_END) == should_end or (room.state == STATE_GAME_END and room.game_over),
              "game end: %s state %s with %d finished, %d in the race" % (
                  tag, room.state, len(room.finish_order), len(holding)))

    def check_standings(self, tag):
        room = self.room
        tag = "%s %s" % (self.tag, tag)
        rows = room.standings()
        ids = [r["user_id"] for r in rows]
        check(len(ids) == len(set(ids)), "standings: %s duplicates" % tag)
        fin = [u for u in room.finish_order if u in room.players]
        check(ids[:len(fin)] == fin, "standings: %s finishers %s not first in order %s" % (tag, fin, ids))
        rest = [r for r in rows if not r["finished"]]
        keys = [(r["eliminated"], r["cards_left"]) for r in rest]
        check(keys == sorted(keys), "standings: %s unfinished not ranked fewest cards first %s" % (tag, keys))
        for r in rest:
            check(r["cards_left"] == len(room.players[r["user_id"]].hand), "standings: %s cards_left" % tag)
        places = [r["place"] for r in rows]
        check(places == sorted(set(places)), "standings: %s places %s" % (tag, places))
        want = set(u for u in room.turn_order if u in room.players) | set(fin)
        check(set(ids) == want, "standings: %s rows %s vs seated %s" % (tag, sorted(ids), sorted(want)))
        if room.state == STATE_GAME_END and room.winner in room.players:
            check(ids and ids[0] == room.winner, "winner: %s %s is not first in %s" % (tag, room.winner, ids))

    # ---- the reveal ------------------------------------------------------------------
    def on_reveal(self, data):
        """bluff_show_result was broadcast: it must flip exactly the challenged play."""
        room = self.room
        lp = room.last_play
        revealed = [c["id"] for c in data.get("revealed_cards", [])]
        check(lp is not None and revealed == [c.id for c in lp["cards"]],
              "show reveal: %s revealed %s, challenged play was %s" % (
                  self.tag, revealed, lp and [c.id for c in lp["cards"]]))
        if lp:
            bluff = any(code_of(c) != lp["declared_rank"] for c in lp["cards"])
            check(data.get("is_bluff") == bluff, "show judge: %s is_bluff=%s, cards %s claimed %r" % (
                self.tag, data.get("is_bluff"), [code_of(c) for c in lp["cards"]], lp["declared_rank"]))
            want_loser = lp["user_id"] if bluff else data.get("challenger")
            check(data.get("loser") == want_loser, "show judge: %s loser %s, reference %s" % (
                self.tag, data.get("loser"), want_loser))

    def during_reveal(self):
        """Inside the 3 s reveal: the table keeps living."""
        room, rng = self.room, self.rng
        self.in_reveal = True
        stats["reveals"] += 1
        check(room.is_showing, "show: %s reveal running without is_showing" % self.tag)
        pre = Pre(room)
        roll = rng.random()
        if roll < 0.3:
            # Anyone tries to act: refused, nothing moves.
            actor = rng.choice(list(room.players))
            ev = rng.choice(["bluff_pass", "bluff_show", "bluff_play"])
            hand = room.players[actor].hand
            ok = self.call(ev, actor, card_ids=[c.id for c in hand[:1]],
                           declared_rank=room.target_rank or "7")
            check(ok is False and snapshot(room) == pre.key,
                  "reveal: %s %s by %s during the reveal was not refused cleanly" % (self.tag, ev, actor))
            stats["refused: action during reveal"] += 1
        elif roll < 0.4:
            room.turn_start_ts -= 10000
            self.tick()
            check(snapshot(room) == pre.key, "reveal: %s turn timer fired during the reveal" % self.tag)
            stats["timer during reveal"] += 1
        elif roll < 0.48 and len(room.players) > 2:
            # Someone walks out mid-reveal — sometimes the very player about to pick up.
            lp = room.last_play
            cands = list(room.players)
            if self.reveal and rng.random() < 0.6:
                cands = [u for u in (self.reveal.get("loser"), self.reveal.get("winner")) if u in room.players] or cands
            q = rng.choice(cands)
            stats["quits during reveal"] += 1
            if self.reveal and q == self.reveal.get("loser"):
                stats["quits during reveal: the loser"] += 1
            if self.reveal and q == self.reveal.get("winner"):
                stats["quits during reveal: the winner"] += 1
            self.reveal_quit = q
            self.do_quit(q, pre, "during reveal", check_after=False)
        elif roll < 0.52 and room.host_id in room.players:
            self.call("bluff_shuffle_seats", room.host_id)
            stats["shuffle requests during reveal"] += 1
        self.in_reveal = False

    # ---- a step ------------------------------------------------------------------
    def step(self):
        room, rng = self.room, self.rng
        self.steps += 1
        cur = room.current_turn_id()
        p = room.players[cur]
        pre = Pre(room)
        roll = rng.random()
        if roll < 0.004:
            self.joiners = getattr(self, "joiners", 0) + 1
            uid = "j%d" % self.joiners
            q = self.add_human(uid)
            q.is_spectator = True
            stats["late joiners"] += 1
            self.invariants("late join")
            return
        if roll < 0.012 and len(room.players) > 1:
            # Often the player on turn: the quit that has to hand the turn on.
            q = cur if rng.random() < 0.35 else rng.choice(list(room.players))
            self.do_quit(q, pre, "mid-game")
            return
        if roll < 0.02 and room.host_id in room.players:
            self.do_shuffle(pre)
            return
        if p.is_bot:
            self.bot_step(cur, pre)
            return
        if room.last_play is not None and room.last_play["user_id"] == cur and rng.random() < 0.5:
            # The turn came back round to the claimant with their play still live
            # (flagged by the invariants); their client offers Show — try it.
            self.do_show(cur, pre)
            return
        if roll < 0.045:
            self.do_timeout(cur, pre)
            return
        if roll < 0.13:
            self.illegal(cur, pre)
            return
        self.legal(cur, pre)

    def legal(self, cur, pre):
        room, rng = self.room, self.rng
        p = room.players[cur]
        r = rng.random()
        if room.last_play and room.last_play["user_id"] != cur and r < 0.22:
            self.do_show(cur, pre)
            return
        if r < 0.35 or not p.hand:
            self.do_pass(cur, pre)
            return
        if r < 0.45:
            from game.bluff.ai import decide_move
            mv = decide_move(room, cur)
            if mv["action"] == "show" and room.last_play:
                self.do_show(cur, pre)
                return
            if mv["action"] == "play":
                cards = [c for c in p.hand if c.id in set(mv["cards"])]
                self.do_play(cur, cards, mv["declared_rank"], pre)
                return
            self.do_pass(cur, pre)
            return
        hand = list(p.hand)
        k = len(hand) if rng.random() < 0.08 else rng.randint(1, min(4, len(hand)))
        if room.target_rank is not None:
            honest = [c for c in hand if code_of(c) == room.target_rank]
            cards = honest[:k] if honest and rng.random() < 0.5 else rng.sample(hand, k)
            declared = room.target_rank
        else:
            cards = rng.sample(hand, k)
            declared = code_of(cards[0]) if rng.random() < 0.6 else rng.choice(RANKS)
        self.do_play(cur, cards, declared, pre)

    def illegal(self, cur, pre):
        room, rng = self.room, self.rng
        p = room.players[cur]
        others = [u for u in room.players if u != cur]
        kind = rng.randrange(10)
        label = None
        ok = None
        if kind == 0 and room.target_rank is not None and p.hand:
            wrong = rng.choice([r for r in RANKS if r != room.target_rank])
            ok = self.call("bluff_play", cur, card_ids=[p.hand[0].id], declared_rank=wrong)
            label = "wrong rank on a locked round"
        elif kind == 1:
            foreign = [c for u in others for c in room.players[u].hand] + list(room.center_pile)
            if foreign:
                ok = self.call("bluff_play", cur, card_ids=[rng.choice(foreign).id],
                               declared_rank=room.target_rank or "5")
                label = "foreign card"
        elif kind == 2 and p.hand:
            ok = self.call("bluff_play", cur, card_ids=[p.hand[0].id, p.hand[0].id],
                           declared_rank=room.target_rank or "5")
            label = "duplicate ids"
        elif kind == 3:
            ok = self.call("bluff_play", cur, card_ids=rng.choice([[], None, ["ZZ#9"]]),
                           declared_rank=room.target_rank or "5")
            label = "garbage ids"
        elif kind == 4 and p.hand:
            ok = self.call("bluff_play", cur, card_ids=[p.hand[0].id], declared_rank=rng.choice(["", None]))
            label = "no rank declared"
        elif kind == 5 and p.hand and room.target_rank is None:
            # A rank that does not exist. The reference says no; see the report.
            bogus = rng.choice(["Z", "1", "11", "14", "a", 7, "joker"])
            self.do_play(cur, [p.hand[0]], bogus, pre)
            stats["bogus rank attempts"] += 1
            return
        elif kind == 6:
            if room.last_play is None or self.window is None or self.window["actor"] == cur:
                self.do_show(cur, pre)    # the reference decides; mostly illegal here
                stats["show attempts with no open window"] += 1
                return
        elif kind == 7 and others:
            o = rng.choice(others)
            ev = rng.choice(["bluff_play", "bluff_pass", "bluff_show"])
            ok = self.call(ev, o, card_ids=[c.id for c in room.players[o].hand[:1]],
                           declared_rank=room.target_rank or "5")
            label = "out of turn"
        elif kind == 8:
            o = rng.choice([u for u in room.players if u != room.host_id] or [cur])
            if o != room.host_id:
                ok = self.call(rng.choice(["bluff_shuffle_seats", "bluff_next_round"]), o)
                label = "non-host table control"
            else:
                ok = self.call("bluff_next_round", o)
                label = "next round mid-game"
        elif kind == 9:
            WIRE.errors = []
            try:
                H[rng.choice(["bluff_play", "bluff_pass", "bluff_show"])](
                    rng.choice([None, {"code": "NOPE", "user_id": cur}]))
            except Exception as exc:
                check(False, "crash: bad payload raised %r (%s)" % (exc, self.tag))
            ok = not WIRE.errors
            label = "bad payload"
        if label is None:
            return self.legal(cur, pre)
        stats["refused: " + label] += 1
        check(ok is False, "legality: %s %s was accepted" % (self.tag, label))
        check(snapshot(room) == pre.key, "refusal: %s refused %s changed the table" % (self.tag, label))

    # ---- actions with their reference ----------------------------------------------
    def close_window(self, how, actor):
        """The next player acted without calling Show: the challenged play is final."""
        w = self.window
        self.window = None
        if not w or w["actor"] == actor:
            return
        p = self.room.players.get(w["actor"])
        if p is not None and not p.hand and not p.eliminated:
            stats["finishes confirmed by a %s" % how] += 1
            check(w["actor"] in self.room.finish_order,
                  "finish not banked: %s %s shed their last cards, then %s %s without calling Show, "
                  "but they are not placed (finish order %s)" % (
                      self.tag, w["actor"], actor, how, self.room.finish_order))

    def pass_closes_window(self, actor):
        """Which Show rule the reference holds the engine to.

        The rules text says only the immediate next player may Show, before
        anyone acts (BLUFF_STRICT_SHOW=1 checks that). What the table has always
        done — and what players have been playing for months — is the house
        rule: a pass leaves the live claim open to a later Show, and it closes
        only when the pile is swept. Which one is right is the owner's call
        (docs/todos.md §26); the default checks the game as it is played.
        """
        if STRICT_SHOW:
            self.close_window("passed", actor)
        elif self.room.last_play is None:
            self.window = None        # the pile was swept: nothing left to challenge

    def do_play(self, cur, cards, declared, pre):
        room = self.room
        ids = [c.id for c in cards]
        legal = (bool(cards) and declared in RANKS and
                 (pre.target is None or declared == pre.target))
        ok = self.call("bluff_play", cur, card_ids=ids, declared_rank=declared)
        if ok is None:
            self.over = True
            return
        prefix = "rank validation" if (ok and declared not in RANKS) else "legality"
        check(ok == legal, prefix + ": %s play %s as %r (locked %r): engine %s, reference %s" % (
            self.tag, ids, declared, pre.target, "accepted" if ok else "refused", "legal" if legal else "illegal"))
        if not ok:
            check(snapshot(room) == pre.key, "refusal: %s refused play changed the table" % self.tag)
            return
        stats["plays"] += 1
        stats["plays: honest" if all(code_of(c) == declared for c in cards) else "plays: bluff"] += 1
        if not pre.target:
            stats["leads"] += 1
        p = room.players[cur]
        check({c.id for c in p.hand} == {c.id for c in pre.hands[cur]} - set(ids),
              "play effect: %s hand wrong" % self.tag)
        check([c.id for c in room.center_pile] == pre.center + ids or room.state == STATE_GAME_END,
              "play effect: %s pile is not old pile + throw" % self.tag)
        self.close_window("played", cur)
        self.window = {"actor": cur, "cards": ids, "declared": declared}
        if not p.hand:
            stats["last cards played"] += 1
        # Anyone else sitting on an empty hand is now past their challenge window.
        for u in room.turn_order:
            q = room.players.get(u)
            if q is not None and u != cur and not q.hand and not q.eliminated:
                check(u in room.finish_order, "finish not banked: %s %s empty-handed after a later play" % (self.tag, u))
        if room.state == STATE_IN_TURN:
            check(room.target_rank == (pre.target or declared), "play effect: %s locked rank" % self.tag)
            want = self.ref_next(room.turn_order, cur)
            check(room.current_turn_id() == want, "turn pass: %s after %s's play turn is %s, reference %s" % (
                self.tag, cur, room.current_turn_id(), want))
        self.after(pre, "play %s" % cur)

    def do_pass(self, cur, pre, via="pass"):
        room = self.room
        lp = pre.last_play
        if via == "pass":
            ok = self.call("bluff_pass", cur)
            if ok is None:
                self.over = True
                return
            check(ok, "legality: %s pass refused: %s" % (self.tag, self.last_errors))
            if not ok:
                return
        stats["passes"] += 1
        if lp is None:
            stats["passes on an empty table"] += 1
        self.pass_closes_window(cur)
        self.check_pass_effect(cur, pre)
        self.after(pre, "%s %s" % (via, cur))

    def check_pass_effect(self, cur, pre):
        room = self.room
        lp = pre.last_play
        if lp is None or room.state != STATE_IN_TURN:
            return
        actor = lp["user_id"]
        # Who has passed on this play so far ("every other player passing in succession").
        if self.chain_key is not pre.last_play_obj:      # a new play since the last pass
            self.chain_key, self.passers = pre.last_play_obj, set()
        self.passers.add(cur)
        a = room.players.get(actor)
        if a is None or a.eliminated or actor == cur:
            return     # (the turn reaching the last player unswept is flagged on its own)
        # Reference: the pile is swept exactly when every other player still in
        # the race — present, not removed, not already placed — has passed on it.
        order = pre.order
        others = [u for u in order if u in room.players and not room.players[u].eliminated
                  and u not in pre.finish and u != actor]
        waiting = [u for u in others if u not in self.passers]
        nxt = waiting
        swept = room.last_play is None
        want = not waiting
        check(swept == want, "full pass: %s %s passed; pile %s, reference %s (yet to pass: %s, last play by %s,"
              " pass_count before %s, order %s)" % (
                  self.tag, cur, "swept" if swept else "kept", "sweep" if want else "keep", nxt, actor,
                  pre.key[4], order))
        if swept:
            stats["full-pass sweeps"] += 1
            check(not room.center_pile and room.target_rank is None and
                  [c for c in room.dead_pile][-len(pre.center):] and
                  [c.id for c in room.dead_pile] == pre.dead + pre.center,
                  "full pass: %s pile not moved to the dead pile" % self.tag)
            seats = [u for u in pre.order if u in room.players]   # a queued shuffle keeps the leader
            lead = actor if a.hand else self.ref_next(seats, cur)
            if not a.hand:
                stats["finishes confirmed by a full pass"] += 1
                check(actor in room.finish_order, "full pass: %s %s not placed" % (self.tag, actor))
            check(room.current_turn_id() == lead, "full pass: %s lead to %s, reference %s" % (
                self.tag, room.current_turn_id(), lead))
        else:
            check(room.current_turn_id() == self.ref_next(room.turn_order, cur),
                  "turn pass: %s after %s's pass turn is %s, reference %s" % (
                      self.tag, cur, room.current_turn_id(), self.ref_next(room.turn_order, cur)))

    def do_show(self, cur, pre):
        room = self.room
        w = self.window
        legal = w is not None and w["actor"] != cur and room.last_play is not None
        if room.last_play is not None and room.last_play["user_id"] == cur:
            stats["show on own play attempted"] += 1
        self.reveal = None
        if room.last_play:
            lp = room.last_play
            bluff = any(code_of(c) != lp["declared_rank"] for c in lp["cards"])
            self.reveal = {"loser": lp["user_id"] if bluff else cur, "winner": cur if bluff else lp["user_id"],
                           "bluff": bluff}
        self.crashed = False
        self.reveal_quit = None
        ok = self.call("bluff_show", cur)
        if ok is None:
            stats["games broken by a crash"] += 1
            self.over = True
            return
        own = bool(pre.last_play and pre.last_play["user_id"] == cur)
        prefix = "legality" if legal or not ok else ("self-show" if own else "show window")
        check(ok == legal, prefix + ": %s Show by %s on %s's play: engine %s, reference %s (%s)" % (
            self.tag, cur, pre.last_play and pre.last_play["user_id"], "accepted" if ok else "refused",
            "legal" if legal else ("illegal: Show on their own play" if pre.last_play and pre.last_play["user_id"] == cur else
                                   "illegal: the challenge window closed when the next player acted"),
            self.last_errors))
        if not ok:
            check(snapshot(room) == pre.key, "refusal: %s refused Show changed the table" % self.tag)
            return
        stats["shows"] += 1
        self.window = None
        rv = self.reveal
        stats["shows: bluff caught" if rv["bluff"] else "shows: false accusation"] += 1
        check(not room.is_showing, "show: %s is_showing stuck" % self.tag)
        loser = room.players.get(rv["loser"])
        if loser is not None and room.last_play is None and rv["loser"] in pre.hands:
            if pre.last_play and pre.last_play["user_id"] in room.players:
                want = {c.id for c in pre.hands[rv["loser"]]} | set(pre.center)
                check({c.id for c in loser.hand} == want, "show effect: %s loser %s did not pick up exactly the pile" % (
                    self.tag, rv["loser"]))
        if room.state == STATE_GAME_END and self.reveal_quit:
            stats["games ended by a quit during the reveal"] += 1
            self.after(pre, "show %s (game ended mid-reveal)" % cur)
            return
        check(not room.center_pile and room.target_rank is None and room.last_play is None,
              "show effect: %s pile not cleared (state %s)" % (self.tag, room.state))
        for u in room.turn_order:
            q = room.players.get(u)
            if q is not None and not q.hand and not q.eliminated:
                check(u in room.finish_order, "show effect: %s %s empty-handed but not placed" % (self.tag, u))
        if room.state == STATE_IN_TURN:
            w_id = rv["winner"]
            # Seat order as it was when the Show was called: a queued shuffle
            # re-seats around the new leader, it does not choose them.
            seats = [u for u in pre.order if u in room.players]
            lead = w_id if self.in_race(w_id) else self.ref_next(seats, w_id) if w_id in seats else None
            if lead is not None:
                check(room.current_turn_id() == lead, "show effect: %s lead %s, reference %s (winner %s)" % (
                    self.tag, room.current_turn_id(), lead, w_id))
        self.after(pre, "show %s" % cur)

    def do_timeout(self, cur, pre):
        room = self.room
        room.turn_start_ts -= room.settings["turn_timer"] + 1
        self.tick()
        p = room.players[cur]
        check(p.timeout_count == pre.timeouts[cur] + 1, "timeout: %s count not bumped" % self.tag)
        if p.timeout_count >= room.settings["timeout_limit"]:
            stats["timeout removals"] += 1
            check(p.eliminated, "timeout: %s %s not removed" % (self.tag, cur))
            if room.state == STATE_IN_TURN:
                check(room.current_turn_id() == self.lead_after_departure(pre, cur),
                      "timeout: %s turn after removal is %s, reference %s" % (
                          self.tag, room.current_turn_id(), self.lead_after_departure(pre, cur)))
            self.after(pre, "timeout-removal %s" % cur)
        else:
            stats["timeout auto-passes"] += 1
            self.do_pass(cur, pre, via="timeout")

    def do_shuffle(self, pre):
        room = self.room
        lead = room.current_turn_id()
        fresh = room.last_play is None and not room.center_pile and room.target_rank is None
        was_pending = room.shuffle_pending
        ok = self.call("bluff_shuffle_seats", room.host_id)
        check(ok, "shuffle: %s host's shuffle refused %s" % (self.tag, self.last_errors))
        stats["shuffle requests"] += 1
        if was_pending:
            check(not room.shuffle_pending and room.turn_order == pre.order, "shuffle: %s second press did not cancel" % self.tag)
        elif fresh:
            stats["shuffles applied at once"] += 1
            check(sorted(room.turn_order) == sorted(pre.order) and room.current_turn_id() == lead,
                  "shuffle: %s leader changed %s -> %s" % (self.tag, lead, room.current_turn_id()))
        else:
            check(room.shuffle_pending and room.turn_order == pre.order, "shuffle: %s re-seated mid-play" % self.tag)
        self.invariants("shuffle")

    def do_quit(self, uid, pre, where, check_after=True):
        room = self.room
        was_cur = room.state == STATE_IN_TURN and room.current_turn_id() == uid
        was_host = uid == room.host_id
        owned = room.last_play is not None and room.last_play["user_id"] == uid
        hand = [c.id for c in room.players[uid].hand]
        try:
            room.remove_participant(uid)
        except Exception as exc:
            check(False, "crash: remove_participant(%s) %s raised %r (%s)" % (uid, where, exc, self.tag))
            self.over = True
            return
        self.gone |= set(hand)
        stats["quits " + where] += 1
        if was_cur:
            stats["quits by the player on turn"] += 1
        if was_host:
            stats["host quits"] += 1
        if owned:
            stats["quits by the player who played last"] += 1
            if self.window and self.window["actor"] == uid:
                self.window = None
        if uid in room.finish_order:
            stats["finished players who quit"] += 1
        check(uid not in room.players, "quit: %s %s still here" % (self.tag, uid))
        if check_after:
            if room.state == STATE_IN_TURN and pre.state == STATE_IN_TURN:
                if was_cur:
                    want = self.lead_after_departure(pre, uid)
                    check(room.current_turn_id() == want, "quit: %s turn after %s left is %s, reference %s" % (
                        self.tag, uid, room.current_turn_id(), want))
                elif not (pre.last_play and room.last_play is None):
                    check(room.current_turn_id() == pre.cur, "quit: %s turn moved when %s left" % (self.tag, uid))
            self.after(pre, "quit %s %s" % (where, uid))

    def bot_step(self, bot, pre):
        room = self.room
        if not self.humans_connected():
            return
        self.reveal = None
        lp = room.last_play
        if lp:
            bluff = any(code_of(c) != lp["declared_rank"] for c in lp["cards"])
            self.reveal = {"loser": lp["user_id"] if bluff else bot, "winner": bot if bluff else lp["user_id"],
                           "bluff": bluff}
        window_before = self.window
        gb._bot_act_at[(CODE, bot)] = 0.0
        LAST_BOT_MOVE.clear()
        self.crashed = False
        self.reveal_quit = None
        self.tick()
        gb._bot_act_at.pop((CODE, bot), None)
        if self.crashed:
            stats["games broken by a crash"] += 1
            self.over = True
            return
        stats["bot actions"] += 1
        mv = LAST_BOT_MOVE.get("move") or {}
        kind = mv.get("action", "none")
        if kind == "none":
            check(snapshot(room) == pre.key, "bot: %s %s did not move but the table changed" % (self.tag, bot))
            return
        if kind == "show":
            stats["bot shows"] += 1
            check(window_before is not None and window_before["actor"] != bot,
                  "show window: %s bot %s called Show on %s after the window closed" % (
                      self.tag, bot, pre.last_play and pre.last_play["user_id"]))
            self.window = None
            self.after(pre, "bot show %s" % bot)
        elif kind == "play":
            stats["bot plays"] += 1
            thrown = room.last_play["cards"] if room.last_play and room.last_play["user_id"] == bot else []
            check(pre.target is None or (room.last_play and room.last_play["declared_rank"] == pre.target)
                  or room.state == STATE_GAME_END,
                  "legality: %s bot played off the locked rank" % self.tag)
            self.close_window("played", bot)
            self.window = {"actor": bot, "cards": [c.id for c in thrown],
                           "declared": room.last_play["declared_rank"] if room.last_play else None}
            self.after(pre, "bot play %s" % bot)
        else:
            stats["bot passes"] += 1
            self.pass_closes_window(bot)
            self.check_pass_effect(bot, pre)
            self.after(pre, "bot pass %s" % bot)

    def after(self, pre, tag):
        room = self.room
        if room.state == STATE_GAME_END:
            self.check_standings(tag)
        self.invariants(tag)

    # ---- after the game ------------------------------------------------------------
    def after_game(self):
        room, rng = self.room, self.rng
        stats["games finished"] += 1
        stats["places banked"] += len(room.finish_order)
        if len(room.finish_order) >= PODIUM_PLACES:
            stats["games ended on a full podium"] += 1
        else:
            stats["games ended with one left"] += 1
        self.check_standings("game end")
        for _ in range(rng.choice([0, 0, 1, 2])):
            if not room.players:
                break
            pick = room.winner if (room.winner in room.players and rng.random() < 0.4) else rng.choice(list(room.players))
            if pick == room.winner:
                stats["winner quits on the podium"] += 1
            self.do_quit(pick, Pre(room), "game end")
        if self.rematches < 1 and rng.random() < 0.35 and self.humans_connected():
            self.rematch()
        else:
            self.over = True

    def rematch(self):
        room = self.room
        host = room.players.get(room.host_id)
        if host is None or host.is_bot:
            self.over = True
            return
        self.rematches += 1
        stats["rematches"] += 1
        room.reset_for_rematch()
        orig = room.players.get(room.original_host_id)
        if orig is not None and orig.connected:
            check(room.host_id == room.original_host_id, "rematch: %s original host not restored" % self.tag)
        for q in room.players.values():
            check(not q.eliminated and not q.is_spectator and not q.hand and q.timeout_count == 0,
                  "rematch: %s %s not reset" % (self.tag, q.user_id))
        check(room.state == STATE_LOBBY and not room.finish_order and not room.game_over,
              "rematch: %s not back in the lobby" % self.tag)
        if len(room.connected_players()) < 2:
            self.over = True
            return
        others = [u for u, q in room.players.items() if u != room.host_id and not q.is_bot]
        if others:
            pre = Pre(room)
            ok = self.call("bluff_next_round", others[0])
            check(ok is False and snapshot(room) == pre.key, "legality: %s non-host started the rematch" % self.tag)
        offset = room.start_offset
        ok = self.call("bluff_next_round", room.host_id)
        check(ok, "rematch: %s host could not deal %s" % (self.tag, self.last_errors))
        if not ok:
            self.over = True
            return
        self.after_deal(offset)
        self.invariants("rematch deal")


def play_game(seed):
    t = Table(seed)
    WIRE.table = t
    room = t.room
    for k in list(gb._bot_act_at):
        gb._bot_act_at.pop(k, None)
    offset = room.start_offset
    room.start_round()
    t.after_deal(offset)
    t.invariants("deal")
    steps = 0
    while not t.over:
        steps += 1
        if steps > 30000:
            check(False, "termination: %s game never ended (%d finished, state %s)" % (
                t.tag, len(room.finish_order), room.state))
            break
        if room.state == STATE_IN_TURN:
            if room.is_showing:
                check(False, "stuck: %s room left mid-reveal (is_showing) — every action is refused" % t.tag)
                break
            if not t.humans_connected():
                stats["rooms left to bots (reaped)"] += 1
                break
            t.step()
        elif room.state == STATE_GAME_END:
            t.after_game()
        else:
            check(False, "state: %s unexpected state %s" % (t.tag, room.state))
            break
    stats["games"] += 1
    stats["steps"] += steps


if __name__ == "__main__":
    t0 = time.time()
    games = int(os.environ.get("BLUFF_FUZZ_GAMES", "2000"))
    for seed in range(games):
        play_game(seed)
    print("reached:")
    for k, v in sorted(stats.items()):
        print("  %-48s %d" % (k, v))
    for k in ("games finished", "games ended on a full podium", "games ended with one left", "shows: bluff caught",
              "shows: false accusation", "full-pass sweeps", "finishes confirmed by a full pass",
              "last cards played", "timeout removals", "timeout auto-passes", "quits mid-game",
              "quits by the player on turn", "quits by the player who played last", "quits during reveal",
              "host quits", "rematches", "bot actions", "bot shows", "shuffles applied at once",
              "refused: wrong rank on a locked round", "refused: action during reveal", "late joiners"):
        check(stats[k] > 0, "coverage: the random games never produced any %s" % k)
    passed = sum(results)
    print("%d checks, %d failed, %.1fs" % (len(results), len(results) - passed, time.time() - t0))
    for k, v in failures.most_common():
        print("  %6d x %s" % (v, k))
    print(("PASS " if all(results) else "FAIL ") + "bluff fuzz: %d games" % games)
    exit(0 if all(results) else 1)
