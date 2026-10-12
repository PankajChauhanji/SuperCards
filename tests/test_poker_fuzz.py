import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Poker engine under fire: a reference evaluator and thousands of random games.

Two halves.

1. **The evaluator against a brute-force reference.** ``reference_value`` scores
   every five-card subset with a deliberately naive scorer written separately
   from game/poker/evaluator.py, and keeps the best. Random hands are drawn both
   uniformly and from a narrowed rank/suit pool, so straights, flushes, full
   houses and quads (rare in uniform deals) are hit thousands of times. The
   evaluator's ``value`` must equal the reference, its five ``cards`` must be
   cards of the input that score that same value on their own, and its ``name``
   must name that category — the summary highlights those cards and prints that
   name, so a mismatch is exactly "it says I made a pair I never had".

2. **Random games.** Tables of 2–9 players with small stacks (so busts, all-ins
   and side pots happen constantly) play to the end with random moves —
   legal ones, illegal ones that must be refused, raises of random size,
   timeouts, sit-outs, quits at any moment, late joiners. After *every* step the
   invariants below are checked, and every showdown is re-judged from scratch.

Invariants:
  * coins are conserved: stacks + money in the pot always equals everything
    handed out, minus the stacks of players who quit;
  * no stack, bet or contribution is ever negative;
  * while betting, exactly one player is on turn, they are live, have coins,
    and still owe an action; ``legal_actions`` is self-consistent;
  * the public pot equals the sum of the pots in the middle plus the bets in
    front of the seats;
  * the 52 cards are all accounted for, once each;
  * the public state never carries a card that is not face up;
  * a showdown pays each pot to the best eligible hand(s), by the reference
    evaluator, and pays out exactly the pot;
  * each player's own hand label (the hint) names the same hand the summary
    shows for them;
  * every round finishes, and every game ends.
"""
import itertools
import random
from collections import Counter

from game.core.cards import Card, build_deck
from game.core.states import STATE_IN_TURN, STATE_ROUND_END, STATE_GAME_END, STATE_LOBBY
from game.poker import ai
from game.poker import pots as potlib
from game.poker.evaluator import evaluate, CATEGORY_NAMES
from game.poker.room import Room, PHASE_BETTING, PHASE_RUNOUT
from game.poker.settings import DEFAULT_SETTINGS
from game.poker.visibility import public_card_ids

results = []
failures = Counter()
stats = Counter()          # what the random games actually reached


def check(ok, msg):
    """Record a check; print failures (and only a summary of passes)."""
    results.append(bool(ok))
    if not ok:
        failures[msg.split(":")[0]] += 1
        if failures[msg.split(":")[0]] <= 5:
            print("FAIL " + msg)


# ---------------------------------------------------------------------------
# 1. Reference evaluator
# ---------------------------------------------------------------------------
def _r(c):
    return 14 if c.rank == 1 else c.rank


def score5(five):
    """Naive five-card scorer, independent of the engine's evaluator."""
    ranks = sorted((_r(c) for c in five), reverse=True)
    flush = len({c.suit for c in five}) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_top = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_top = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_top = 5
    counts = Counter(ranks)
    # Ranks ordered by (count, rank), highest first.
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = [n for _, n in groups]
    order = tuple(r for r, _ in groups)
    if straight_top and flush:
        return (8, straight_top)
    if shape == [4, 1]:
        return (7,) + order
    if shape == [3, 2]:
        return (6,) + order
    if flush:
        return (5,) + tuple(ranks)
    if straight_top:
        return (4, straight_top)
    if shape == [3, 1, 1]:
        return (3,) + order
    if shape == [2, 2, 1]:
        return (2,) + order
    if shape == [2, 1, 1, 1]:
        return (1,) + order
    return (0,) + tuple(ranks)


def reference_value(cards):
    return max(score5(list(f)) for f in itertools.combinations(cards, 5))


def narrow_hand(rng, n):
    """n distinct cards from a small pool of ranks/suits — dense in big hands."""
    deck = build_deck(1)
    mode = rng.random()
    if mode < 0.35:          # few suits -> flushes, straight flushes
        suits = set(rng.sample("SHDC", 2))
        pool = [c for c in deck if c.suit in suits]
    elif mode < 0.7:         # a window of ranks -> straights, wheels
        lo = rng.randint(1, 10)
        window = {((lo + i - 1) % 13) + 1 for i in range(6)}
        pool = [c for c in deck if c.rank in window]
    else:                    # few ranks -> pairs, trips, full houses, quads
        ranks = set(rng.sample(range(1, 14), 4))
        pool = [c for c in deck if c.rank in ranks]
    return rng.sample(pool, n)


def check_evaluator(rng, samples):
    cats = Counter()
    for i in range(samples):
        n = rng.choice((5, 6, 7, 7, 7))
        hand = narrow_hand(rng, n) if i % 2 else rng.sample(build_deck(1), n)
        got = evaluate(hand)
        want = reference_value(hand)
        cats[got.value[0]] += 1
        ok = got.value[0] == want[0] and _same_strength(got.value, want)
        check(ok, "evaluator value: %s -> %s, reference %s" % (
            " ".join(c.face for c in hand), got.value, want))
        ids = {id(c) for c in hand}
        check(len(got.cards) == 5 and all(id(c) in ids for c in got.cards)
              and len({id(c) for c in got.cards}) == 5,
              "evaluator cards: best five are five distinct input cards (%s)" % got.name)
        check(_same_strength(score5(got.cards), want),
              "evaluator best-five: %s scores %s, hand is %s" % (
                  " ".join(c.face for c in got.cards), score5(got.cards), want))
        cat_name = CATEGORY_NAMES[got.value[0]]
        check(got.name.startswith(cat_name) or (got.value[0] == 8 and got.name == "Royal Flush"),
              "evaluator name: %r for category %s" % (got.name, cat_name))
    return cats


def _same_strength(a, b):
    """Engine and reference encode tiebreaks the same way for every category
    except where the reference lists the full group order; compare by category
    and by ordering against each other via the engine's own tuple shape."""
    return a == b


# ---------------------------------------------------------------------------
# 2. Random games
# ---------------------------------------------------------------------------
class Ledger:
    """What the table should hold: coins handed out minus stacks forfeited."""

    def __init__(self):
        self.total = 0


def all_cards(room):
    out = list(room.deck) + list(room.burns) + list(room.board)
    for h in room.hole.values():
        out.extend(h)
    return out


def money_on_table(room):
    if room.state == STATE_IN_TURN:
        return sum(room.chips.values()) + sum(room.contributed.values())
    return sum(room.chips.values())


def card_ids_in(node, out):
    if isinstance(node, dict):
        if isinstance(node.get("rank"), int) and isinstance(node.get("suit"), str) and "id" in node:
            out.add(node["id"])
            return out
        for v in node.values():
            card_ids_in(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            card_ids_in(v, out)
    return out


def check_invariants(room, ledger, tag):
    check(money_on_table(room) == ledger.total,
          "conservation: %s table holds %d, expected %d" % (tag, money_on_table(room), ledger.total))
    check(all(v >= 0 for v in room.chips.values()), "negative stack: %s %s" % (tag, room.chips))
    check(all(v >= 0 for v in room.bets.values()), "negative bet: %s %s" % (tag, room.bets))
    check(all(v >= 0 for v in room.contributed.values()),
          "negative contribution: %s %s" % (tag, room.contributed))

    if room.state == STATE_IN_TURN:
        deck = all_cards(room)
        check(len(deck) == 52 and len({c.id for c in deck}) == 52,
              "cards: %s %d cards, %d distinct" % (tag, len(deck), len({c.id for c in deck})))
        board_ok = {
            "preflop": 0, "flop": 3, "turn": 4, "river": 5,
        }.get(room.street) == len(room.board)
        check(board_ok, "board size: %s street %s with %d cards" % (tag, room.street, len(room.board)))

    if room.state == STATE_IN_TURN and room.phase == PHASE_BETTING:
        cur = room.current
        check(cur is not None, "turn: %s betting with nobody on turn" % tag)
        if cur is not None:
            check(cur in room.live(), "turn: %s %s on turn but not live" % (tag, cur))
            check(room.chips.get(cur, 0) > 0, "turn: %s %s on turn with no coins" % (tag, cur))
            check(room._needs_action(cur), "turn: %s %s on turn but owes nothing" % (tag, cur))
            a = room.legal_actions(cur)
            check(a is not None, "legal: %s none for the player on turn" % tag)
            if a:
                check(a["min_to"] <= a["max_to"], "legal: %s min_to %d > max_to %d" % (tag, a["min_to"], a["max_to"]))
                check(a["call"] <= a["stack"], "legal: %s call above stack" % tag)
                check(a["check"] == (a["to_call"] == 0), "legal: %s check flag vs to_call" % tag)
                check(a["max_to"] == a["bet"] + a["stack"], "legal: %s max_to is not bet+stack" % tag)
                if a["raise"]:
                    check(a["max_to"] > room.current_bet, "legal: %s raise allowed with nothing to raise" % tag)
        check(len(room.live()) >= 2, "turn: %s betting with fewer than two live players" % tag)
        check(len(room.live_not_allin()) >= 1, "turn: %s betting with nobody able to bet" % tag)
    elif room.state == STATE_IN_TURN:
        check(room.phase == PHASE_RUNOUT, "phase: %s IN_TURN with phase %r" % (tag, room.phase))
        check(room.current_turn_id() is None, "phase: %s runout with a turn" % tag)
        check(set(room.shown) == set(room.live()), "runout: %s hands shown %s vs live %s" % (
            tag, sorted(room.shown), sorted(room.live())))

    pub = room.public_round_state()
    if room.state == STATE_IN_TURN:
        in_pots = sum(p["amount"] for p in pub["pots"])
        in_front = sum(p["bet"] for p in pub["players"])
        # A quitter's street bet is no longer in front of any seat, but it is in the pot.
        gone = sum(room.bets.get(u, 0) for u in room.in_hand if u not in room.players)
        check(in_pots + in_front + gone == pub["pot_total"],
              "pot display: %s pots %d + bets %d + gone %d != total %d" % (
                  tag, in_pots, in_front, gone, pub["pot_total"]))
    leaked = card_ids_in(pub, set()) - public_card_ids(room)
    check(not leaked, "leak: %s public state carries %s" % (tag, sorted(leaked)))
    if room.state == STATE_ROUND_END:
        leaked = card_ids_in(room.round_end_payload(), set()) - public_card_ids(room)
        check(not leaked, "leak: %s round summary carries %s" % (tag, sorted(leaked)))
    if room.state == STATE_GAME_END:
        leaked = card_ids_in(room.game_end_payload(), set()) - public_card_ids(room)
        check(not leaked, "leak: %s game-end payload carries %s" % (tag, sorted(leaked)))


def judge_showdown(room, snapshot, tag):
    """Re-judge a finished showdown from the cards, with the reference scorer."""
    res = room.last_result
    if not res or res.get("fold_win"):
        return
    board = snapshot["board"]
    live = snapshot["live"]
    holes = snapshot["hole"]
    ref = {u: reference_value(holes[u] + board) for u in live}
    pots = potlib.build_pots(snapshot["contributed"], snapshot["folded"])
    stats["showdowns"] += 1
    stats["side pots"] += max(0, len(pots) - 1)
    check(len(pots) == len(res["awards"]),
          "showdown pots: %s %d pots built, %d awarded" % (tag, len(pots), len(res["awards"])))
    for pot, award in zip(pots, res["awards"]):
        contenders = [u for u in pot["eligible"] if u in ref] or list(ref)
        best = max(ref[u] for u in contenders)
        want = sorted(u for u in contenders if ref[u] == best)
        if len(want) > 1:
            stats["split pots"] += 1
        check(sorted(award["winners"]) == want,
              "showdown winners: %s pot %d won by %s, reference says %s (board %s, holes %s)" % (
                  tag, pot["amount"], award["winners"], want,
                  " ".join(c.face for c in board),
                  {u: " ".join(c.face for c in holes[u]) for u in contenders}))
        check(sum(award["payouts"].values()) == pot["amount"],
              "showdown payout: %s pays %d of a %d pot" % (tag, sum(award["payouts"].values()), pot["amount"]))
        check(award["amount"] == pot["amount"], "showdown amount: %s" % tag)
    for uid in live:
        shown = res["hands"].get(uid)
        check(shown is not None, "showdown hands: %s live %s missing from summary" % (tag, uid))
        if not shown:
            continue
        mine = {c.id for c in holes[uid]}
        check({c["id"] for c in shown["cards"]} == mine,
              "showdown hands: %s %s summary shows cards that are not theirs" % (tag, uid))
        pool = mine | {c.id for c in board}
        check(set(shown["best"]) <= pool and len(shown["best"]) == 5,
              "showdown best: %s %s best five not from their cards + board" % (tag, uid))
        hint = snapshot["labels"].get(uid)
        check(hint == shown["name"],
              "hint vs summary: %s %s was told %r, summary says %r" % (tag, uid, hint, shown["name"]))
        ref_cat = CATEGORY_NAMES[ref[uid][0]]
        check(shown["name"].startswith(ref_cat) or shown["name"] == "Royal Flush",
              "summary name: %s %s summary %r, reference %s" % (tag, uid, shown["name"], ref_cat))


def random_move(room, uid, rng):
    a = room.legal_actions(uid)
    roll = rng.random()
    if roll < 0.04:
        # Garbage the server must refuse without changing anything.
        return rng.choice([("check", None), ("raise", -5), ("raise", "abc"), ("bet", 10 ** 12),
                           ("call", None), ("dance", None), ("raise", a["min_to"] - 1)])
    if roll < 0.10:
        return ("fold", None)
    if roll < 0.18:
        return ("allin", None)
    if roll < 0.40 and a["raise"]:
        lo, hi = a["min_to"], a["max_to"]
        return ("raise", rng.choice([lo, hi, rng.randint(lo, hi), (lo + hi) // 2]))
    if roll < 0.55:
        mv = ai.decide_move(room, uid, rng=rng)
        return (mv["action"], mv["amount"])
    return ("check", None) if a["check"] else ("call", None)


def snapshot_for_showdown(room):
    return {
        "board": list(room.board),
        "live": list(room.live()),
        "hole": {u: list(h) for u, h in room.hole.items()},
        "contributed": dict(room.contributed),
        "folded": set(room.folded),
        "labels": {},
    }


def play_game(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 9)
    start = rng.choice([10_000, 20_000, 50_000, 1_000_000])
    settings = dict(DEFAULT_SETTINGS)
    settings.update({
        "starting_chips": start,
        "rounds": rng.choice([3, 8, 20, 60]),
        "blind_up_every": rng.choice([0, 0, 1, 2, 5]),
        "hand_hints": 1,
        "timeout_limit": rng.choice([1, 2, 3]),
    })
    room = Room("FUZZ", "P0", settings)
    uids = ["P%d" % i for i in range(n)]
    for uid in uids:
        room.register_player(uid, uid).connected = True
    if rng.random() < 0.3:
        b = room.register_player("BOT", "Bot")
        b.is_bot = True
        b.connected = True
    ledger = Ledger()
    tag = "seed %d" % seed

    room.start_round()
    ledger.total = sum(room.received.values())
    check_invariants(room, ledger, tag)

    steps = 0
    rounds_seen = 0
    while room.state != STATE_GAME_END:
        steps += 1
        if steps > 20000:
            check(False, "termination: %s game never ended (round %d, state %s)" % (tag, room.round_number, room.state))
            return
        if room.state == STATE_ROUND_END:
            rounds_seen += 1
            # Between rounds: maybe a quit, maybe a late joiner is admitted.
            if rng.random() < 0.05 and len(room.players) > 2:
                q = rng.choice(list(room.players))
                ledger.total -= room.chips.get(q, 0)
                room.remove_participant(q)
                check_invariants(room, ledger, tag + " quit-between")
                if room.state == STATE_GAME_END:
                    break
            if rng.random() < 0.08:
                nid = "L%d" % steps
                p = room.register_player(nid, nid)
                p.connected = True
                p.is_spectator = True
                p.pending_join = True
                p.join_penalty_pct = rng.choice([0, 10, 50])
            before = sum(room.received.values())
            room.start_round()
            ledger.total += sum(room.received.values()) - before
            check_invariants(room, ledger, tag + " new round")
            continue

        if room.phase == PHASE_RUNOUT:
            stats["runout streets"] += 1
            check(room.current_turn_id() is None, "runout: %s someone on turn" % tag)
            snap = snapshot_for_showdown(room)
            for u in snap["live"]:
                snap["labels"][u] = None
            room.step_runout()
            if room.state != STATE_IN_TURN:
                # step_runout dealt the river and settled: judge it.
                snap["board"] = [c for c in room.board] if room.board else snap["board"]
                _finish_judge(room, snap, ledger, tag)
            check_invariants(room, ledger, tag + " runout")
            continue

        cur = room.current
        roll = rng.random()
        snap = snapshot_for_showdown(room)
        if roll < 0.01 and len(room.players) > 2:
            # Someone (often not the player on turn) quits mid-round.
            q = rng.choice(list(room.players))
            ledger.total -= room.chips.get(q, 0)
            room.remove_participant(q)
            tag2 = tag + " quit-mid %s" % q
            stats["quits mid-round"] += 1
        elif roll < 0.04:
            room.force_timeout(cur)
            tag2 = tag + " timeout"
        else:
            action, amount = random_move(room, cur, rng)
            before = (dict(room.chips), dict(room.bets), room.current, room.street)
            try:
                room.act(cur, action, amount)
                stats["moves"] += 1
            except ValueError:
                stats["refused moves"] += 1
                after = (dict(room.chips), dict(room.bets), room.current, room.street)
                check(before == after, "refusal: %s a refused %s %r changed the table" % (tag, action, amount))
            tag2 = tag + " %s %s %r" % (cur, action, amount)
        if room.state != STATE_IN_TURN:
            _finish_judge(room, snap, ledger, tag2)
        check_invariants(room, ledger, tag2)
        # Sat-out players act instantly when the turn reaches them (the ticker does this).
        while (room.state == STATE_IN_TURN and room.phase == PHASE_BETTING
               and room.current in room.sitting_out):
            snap = snapshot_for_showdown(room)
            room.auto_act(room.current)
            if room.state != STATE_IN_TURN:
                _finish_judge(room, snap, ledger, tag + " sat-out")
            check_invariants(room, ledger, tag + " sat-out")

    stats["games"] += 1
    stats["rounds"] += room.round_number
    stats["busts"] += len(room.bust_log)
    check(room.state == STATE_GAME_END and room.game_over, "game end: %s" % tag)
    st = room.standings()
    check(len({r["user_id"] for r in st}) == len(st), "standings: %s duplicate rows" % tag)
    places = [r["place"] for r in st]
    check(places == sorted(places) and (not places or places[0] == 1), "standings: %s places %s" % (tag, places))
    check(room.winner == (st[0]["user_id"] if st else None), "winner: %s" % tag)


def _finish_judge(room, snap, ledger, tag):
    """The round just settled: the hint each player held vs the summary."""
    if room.last_result and not room.last_result.get("fold_win"):
        snap["board"] = list(room.board)
        snap["live"] = [u for u in snap["live"] if u in room.live()]
        snap["contributed"] = dict(room.contributed)
        snap["folded"] = set(room.folded)
        # The hint a player sees for the final board — what the client shows
        # under their cards when the summary opens.
        snap["labels"] = {u: room.hand_label(u) for u in snap["live"]}
        judge_showdown(room, snap, tag)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    rng = random.Random(20261012)
    cats = check_evaluator(rng, 40000)
    print("evaluator categories covered:", {CATEGORY_NAMES[k]: v for k, v in sorted(cats.items())})
    check(all(cats[k] > 50 for k in range(9)), "evaluator coverage: every category sampled")

    games = int(os.environ.get("POKER_FUZZ_GAMES", "400"))
    for seed in range(games):
        play_game(seed)

    print("reached:", dict(stats))
    for k in ("showdowns", "side pots", "split pots", "runout streets", "quits mid-round", "refused moves", "busts"):
        check(stats[k] > 0, "coverage: the random games never produced any %s" % k)
    passed = sum(results)
    print("%d checks, %d failed" % (len(results), len(results) - passed))
    for k, v in failures.most_common():
        print("  %5d x %s" % (v, k))
    print(("PASS " if all(results) else "FAIL ") + "poker fuzz: %d games" % games)
    exit(0 if all(results) else 1)
