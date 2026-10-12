import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Super Seven engine under fire: thousands of seeded random games.

Every game is driven through the real authority path — the socket handlers in
sockets/gameplay/super_seven.py (play_cards / draw_card / call_stop /
next_round, which is where move validation lives) and the director ticker
(_tick_room: turn timer, the 3 s pick timer, computer players) — with a fake
socketio object, so no server is needed. Quits go through
Room.remove_participant, rematches through Room.reset_for_rematch, exactly as
the lobby handlers call them.

Tables of 2-10 players (bots mixed in) play to the end with random legal AND
illegal moves, quits at any moment (including the player on turn, the player
who owes a draw, the host, between rounds and on the podium), turn-timer and
pick-timer expiries, removals on the timeout limit, late joiners admitted with
a penalty, and rematches. After *every* step the invariants below are checked,
and every round settlement is re-scored from scratch from the rules page
(static/rules/super_seven/en.html) by an independent reference.

Invariants:
  * every card is accounted for exactly once (hands + draw + discard + centre),
    minus the hands of players who quit;
  * while a round is in play the turn belongs to a dealt, present, not-safe,
    not-eliminated, non-spectator player holding cards, and at least two
    players can still act; every round and every game terminates;
  * a move is accepted iff the rules reference says it is legal (Discard 1,
    Pair, Set of 3-4, Sequence 3+ ace-low, Match of centre ranks; Stop only at
    the start of your turn, never in the first orbit); a refused move leaves
    the table exactly as it was;
  * an accepted move does what the rules say: thrown cards become the centre,
    the old centre is buried, the right plays owe a draw, an emptied hand with
    no draw is Safe, and the turn passes to the next player who can act;
  * round scores, Stop outcomes (Safe players exempt), late-join penalties,
    eliminations at max_score (with the everyone-crosses tiebreak), game over
    and winner match the reference;
  * no broadcast or public view carries a card face the table may not see
    (game/super_seven/visibility.py), and private hands go only to their owner;
  * round_end_payload / game_end_payload / standings always build, after any
    quit; the winner heads the standings; there is always a usable host.

Scale with S7_FUZZ_GAMES (default 2000).
"""
import random
import time
import traceback
from collections import Counter

from game.core import bots as botlib
from game.core.cards import build_deck
from game.core.states import STATE_LOBBY, STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END
from game.core.visibility import EVERYTHING
from game.super_seven.room import Room
from game.super_seven.settings import DEFAULT_SETTINGS, HAND_SIZE, MATCH_REQUIRES_DRAW
from game.super_seven.visibility import public_card_ids
import sockets.gameplay.super_seven as gp

results = []
failures = Counter()
stats = Counter()
CODE = "FUZZ"


def check(ok, msg):
    """Record a check; print the first few failures of each kind."""
    results.append(bool(ok))
    if not ok:
        key = msg.split(":")[0]
        failures[key] += 1
        if failures[key] <= int(os.environ.get("FUZZ_SHOW", "3")):
            print("FAIL " + msg)
    return ok


# ---------------------------------------------------------------------------
# Rules reference — written from the rules page, not from game/super_seven/rules.py
# ---------------------------------------------------------------------------
def card_points(c):
    # "Ace = 1 · numbers = face value · Jack = 11 · Queen = 12 · King = 13"
    return c.rank


def ref_play(ranks, center_ranks):
    """None if illegal, else "draw" (owes a draw) or "free" (no draw).

    Discard (1, draw) · Pair (2 same, draw) · Set (3-4 same, no draw) ·
    Sequence (3+ consecutive, ace low, no draw) · Match (every card's rank is in
    the centre, no draw — MATCH_REQUIRES_DRAW is False).
    """
    n = len(ranks)
    if n == 0:
        return None
    distinct = set(ranks)
    is_set = n in (3, 4) and len(distinct) == 1
    is_seq = n >= 3 and len(distinct) == n and max(ranks) - min(ranks) == n - 1
    is_match = bool(center_ranks) and all(r in center_ranks for r in ranks)
    if is_set or is_seq:
        return "free"
    if is_match:
        return "draw" if MATCH_REQUIRES_DRAW else "free"
    if n == 1 or (n == 2 and len(distinct) == 1):
        return "draw"
    return None


def ref_next(order, after, players):
    """Next player after `after` (by seat) who can act: not safe, not eliminated."""
    if after not in order:
        return None
    n = len(order)
    i = order.index(after)
    for k in range(1, n + 1):
        u = order[(i + k) % n]
        p = players.get(u)
        if p is not None and not p.is_safe and not p.eliminated:
            return u
    return None


# ---------------------------------------------------------------------------
# Fake socket plumbing: the real handlers, a recording emit, a leak scan
# ---------------------------------------------------------------------------
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


class Wire:
    """Stands in for socketio + manager; records every emit and scans it."""

    def __init__(self):
        self.table = None
        self.handlers = {}
        self.errors = []
        self.requester = None
        self.events = []

    # socketio surface
    def on(self, name):
        def deco(fn):
            self.handlers[name] = fn
            return fn
        return deco

    def emit(self, event, data=None, to=None, **_kw):
        self.events.append(event)
        t = self.table
        room = t.room if t else None
        if event == "error":
            self.errors.append((data or {}).get("message"))
            return
        if room is None:
            return
        ids = card_ids_in(data, set())
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

    # manager surface
    def get_room(self, code):
        if self.table and code == self.table.room.code:
            return self.table.room
        return None


WIRE = Wire()
gp.emit = WIRE.emit
gp.error = lambda message, reason="": WIRE.emit("error", {"message": message})
gp.register(WIRE, WIRE)
H = WIRE.handlers


def snapshot(room):
    """Everything a refused move must leave untouched."""
    return (
        room.state, room.round_number, room.turn_index, tuple(room.turn_order),
        room.awaiting_draw, room.first_orbit_complete, room.turns_completed,
        tuple(c.id for c in room.draw_pile), tuple(c.id for c in room.discard_pile),
        tuple(c.id for c in room.center_throw), room.host_id, room.game_over, room.winner,
        tuple(sorted(
            (u, tuple(c.id for c in p.hand), p.total_score, p.round_score, p.is_safe,
             p.eliminated, p.timeout_count, p.is_spectator, p.pending_join)
            for u, p in room.players.items())),
    )


class Pre:
    """What the reference needs from just before a step."""

    def __init__(self, room):
        self.key = snapshot(room)
        self.state = room.state
        self.order = list(room.turn_order)
        self.cur = room.current_turn_id() if room.state == STATE_IN_TURN else None
        self.awaiting = room.awaiting_draw
        self.center = [c for c in room.center_throw]
        self.draw = [c.id for c in room.draw_pile]
        self.discard = [c.id for c in room.discard_pile]
        self.hands = {u: [c for c in p.hand] for u, p in room.players.items()}
        self.totals = {u: p.total_score for u, p in room.players.items()}
        self.elim = {u for u, p in room.players.items() if p.eliminated}
        self.spect = {u for u, p in room.players.items() if p.is_spectator}
        self.pending = {u: p.join_penalty_pct for u, p in room.players.items()
                        if p.is_spectator and p.pending_join}
        self.timeouts = {u: p.timeout_count for u, p in room.players.items()}
        self.last_result = getattr(room, "_last_result", None)
        self.host = room.host_id


# ---------------------------------------------------------------------------
# One table
# ---------------------------------------------------------------------------
class Table:
    def __init__(self, seed):
        self.seed = seed
        self.rng = rng = random.Random(seed)
        random.seed(seed * 7919 + 17)          # the engine's deck shuffles, bot pacing
        self.tag = "seed %d" % seed
        settings = dict(DEFAULT_SETTINGS)
        settings.update({
            "max_score": rng.choice([20, 35, 60, 100]),
            "stop_penalty": rng.choice([0, 10, 40, 200]),
            "win_discount": rng.choice([0, 5, 20, 50]),
            "timeout_limit": rng.choice([1, 2, 3, 3]),
        })
        n_humans = rng.choice([1, 2, 2, 3, 3, 4, 5, 6, 8])
        n_bots = rng.choice([0, 0, 0, 1, 2]) if n_humans > 1 else rng.choice([1, 2])
        n = n_humans + n_bots
        settings["num_decks"] = max(1, -(-(n * HAND_SIZE + 6) // 52)) + rng.choice([0, 0, 1])
        self.room = room = Room(CODE, "h0", settings)
        self.sid_owner = {}
        for i in range(n_humans):
            self.add_human("h%d" % i)
        for _ in range(n_bots):
            botlib.add_to(room)
        self.deck_ids = {c.id for c in build_deck(settings["num_decks"])}
        self.gone = set()           # cards that left with a mid-round quitter
        self.dealt = []
        self.had_turn = set()
        self.round_steps = 0
        self.rematches = 0
        self.over = False

    def new_joiner_id(self):
        self.joiners = getattr(self, "joiners", 0) + 1
        return "j%d" % self.joiners

    def add_human(self, uid):
        p = self.room.register_player(uid, uid.upper())
        p.connected = True
        p.sid = "sid-" + uid
        self.sid_owner[p.sid] = uid
        return p

    def humans_connected(self):
        return any(p.connected and not p.is_bot for p in self.room.players.values())

    def call(self, event, actor, **payload):
        """Fire a real handler as `actor`. Returns True if it was accepted."""
        WIRE.errors = []
        WIRE.requester = actor
        data = {"code": CODE, "user_id": actor}
        data.update(payload)
        try:
            H[event](data)
        except Exception as exc:
            check(False, "crash: handler %s raised %s: %s (%s)\n%s" % (
                event, type(exc).__name__, exc, self.tag, traceback.format_exc(limit=3)))
            return False
        return not WIRE.errors

    def tick(self):
        try:
            gp._tick_room(WIRE, self.room)
        except Exception as exc:
            check(False, "crash: director tick raised %s: %s (%s)\n%s" % (
                type(exc).__name__, exc, self.tag, traceback.format_exc(limit=3)))

    # ---- round bookkeeping --------------------------------------------------
    def capacity_ok(self, extra=0):
        room = self.room
        n = sum(1 for p in room.players.values()
                if p.connected and not p.eliminated and (not p.is_spectator or p.pending_join))
        return (n + extra) * HAND_SIZE <= 52 * room.settings["num_decks"]

    def after_deal(self, offset_before):
        room = self.room
        stats["rounds"] += 1
        self.gone = set()
        self.had_turn = set()
        self.round_steps = 0
        self.deck_ids = {c.id for c in build_deck(room.settings["num_decks"])}
        want = [u for u, p in room.players.items()
                if p.connected and not p.eliminated and not p.is_spectator]
        self.dealt = list(room.turn_order)
        check(sorted(self.dealt) == sorted(want),
              "deal: %s dealt %s, expected %s" % (self.tag, self.dealt, want))
        for u, p in room.players.items():
            exp = HAND_SIZE if u in self.dealt else 0
            check(len(p.hand) == exp, "deal: %s %s holds %d cards, expected %d" % (
                self.tag, u, len(p.hand), exp))
            check(not p.is_safe and p.round_score == 0, "deal: %s %s carries round state" % (self.tag, u))
        if self.dealt:
            check(room.current_turn_id() == self.dealt[offset_before % len(self.dealt)],
                  "deal: %s lead did not rotate" % self.tag)
        check(not room.center_throw and not room.discard_pile and not room.awaiting_draw
              and not room.first_orbit_complete,
              "deal: %s fresh round carries old table state" % self.tag)
        check(len(self.dealt) >= 2,
              "round with one player: %s round %d dealt only %s (non-eliminated %s)" % (
                  self.tag, room.round_number, self.dealt, room.non_eliminated()))

    def ref_orbit_done(self):
        room = self.room
        live = [u for u in self.dealt if u in room.players and u in room.turn_order]
        return all(u in self.had_turn for u in live)

    # ---- invariants -----------------------------------------------------------
    def invariants(self, tag):
        room = self.room
        tag = "%s %s" % (self.tag, tag)
        if room.state != STATE_LOBBY:
            cards = list(room.draw_pile) + list(room.discard_pile) + list(room.center_throw)
            for p in room.players.values():
                cards.extend(p.hand)
            ids = [c.id for c in cards]
            dup = len(ids) != len(set(ids))
            check(not dup and set(ids) == self.deck_ids - self.gone and not (set(ids) & self.gone),
                  "cards: %s %d cards (%d distinct), %d expected; missing %s extra %s" % (
                      tag, len(ids), len(set(ids)), len(self.deck_ids - self.gone),
                      sorted(self.deck_ids - self.gone - set(ids))[:4],
                      sorted(set(ids) - (self.deck_ids - self.gone))[:4]))
        check(len(set(room.turn_order)) == len(room.turn_order), "turn order: %s duplicates" % tag)
        check(all(u in room.players for u in room.turn_order),
              "turn order: %s holds a player who left %s" % (tag, room.turn_order))
        if room.state == STATE_IN_TURN:
            cur = room.current_turn_id()
            p = room.players.get(cur)
            ok = (p is not None and cur in self.dealt and not p.is_safe and not p.eliminated
                  and not p.is_spectator)
            check(ok, "turn: %s turn on %s, who cannot act (%s)" % (
                tag, cur, p and dict(safe=p.is_safe, elim=p.eliminated, spect=p.is_spectator)))
            if p is not None and not room.awaiting_draw:
                check(len(p.hand) > 0, "turn: %s %s on turn with an empty hand" % (tag, cur))
            check(room.active_count() >= 2,
                  "turn: %s round in play with %d player(s) able to act" % (tag, room.active_count()))
            for u in room.turn_order:
                q = room.players[u]
                check(not q.is_spectator, "turn order: %s spectator %s dealt in" % (tag, u))
                if q.is_safe:
                    check(not q.hand, "safe: %s %s is safe holding cards" % (tag, u))
            if room.first_orbit_complete != self.ref_orbit_done():
                check(False, "orbit: %s first_orbit_complete=%s, reference says %s (dealt %s, had turn %s)" % (
                    tag, room.first_orbit_complete, self.ref_orbit_done(), self.dealt, sorted(self.had_turn)))
        # Public views never carry a hidden card.
        allowed = public_card_ids(room)
        for label, view in (("public_round_state", room.public_round_state()),
                            ("public_players", room.public_players())):
            leaked = set() if allowed is EVERYTHING else card_ids_in(view, set()) - allowed
            check(not leaked, "leak: %s %s carries %s" % (tag, label, sorted(leaked)[:4]))
        for p in room.players.values():
            v = p.public_view()
            check("hand" not in v and v["card_count"] == len(p.hand), "leak: %s public_view shape" % tag)
        # Summaries always build.
        if room.state == STATE_ROUND_END:
            try:
                pay = room.round_end_payload(room._last_result)
                rows = [r["user_id"] for r in pay["results"]]
                check(rows == [u for u in room.turn_order if u in room.players],
                      "summary: %s rows %s vs turn order %s" % (tag, rows, room.turn_order))
                for r in pay["results"]:
                    check(r["hand_total"] == sum(c["value"] for c in r["hand"]),
                          "summary: %s %s hand_total mismatch" % (tag, r["user_id"]))
            except Exception as exc:
                check(False, "summary: %s round_end_payload raised %s: %s" % (tag, type(exc).__name__, exc))
        if room.state == STATE_GAME_END:
            try:
                room.game_end_payload()
            except Exception as exc:
                check(False, "game-end payload: %s raised %s: %r" % (tag, type(exc).__name__, exc))
        # A usable host whenever a person is still here.
        if self.humans_connected():
            h = room.players.get(room.host_id)
            check(h is not None and not h.is_bot,
                  "host: %s host %r is %s" % (tag, room.host_id, "gone" if h is None else "a bot"))
            if h is not None and h.eliminated and room.state != STATE_LOBBY:
                eligible = [q.user_id for q in room.players.values()
                            if q.connected and not q.is_bot and not q.eliminated
                            and not q.is_spectator]
                check(not eligible, "host: %s host %s eliminated while %s could take over" % (
                    tag, room.host_id, eligible))

    # ---- settlement reference ---------------------------------------------------
    def check_settle(self, pre, elim_before, tag):
        """A round was just scored (end_round ran). Re-score it independently."""
        room = self.room
        tag = "%s %s" % (self.tag, tag)
        caller = room.last_caller
        cfg = room.settings
        order = list(room.turn_order)
        tot = {u: sum(card_points(c) for c in room.players[u].hand) for u in order}
        safe = {u: room.players[u].is_safe for u in order}
        exp = dict(tot)
        if caller is None:
            stats["auto-ends"] += 1
        else:
            # "If your total is strictly lower than all other active players, you
            # win ... Players who are Safe (0 points) are ignored."
            rivals = [u for u in order if u != caller and not safe[u] and u not in elim_before]
            win = all(tot[u] > tot[caller] for u in rivals)
            exp[caller] = max(tot[caller] - cfg["win_discount"], 0) if win else tot[caller] + cfg["stop_penalty"]
            stats["stops won" if win else "stops caught"] += 1
            if any(u in elim_before for u in order if u != caller):
                stats["stops with a removed player still seated"] += 1
            check(room.last_caught == (not win),
                  "stop outcome: %s caller %s total %d vs active rivals %s -> %s, engine says caught=%s"
                  " (removed-by-timeout still seated: %s)" % (
                      tag, caller, tot[caller], {u: tot[u] for u in rivals},
                      "won" if win else "caught", room.last_caught,
                      {u: tot[u] for u in order if u in elim_before}))
        for u in order:
            if u in elim_before:
                continue      # removed mid-round: the rules page is silent on their score
            p = room.players[u]
            if safe[u]:
                stats["safe players scored"] += 1
                check(not p.hand, "safe: %s %s safe with cards" % (tag, u))
            check(p.round_score == exp[u], "round score: %s %s scored %d, reference %d" % (
                tag, u, p.round_score, exp[u]))
        # Totals as they stood after scoring (before any late joiner is admitted).
        after = {}
        for u, p in room.players.items():
            if u in pre.pending:
                continue
            want = pre.totals.get(u, 0) + (exp[u] if (u in order and u not in elim_before) else 0)
            if u in order and u in elim_before:
                want = p.total_score        # unspecified, see above
            after[u] = want
            check(p.total_score == want, "total: %s %s total %d, reference %d" % (
                tag, u, p.total_score, want))
        # Late joiners: average of post-round totals of everyone in play, plus their penalty.
        in_play = [u for u in room.players if u not in elim_before and u not in pre.spect]
        avg = sum(after[u] for u in in_play) / len(in_play) if in_play else 0
        for u, pct in pre.pending.items():
            p = room.players.get(u)
            if p is None:
                continue
            stats["late joiners admitted"] += 1
            want = int(round(avg + avg * pct / 100.0))
            check(not p.is_spectator and not p.pending_join, "join: %s %s not admitted" % (tag, u))
            check(p.total_score == want, "join: %s %s admitted on %d, reference %d" % (
                tag, u, p.total_score, want))
            after[u] = p.total_score
        # Eliminations at max_score; if everyone in play crosses, the single lowest survives.
        cap = cfg["max_score"]
        in_play2 = [u for u, p in room.players.items() if u not in elim_before and not p.is_spectator]
        crossing = [u for u in in_play2 if room.players[u].total_score >= cap]
        if crossing and len(crossing) == len(in_play2):
            survivor = min(in_play2, key=lambda u: room.players[u].total_score)
            out = set(crossing) - {survivor}
            stats["everyone-crossed tiebreaks"] += 1
        else:
            out = set(crossing)
        stats["eliminations"] += len(out)
        for u, p in room.players.items():
            want = u in elim_before or u in out
            check(p.eliminated == want, "elimination: %s %s eliminated=%s, reference %s (total %d, cap %d)" % (
                tag, u, p.eliminated, want, p.total_score, cap))
            if u in out:
                check(room.elim_round.get(u) == room.round_number, "elimination: %s elim_round" % tag)
        check(set(room.newly_eliminated) == out, "elimination: %s newly_eliminated %s, reference %s" % (
            tag, room.newly_eliminated, sorted(out)))
        remaining = [u for u in in_play2 if u not in out]
        over = len(remaining) <= 1
        check(room.game_over == over and room.state == (STATE_GAME_END if over else STATE_ROUND_END),
              "game over: %s game_over=%s state=%s, reference over=%s" % (tag, room.game_over, room.state, over))
        if over:
            check(room.winner == (remaining[0] if remaining else None),
                  "winner: %s %s, reference %s" % (tag, room.winner, remaining))

    def check_standings(self, tag):
        """Winner first; then evictions, most recent first, smaller overshoot first.

        A spectator who never played has no place on the podium: they may be
        left out of the standings or ranked after everyone who played, but
        never above them.
        """
        room = self.room
        tag = "%s %s" % (self.tag, tag)
        rows = room.standings()
        ids = [r["user_id"] for r in rows]
        spect = {u for u, p in room.players.items() if p.is_spectator}
        players = [u for u in room.players if u not in spect]
        check(len(ids) == len(set(ids)) and set(players) <= set(ids) <= set(room.players),
              "standings: %s rows %s vs players %s" % (tag, ids, list(room.players)))
        if room.winner is not None and room.winner in room.players:
            check(ids and ids[0] == room.winner,
                  "standings: %s winner %s is not first, podium order %s (spectators %s)" % (
                      tag, room.winner, ids, sorted(spect)))
        played = [r for r in rows if r["user_id"] not in spect]
        check(rows[:len(played)] == played,
              "standings: %s a spectator who never played ranks above a player %s" % (tag, ids))
        el = [r for r in played if r["eliminated"]]
        check(played[len(played) - len(el):] == el if played else True,
              "standings: %s an eliminated player ranks above a survivor" % tag)
        keys = [(-room.elim_round.get(r["user_id"], 0), r["total_score"]) for r in el]
        check(keys == sorted(keys), "standings: %s evictions out of order" % tag)

    # ---- one step in play ---------------------------------------------------
    def turn_step(self):
        room, rng = self.room, self.rng
        self.round_steps += 1
        cur = room.current_turn_id()
        p = room.players[cur]
        pre = Pre(room)
        roll = rng.random()

        if roll < 0.004 and self.capacity_ok(1):
            # A late joiner arrives mid-round: a spectator until admitted.
            uid = self.new_joiner_id()
            q = self.add_human(uid)
            q.is_spectator = True
            stats["late joiners"] += 1
            self.invariants("late join")
            return
        if roll < 0.014 and len(room.players) > 1:
            # Often the player on turn: the quit that has to hand the turn on.
            q = cur if rng.random() < 0.35 else rng.choice(list(room.players))
            self.do_quit(q, pre, "mid-round")
            return
        if p.is_bot:
            self.bot_step(cur, pre)
            return
        if roll < 0.04:
            self.do_timeout(cur, pre)
            return
        if roll < 0.12:
            self.illegal(cur, pre)
            return
        self.legal(cur, pre)

    def mark_turn_done(self, cur):
        self.had_turn.add(cur)

    def after_action(self, pre, tag, elim_before=None, turn_owner=None):
        """Common tail: settlement check if a round was scored, then invariants."""
        room = self.room
        if elim_before is None:
            elim_before = set(pre.elim)
        if getattr(room, "_last_result", None) is not pre.last_result and room.state != STATE_IN_TURN:
            self.check_settle(pre, elim_before, tag)
            stats["rounds settled"] += 1
        if room.state == STATE_GAME_END:
            self.check_standings(tag)
        self.invariants(tag)

    def legal(self, cur, pre):
        room, rng = self.room, self.rng
        p = room.players[cur]
        if room.awaiting_draw:
            if rng.random() < 0.2:
                # Let the 3 s pick timer take it (no penalty).
                room.awaiting_draw_ts -= 10
                self.tick()
                stats["pick-timer draws"] += 1
                self.check_draw(cur, pre, "pick timer")
                check(p.timeout_count == pre.timeouts[cur], "pick timer: %s penalised" % self.tag)
                return
            ok = self.call("draw_card", cur)
            check(ok, "legal refused: %s draw owed but draw_card refused: %s" % (self.tag, WIRE.errors))
            self.check_draw(cur, pre, "draw")
            return
        hand = list(p.hand)
        center = {c.rank for c in room.center_throw}
        total = sum(card_points(c) for c in hand)
        if room.first_orbit_complete and rng.random() < (0.5 if total <= 12 else 0.08):
            self.do_stop(cur, pre)
            return
        legal, _ = self.enumerate(hand, center)
        if rng.random() < 0.15:
            from game.super_seven.ai import decide_move
            mv = decide_move(room, cur)
            if mv and mv.get("action") == "play":
                cards = mv["cards"]
            elif mv and mv.get("action") == "stop" and self.ref_orbit_done():
                self.do_stop(cur, pre)
                return
            else:
                cards = rng.choice(legal)
        else:
            free = [s for s in legal if ref_play([c.rank for c in s], center) == "free"]
            if free and rng.random() < 0.5:
                cards = max(free, key=len) if rng.random() < 0.5 else rng.choice(free)
            else:
                cards = rng.choice(legal)
        self.do_play(cur, cards, pre)

    def enumerate(self, hand, center):
        """All selections of the hand, split by the reference into legal/illegal."""
        legal, illegal = [], []
        n = len(hand)
        if n <= 10:
            masks = range(1, 1 << n)
        else:
            masks = {self.rng.randrange(1, 1 << n) for _ in range(400)} | {1 << i for i in range(n)}
        for m in masks:
            sel = [hand[i] for i in range(n) if m >> i & 1]
            (legal if ref_play([c.rank for c in sel], center) else illegal).append(sel)
        return legal, illegal

    def do_play(self, cur, cards, pre):
        room = self.room
        center = {c.rank for c in pre.center}
        kind = ref_play([c.rank for c in cards], center)
        ok = self.call("play_cards", cur, card_ids=[c.id for c in cards])
        tag = "play %s %s" % (cur, [c.id for c in cards])
        check(ok == (kind is not None), "legality: %s %s ranks %s on centre %s: engine %s, reference %s (%s)" % (
            self.tag, tag, [c.rank for c in cards], sorted(center),
            "accepted" if ok else "refused", kind or "illegal", WIRE.errors))
        if not ok:
            check(snapshot(room) == pre.key, "refusal: %s refused %s changed the table" % (self.tag, tag))
            return
        stats["plays"] += 1
        stats["plays: %s" % self.kind_name(cards, center)] += 1
        p = room.players[cur]
        thrown = {c.id for c in cards}
        check({c.id for c in p.hand} == {c.id for c in pre.hands[cur]} - thrown,
              "play effect: %s %s hand wrong after throw" % (self.tag, tag))
        check([c.id for c in room.center_throw] == [c.id for c in cards],
              "play effect: %s %s centre is not the throw" % (self.tag, tag))
        check([c.id for c in room.discard_pile] == pre.discard + [c.id for c in pre.center],
              "play effect: %s %s old centre not buried" % (self.tag, tag))
        if kind == "draw":
            check(room.awaiting_draw and room.current_turn_id() == cur and room.state == STATE_IN_TURN
                  or len(self.dealt) < 2,       # a one-player round is reported on its own
                  "play effect: %s %s should owe a draw" % (self.tag, tag))
        else:
            self.mark_turn_done(cur)
            check(not room.awaiting_draw, "play effect: %s %s owes a draw it should not" % (self.tag, tag))
            check(p.is_safe == (not p.hand), "safe: %s %s safe=%s with %d cards left" % (
                self.tag, tag, p.is_safe, len(p.hand)))
            if p.is_safe:
                stats["went safe"] += 1
            if room.state == STATE_IN_TURN:
                want = ref_next(room.turn_order, cur, room.players)
                check(room.current_turn_id() == want, "turn pass: %s %s turn went to %s, reference %s" % (
                    self.tag, tag, room.current_turn_id(), want))
            else:
                check(room.last_caller is None, "auto-end: %s round ended with a caller" % self.tag)
        self.after_action(pre, tag)

    def kind_name(self, cards, center):
        ranks = [c.rank for c in cards]
        n = len(ranks)
        if n >= 3 and len(set(ranks)) == 1:
            return "set"
        if n >= 3 and len(set(ranks)) == n and max(ranks) - min(ranks) == n - 1:
            return "sequence"
        if center and all(r in center for r in ranks):
            return "match"
        return "pair" if n == 2 else "single"

    def check_draw(self, cur, pre, label):
        room = self.room
        tag = "%s %s %s" % (self.tag, label, cur)
        self.mark_turn_done(cur)
        p = room.players.get(cur)
        before = {c.id for c in pre.hands[cur]}
        now = {c.id for c in p.hand}
        if pre.draw:
            check(now == before | {pre.draw[-1]}, "draw: %s did not take the top card" % tag)
        elif pre.discard:
            stats["reshuffles"] += 1
            new = now - before
            check(len(new) == 1 and new <= set(pre.discard) and len(now) == len(before) + 1,
                  "draw: %s reshuffle draw wrong" % tag)
            check(not (set(c.id for c in room.draw_pile) & {c.id for c in room.center_throw}),
                  "draw: %s centre reshuffled into the deck" % tag)
        else:
            stats["draws from empty piles"] += 1
            check(now == before, "draw: %s drew from nothing" % tag)
        check(not room.awaiting_draw, "draw: %s still owes a draw" % tag)
        if room.state == STATE_IN_TURN:
            want = ref_next(room.turn_order, cur, room.players)
            check(room.current_turn_id() == want, "turn pass: %s turn went to %s, reference %s" % (
                tag, room.current_turn_id(), want))
        self.after_action(pre, "%s %s" % (label, cur))

    def do_stop(self, cur, pre):
        room = self.room
        p = room.players[cur]
        legal = (not room.awaiting_draw) and self.ref_orbit_done() and not p.is_safe
        ok = self.call("call_stop", cur)
        prefix = "orbit" if (ok and not legal and not self.ref_orbit_done()) else "legality"
        check(ok == legal, prefix + ": %s stop by %s: engine %s, reference %s (awaiting %s, orbit %s)" % (
            self.tag, cur, "accepted" if ok else "refused", "legal" if legal else "illegal",
            room.awaiting_draw, self.ref_orbit_done()))
        if not ok:
            check(snapshot(room) == pre.key, "refusal: %s refused stop changed the table" % self.tag)
            return
        stats["stops"] += 1
        check(room.last_caller == cur and room.state in (STATE_ROUND_END, STATE_GAME_END),
              "stop: %s did not end the round" % self.tag)
        self.after_action(pre, "stop %s" % cur)

    def illegal(self, cur, pre):
        """Something the server must refuse without touching the table."""
        room, rng = self.room, self.rng
        p = room.players[cur]
        others = [u for u in room.players if u != cur]
        center = {c.rank for c in room.center_throw}
        kind = rng.randrange(11)
        label = None
        if kind == 0 and not room.awaiting_draw:
            _, bad = self.enumerate(list(p.hand), center)
            if bad:
                sel = rng.choice(bad)
                self.do_play(cur, sel, pre)        # reference judges it; must be refused
                stats["refused: illegal combination"] += 1
                return
            kind = 1
        if kind == 1:
            foreign = [c for u in others for c in room.players[u].hand] + list(room.draw_pile)
            if foreign:
                ids = [rng.choice(foreign).id] + [c.id for c in p.hand[:rng.randint(0, 1)]]
                ok = self.call("play_cards", cur, card_ids=ids)
                label = "foreign card"
        if kind == 2 and p.hand:
            ok = self.call("play_cards", cur, card_ids=[p.hand[0].id, p.hand[0].id])
            label = "duplicate ids"
        elif kind == 3:
            ok = self.call("play_cards", cur, card_ids=rng.choice([[], None, "", ["ZZ#9"], "7H#0"]))
            label = "garbage ids"
        elif kind == 4:
            if room.awaiting_draw:
                ok = self.call("play_cards", cur, card_ids=[p.hand[0].id] if p.hand else ["x"])
                label = "play while owing a draw"
            else:
                ok = self.call("draw_card", cur)
                label = "draw with nothing owed"
        elif kind == 5:
            if not self.ref_orbit_done() or room.awaiting_draw:
                self.do_stop(cur, pre)
                stats["refused: early/owing stop"] += 1
                return
            ok = self.call("call_stop", others[0] if others else "nobody")
            label = "stop out of turn"
        elif kind == 6 and others:
            o = rng.choice(others)
            ids = [c.id for c in room.players[o].hand[:1]]
            ok = self.call(rng.choice(["play_cards", "draw_card", "call_stop"]), o, card_ids=ids)
            label = "out of turn"
        elif kind == 7:
            WIRE.errors = []
            try:
                H["play_cards"]({"code": "NOPE", "user_id": cur, "card_ids": [c.id for c in p.hand[:1]]})
            except Exception as exc:
                check(False, "crash: unknown room raised %r" % exc)
            ok = not WIRE.errors
            label = "unknown room"
        elif kind == 8:
            ok = self.call("next_round", room.host_id)
            label = "next round mid-play"
        elif kind == 9:
            try:
                H["play_cards"](None)
                ok = False
            except Exception as exc:
                check(False, "crash: play_cards(None) raised %r" % exc)
                ok = False
            label = "no payload"
        elif kind == 10 and room.awaiting_draw:
            ok = self.call("call_stop", cur)
            label = "stop while owing a draw"
        if label is None:
            return self.legal(cur, pre)
        stats["refused: " + label] += 1
        check(not ok, "legality: %s %s was accepted" % (self.tag, label))
        check(snapshot(room) == pre.key, "refusal: %s refused %s changed the table" % (self.tag, label))

    def do_timeout(self, cur, pre):
        room = self.room
        p = room.players[cur]
        if room.awaiting_draw:
            room.awaiting_draw_ts -= 10
            self.tick()
            stats["pick-timer draws"] += 1
            self.check_draw(cur, pre, "pick timer")
            return
        room.turn_start_ts -= room.settings["turn_timer"] + 1
        self.tick()
        tag = "timeout %s" % cur
        check(p.timeout_count == pre.timeouts[cur] + 1, "timeout: %s count not bumped" % self.tag)
        elim_before = set(pre.elim)
        self.mark_turn_done(cur)
        if p.timeout_count >= room.settings["timeout_limit"]:
            stats["timeout removals"] += 1
            check(p.eliminated, "timeout: %s %s not removed at the limit" % (self.tag, cur))
            elim_before.add(cur)
            if room.state == STATE_IN_TURN:
                check(room.current_turn_id() != cur, "timeout: %s removed player keeps the turn" % self.tag)
        else:
            stats["timeout auto-discards"] += 1
            hi = max(card_points(c) for c in pre.hands[cur])
            thrown = {c.id for c in pre.hands[cur]} - {c.id for c in p.hand}
            check(len(thrown) == 1 and all(card_points(c) == hi for c in pre.hands[cur] if c.id in thrown),
                  "timeout: %s auto-discard did not throw a highest card" % self.tag)
        self.after_action(pre, tag, elim_before=elim_before)

    def do_quit(self, uid, pre, where):
        room = self.room
        was_cur = room.state == STATE_IN_TURN and room.current_turn_id() == uid
        hand = [c.id for c in room.players[uid].hand]
        was_host = room.host_id == uid
        try:
            room.remove_participant(uid)
        except Exception as exc:
            check(False, "crash: remove_participant(%s) %s raised %r (%s)" % (uid, where, exc, self.tag))
            self.over = True
            return
        stats["quits " + where] += 1
        if was_cur:
            stats["quits by the player on turn"] += 1
            if pre.awaiting:
                stats["quits while owing a draw"] += 1
        if was_host:
            stats["host quits"] += 1
        self.gone |= set(hand)          # their cards leave the table with them
        check(uid not in room.players and uid not in room.turn_order,
              "quit: %s %s still seated" % (self.tag, uid))
        if pre.state == STATE_IN_TURN and room.state == STATE_IN_TURN:
            if was_cur:
                want = ref_next(pre.order, uid, room.players)
                check(room.current_turn_id() == want and not room.awaiting_draw,
                      "quit: %s turn after %s left went to %s, reference %s" % (
                          self.tag, uid, room.current_turn_id(), want))
            else:
                check(room.current_turn_id() == pre.cur and room.awaiting_draw == pre.awaiting,
                      "quit: %s turn moved off %s when %s left" % (self.tag, pre.cur, uid))
        if pre.state == STATE_IN_TURN:
            remaining = [u for u, p in room.players.items() if not p.eliminated and not p.is_spectator]
            if len(remaining) <= 1:
                check(room.state == STATE_GAME_END and room.winner == (remaining[0] if remaining else None),
                      "quit: %s %s left one player but the game did not end" % (self.tag, uid))
        self.after_action(pre, "quit %s %s" % (where, uid))

    def bot_step(self, bot, pre):
        room = self.room
        if not self.humans_connected():
            return
        gp._bot_act_at[(CODE, bot)] = 0.0
        self.tick()
        gp._bot_act_at.pop((CODE, bot), None)
        stats["bot actions"] += 1
        tag = "bot %s" % bot
        if pre.awaiting:
            self.check_draw(bot, pre, "bot draw")
            return
        if room.state != STATE_IN_TURN and room.last_caller == bot and room._last_result is not pre.last_result:
            stats["bot stops"] += 1
            check(self.ref_orbit_done(), "legality: %s bot %s called Stop in the first orbit" % (self.tag, bot))
            self.after_action(pre, tag)
            return
        before = {c.id: c for c in pre.hands[bot]}
        now = {c.id for c in room.players[bot].hand}
        thrown = [before[i] for i in before if i not in now]
        if not thrown:
            check(snapshot(room) == pre.key, "bot: %s %s did nothing but changed the table" % (self.tag, bot))
            return
        center = {c.rank for c in pre.center}
        kind = ref_play([c.rank for c in thrown], center)
        check(kind is not None, "legality: %s bot %s threw illegal %s on %s" % (
            self.tag, bot, [c.rank for c in thrown], sorted(center)))
        if kind == "draw":
            check(room.awaiting_draw and room.current_turn_id() == bot
                  or room.state != STATE_IN_TURN and room.active_count() <= 1,
                  "bot: %s owes no draw after a %s" % (self.tag, [c.rank for c in thrown]))
        else:
            self.mark_turn_done(bot)
            check(not room.awaiting_draw, "bot: %s owes a draw after a free play" % self.tag)
        self.after_action(pre, tag)

    # ---- between rounds / after the game ------------------------------------
    def between_rounds(self):
        room, rng = self.room, self.rng
        pre = Pre(room)
        if rng.random() < 0.12 and len(room.players) > 1:
            self.do_quit(rng.choice(list(room.players)), pre, "between rounds")
            if room.state != STATE_ROUND_END:
                return
            if not self.humans_connected():
                self.over = True      # bots alone: the reaper closes the room
                return
            pre = Pre(room)
        if rng.random() < 0.08 and self.capacity_ok(1):
            uid = self.new_joiner_id()
            if uid not in room.players:
                q = self.add_human(uid)
                q.is_spectator = True
                stats["late joiners"] += 1
        for q in room.players.values():
            if q.is_spectator and not q.pending_join and rng.random() < 0.5 and self.capacity_ok():
                # Host admits them with a penalty; they enter at the next round end.
                q.pending_join = True
                q.join_penalty_pct = rng.choice([0, 10, 25, 50])
        if not self.humans_connected():
            self.over = True
            return
        pre = Pre(room)
        # A non-host cannot deal.
        others = [u for u, q in room.players.items() if u != room.host_id and not q.is_bot]
        if others and rng.random() < 0.2:
            ok = self.call("next_round", rng.choice(others))
            check(not ok and snapshot(room) == pre.key, "legality: %s non-host dealt the next round" % self.tag)
            stats["refused: non-host next round"] += 1
        if rng.random() < 0.03:
            self.rematch("from the round summary")
            return
        if rng.random() < 0.05:
            ok = self.call("play_cards", room.host_id, card_ids=[])
            check(not ok and snapshot(room) == pre.key, "legality: %s play between rounds accepted" % self.tag)
        if room.round_number > 60:
            check(False, "termination: %s game still running after 60 rounds" % self.tag)
            self.over = True
            return
        offset = room.start_offset
        host = room.players.get(room.host_id)
        if host is None or host.is_bot or not host.connected:
            check(False, "host: %s nobody can deal the next round (host %r)" % (self.tag, room.host_id))
            room.start_round()
        else:
            ok = self.call("next_round", room.host_id, shuffle=rng.random() < 0.2)
            check(ok, "next round: %s host's next_round refused: %s" % (self.tag, WIRE.errors))
            if not ok:
                self.over = True
                return
        self.after_deal(offset)
        self.invariants("new round")

    def rematch(self, where):
        room = self.room
        host = room.players.get(room.host_id)
        if host is None or host.is_bot:
            self.over = True
            return
        if self.rematches >= 1:
            self.over = True
            return
        self.rematches += 1
        stats["rematches"] += 1
        room.reset_for_rematch()
        orig = room.players.get(room.original_host_id)
        if orig is not None and orig.connected:
            check(room.host_id == room.original_host_id, "rematch: %s original host not restored" % self.tag)
        for q in room.players.values():
            check(q.total_score == 0 and not q.eliminated and not q.is_spectator and not q.hand,
                  "rematch: %s %s not reset" % (self.tag, q.user_id))
        check(room.state == STATE_LOBBY and room.round_number == 0 and not room.game_over,
              "rematch: %s room not back in the lobby" % self.tag)
        self.invariants("rematch " + where)
        if len(room.connected_players()) < 2 or not self.capacity_ok():
            self.over = True
            return
        offset = room.start_offset
        room.start_round()
        self.after_deal(offset)
        self.invariants("rematch deal")

    def after_game(self):
        room, rng = self.room, self.rng
        stats["games finished"] += 1
        self.check_standings("game end")
        # People leave the podium — sometimes the winner, sometimes the host.
        for _ in range(rng.choice([0, 0, 1, 2])):
            if not room.players:
                break
            pick = room.winner if (room.winner in room.players and rng.random() < 0.4) else rng.choice(list(room.players))
            if pick == room.winner:
                stats["winner quits on the podium"] += 1
            self.do_quit(pick, Pre(room), "game end")
        if rng.random() < 0.35 and self.humans_connected():
            self.rematch("from the podium")
        else:
            self.over = True


def play_game(seed):
    t = Table(seed)
    WIRE.table = t
    room = t.room
    for k in list(gp._bot_act_at):
        gp._bot_act_at.pop(k, None)
    offset = room.start_offset
    room.start_round()
    t.after_deal(offset)
    t.invariants("first deal")
    steps = 0
    while not t.over:
        steps += 1
        if steps > 40000:
            check(False, "termination: %s game never ended (round %d, state %s)" % (t.tag, room.round_number, room.state))
            break
        if room.state == STATE_IN_TURN:
            if t.round_steps > 3000:
                check(False, "termination: %s round %d never ended" % (t.tag, room.round_number))
                break
            if not t.humans_connected():
                stats["rooms left to bots (reaped)"] += 1
                break
            t.turn_step()
        elif room.state == STATE_ROUND_END:
            t.between_rounds()
        elif room.state == STATE_GAME_END:
            t.after_game()
        else:
            break
    stats["games"] += 1


def deal_capacity_check():
    """MAX_PLAYERS is 20 and num_decks may be 1: the deal must not crash."""
    from game.super_seven.settings import MAX_PLAYERS, SETTINGS_BOUNDS
    for n in (7, 8, MAX_PLAYERS):
        room = Room("CAP", "h0", dict(DEFAULT_SETTINGS, num_decks=SETTINGS_BOUNDS["num_decks"][0]))
        for i in range(n):
            room.register_player("h%d" % i, "H").connected = True
        try:
            room.start_round()
            ok = True
        except Exception as exc:
            ok = False
            err = "%s: %s" % (type(exc).__name__, exc)
        check(ok, "deal capacity: %d players, num_decks=1 (allowed by MAX_PLAYERS/SETTINGS_BOUNDS) -> %s" % (
            n, "ok" if ok else err + "; room left in %s with hands %s" % (
                room.state, [len(p.hand) for p in room.players.values()])))


if __name__ == "__main__":
    t0 = time.time()
    deal_capacity_check()
    games = int(os.environ.get("S7_FUZZ_GAMES", "2000"))
    for seed in range(games):
        play_game(seed)
    print("reached:")
    for k, v in sorted(stats.items()):
        print("  %-45s %d" % (k, v))
    for k in ("rounds settled", "stops won", "stops caught", "auto-ends", "went safe", "eliminations",
              "everyone-crossed tiebreaks", "reshuffles", "timeout removals", "timeout auto-discards",
              "pick-timer draws", "quits mid-round", "quits between rounds", "quits by the player on turn",
              "quits while owing a draw", "host quits", "late joiners admitted", "rematches", "bot actions",
              "plays: set", "plays: sequence", "plays: match", "plays: pair", "plays: single",
              "refused: illegal combination", "games finished"):
        check(stats[k] > 0, "coverage: the random games never produced any %s" % k)
    passed = sum(results)
    print("%d checks, %d failed, %.1fs" % (len(results), len(results) - passed, time.time() - t0))
    for k, v in failures.most_common():
        print("  %6d x %s" % (v, k))
    print(("PASS " if all(results) else "FAIL ") + "super seven fuzz: %d games" % games)
    exit(0 if all(results) else 1)
